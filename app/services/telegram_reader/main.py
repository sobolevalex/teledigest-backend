"""Orchestration: load config, fetch digest, send via email or radio."""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

from app.core.database import SessionLocal
from app.models import Channel
from app.services.telegram_reader.config import (
    ChannelConfig,
    EnvVars,
    MODE_LAST_N,
    load_config,
    load_env,
)
from app.services.telegram_reader.email_sender import EmailSender
from app.services.telegram_reader.fetcher import TelegramDigestFetcher
from app.services.telegram_reader.radio import RadioEpisodeCreator

logger = logging.getLogger(__name__)


def _check_env_for_run(env: EnvVars, output_mode: str) -> None:
    """Ensure required env vars are set; exit with message if not."""
    missing: list[str] = []
    if not env.api_id:
        missing.append("TG_API_ID")
    if not env.api_hash:
        missing.append("TG_API_HASH")
    if not env.gmail_user:
        missing.append("GMAIL_USER")
    if not env.gmail_pass:
        missing.append("GMAIL_PASS")
    if not env.to_email:
        missing.append("TO_EMAIL")
    if output_mode == "radio" and not env.gemini_key:
        missing.append("GEMINI_KEY")

    if missing:
        logger.error("Missing required env vars: %s", ", ".join(missing))
        sys.exit(1)


async def run(config_path: str | Path = "config.json") -> None:
    """
    Load env and config, connect to Telegram, fetch digest, then send by email
    or create radio episode according to config.output_mode.
    """
    load_dotenv()
    env = load_env()
    config = load_config(config_path)
    _check_env_for_run(env, config.output_mode)

    # Channel list: DB only for app/API; here use DB first, fallback to config when DB is empty
    channel_configs: list[ChannelConfig] = []
    db = SessionLocal()
    try:
        channels = (
            db.query(Channel)
            .order_by(Channel.sort_order, Channel.id)
            .all()
        )
        if channels:
            channel_configs = [
                ChannelConfig(
                    username=c.username,
                    message_limit=c.message_limit or config.message_limit_per_channel,
                    message_selection_mode=getattr(c, "message_selection_mode", None) or MODE_LAST_N,
                    last_digest_message_id=getattr(c, "last_digest_message_id", None),
                    last_digest_message_at=getattr(c, "last_digest_message_at", None),
                )
                for c in channels
            ]
    finally:
        db.close()

    if not channel_configs and getattr(config, "channels", None):
        # Fallback: config.channels when DB has no channels (standalone CLI without DB)
        channel_configs = [
            ChannelConfig(
                username=c,
                message_limit=config.message_limit_per_channel,
            )
            for c in config.channels
        ]

    if not channel_configs:
        logger.error(
            "No channels. Add channels via API (or DB) or set 'channels' in config.json for standalone run."
        )
        sys.exit(1)

    session_name = "anon"
    async with TelegramClient(
        session_name, int(env.api_id), env.api_hash
    ) as client:
        fetcher = TelegramDigestFetcher(client, config, channel_configs)
        result = await fetcher.fetch()

    if result is None:
        logger.info("No new messages today. Exiting.")
        return

    content = result.prompt_prefix + result.content_data_only
    date_str = datetime.now().strftime("%d.%m.%Y")
    time_str = datetime.now().strftime("%H:%M")
    subject = f"{config.email_subject_prefix} [{date_str} {time_str}]"

    print(content)

    if config.output_mode == "radio":
        if not env.gemini_key:
            logger.error("GEMINI_KEY required for radio mode.")
            sys.exit(1)
        creator = RadioEpisodeCreator(gemini_api_key=env.gemini_key)
        try:
            await creator.create_episode(content)
        except Exception as err:
            logger.exception("Radio episode failed: %s", err)
            sys.exit(1)
    else:
        sender = EmailSender(
            smtp_user=env.gmail_user,
            smtp_password=env.gmail_pass,
            to_email=env.to_email,
        )
        try:
            sender.send_digest(content, subject)
        except Exception as err:
            logger.exception("Email send failed: %s", err)
            logger.info(
                "Tip: mobile/hotspot often block SMTP. Try Wi‑Fi."
            )
            sys.exit(1)


def main() -> None:
    """Entry point: configure logging and run async run()."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run())


if __name__ == "__main__":
    main()
