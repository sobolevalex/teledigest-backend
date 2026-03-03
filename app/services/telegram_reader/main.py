"""Orchestration: load config, fetch digest, send via email or radio."""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

from app.services.telegram_reader.config import EnvVars, load_config, load_env
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

    session_name = "anon"
    async with TelegramClient(
        session_name, int(env.api_id), env.api_hash
    ) as client:
        fetcher = TelegramDigestFetcher(client, config)
        content = await fetcher.fetch()

    if content is None:
        logger.info("No new messages today. Exiting.")
        return

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
