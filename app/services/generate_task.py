"""
Background generation task: fetch Telegram digest and create MP3 for one track.
Adapted from the old run() in telegram_reader/main.py (fetch -> create_episode).
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

from app.core.database import SessionLocal
from app.models import Channel, Track
from app.services.telegram_reader.config import (
    ChannelConfig,
    MODE_LAST_N,
    load_config,
    load_env,
)
from app.services.telegram_reader.fetcher import FetchResult, TelegramDigestFetcher
from app.services.telegram_reader.radio import RadioEpisodeCreator

logger = logging.getLogger(__name__)

# Session name for Telegram client (must match anon.session on disk)
SESSION_NAME = "anon"


async def run_generation_for_track(
    track_id: int,
    config_path: str = "config.json",
    channel_id: int | None = None,
) -> None:
    """
    Load env/config, load channels from DB (all or single by channel_id), fetch digest
    via TelegramDigestFetcher, generate MP3 via RadioEpisodeCreator, then update the track.
    On no content or error, update track accordingly and return.
    """
    load_dotenv()
    env = load_env()
    config = load_config(Path(config_path))

    # Radio path requires Telegram + Gemini credentials
    if not env.api_id or not env.api_hash:
        logger.error("TG_API_ID/TG_API_HASH missing; cannot run generation for track %s", track_id)
        return
    if not env.gemini_key:
        logger.error("GEMINI_KEY missing; cannot run generation for track %s", track_id)
        return

    # Resolve paths from project root (current working directory when uvicorn runs)
    root = Path(".").resolve()
    media_dir = root / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(media_dir / f"{track_id}.mp3")

    db = SessionLocal()
    try:
        track = db.query(Track).filter(Track.id == track_id).first()
        if not track:
            logger.warning("Track id=%s not found; skipping generation", track_id)
            return

        # Load channels from DB: single channel or all (ordered by sort_order, id)
        if channel_id is not None:
            channel = db.query(Channel).filter(Channel.id == channel_id).first()
            channels = [channel] if channel else []
        else:
            channels = (
                db.query(Channel)
                .order_by(Channel.sort_order, Channel.id)
                .all()
            )
        channel_configs = [
            ChannelConfig(
                username=c.username,
                message_limit=c.message_limit,
                only_unread=c.only_unread,
                message_selection_mode=getattr(c, "message_selection_mode", None) or MODE_LAST_N,
                last_digest_message_id=getattr(c, "last_digest_message_id", None),
                last_digest_message_at=getattr(c, "last_digest_message_at", None),
            )
            for c in channels
        ]
        if not channel_configs:
            logger.warning("No channels to fetch for track %s", track_id)
            track.status = "new"
            track.file_url = None
            db.commit()
            return

        # Optionally set track display for single-channel run
        if len(channels) == 1:
            track.channel_id = channels[0].id
            track.channel_name = channels[0].display_name or channels[0].username
        else:
            track.channel_name = "TeleDigest"

        async with TelegramClient(
            SESSION_NAME,
            int(env.api_id),
            env.api_hash,
        ) as client:
            fetcher = TelegramDigestFetcher(client, config, channel_configs)
            result = await fetcher.fetch()

        if result is None:
            track.status = "new"
            track.file_url = None
            db.commit()
            logger.info("No new messages for track %s; marked as new (no file)", track_id)
            return

        creator = RadioEpisodeCreator(gemini_api_key=env.gemini_key)
        try:
            content_for_gemini = result.prompt_prefix + result.content_data_only
            await creator.create_episode(content_for_gemini, output_path=output_path)
        except Exception as err:
            logger.exception("Radio episode failed for track %s: %s", track_id, err)
            return

        # Timestamp when digest was finished; use for filename and DB
        digest_created_at = datetime.now(timezone.utc)
        final_name = f"digest_{digest_created_at.strftime('%Y-%m-%d_%H-%M')}_{track_id}.mp3"
        final_mp3_path = media_dir / final_name
        initial_mp3_path = Path(output_path)
        if initial_mp3_path.resolve() != final_mp3_path.resolve():
            initial_mp3_path.rename(final_mp3_path)

        # Transcript: raw message data only (before AI prompt was added), same basename as MP3
        transcript_path = final_mp3_path.with_suffix(".txt")
        transcript_path.write_text(result.content_data_only, encoding="utf-8")

        # Normalize datetimes to UTC for storage (SQLite has no timezone)
        def _utc(dt: datetime | None) -> datetime | None:
            if dt is None:
                return None
            return dt.astimezone(timezone.utc).replace(tzinfo=None) if getattr(dt, "tzinfo", None) else dt

        track.status = "new"
        track.file_url = f"/media/{final_name}"
        track.messages_start_at = _utc(result.first_message_at)
        track.messages_end_at = _utc(result.last_message_at)
        track.digest_created_at = digest_created_at.replace(tzinfo=None)
        track.channels_used = json.dumps(result.channel_names) if result.channel_names else None

        # Update per-channel bookmark for since_last_digest mode (id + date for 24h cutoff)
        channels_by_username = {c.username: c for c in channels}
        for username, max_msg_id in result.channel_last_message_ids.items():
            ch = channels_by_username.get(username)
            if ch is not None:
                ch.last_digest_message_id = max_msg_id
                last_at = result.channel_last_message_dates.get(username)
                if last_at is not None:
                    ch.last_digest_message_at = _utc(last_at)

        db.commit()
        logger.info("Track %s ready: %s", track_id, track.file_url)
    finally:
        db.close()
