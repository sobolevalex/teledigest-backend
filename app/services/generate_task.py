"""
Background generation task: fetch Telegram digest and create MP3 for one track.
Adapted from the old run() in telegram_reader/main.py (fetch -> create_episode).
"""

import logging
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

from app.core.database import SessionLocal
from app.models import Track
from app.services.telegram_reader.config import load_config, load_env
from app.services.telegram_reader.fetcher import TelegramDigestFetcher
from app.services.telegram_reader.radio import RadioEpisodeCreator

logger = logging.getLogger(__name__)

# Session name for Telegram client (must match anon.session on disk)
SESSION_NAME = "anon"


async def run_generation_for_track(
    track_id: int,
    config_path: str = "config.json",
) -> None:
    """
    Load env/config, fetch digest via TelegramDigestFetcher, generate MP3 via
    RadioEpisodeCreator, then update the track (status='new', file_url).
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

        async with TelegramClient(
            SESSION_NAME,
            int(env.api_id),
            env.api_hash,
        ) as client:
            fetcher = TelegramDigestFetcher(client, config)
            content = await fetcher.fetch()

        if content is None:
            track.status = "new"
            track.file_url = None
            db.commit()
            logger.info("No new messages for track %s; marked as new (no file)", track_id)
            return

        creator = RadioEpisodeCreator(gemini_api_key=env.gemini_key)
        try:
            await creator.create_episode(content, output_path=output_path)
        except Exception as err:
            logger.exception("Radio episode failed for track %s: %s", track_id, err)
            # Leave status='progress', file_url=None so frontend can retry or show error
            return

        track.status = "new"
        track.file_url = f"/media/{track_id}.mp3"
        db.commit()
        logger.info("Track %s ready: %s", track_id, track.file_url)
    finally:
        db.close()
