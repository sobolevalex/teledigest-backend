"""
One-time Telegram session login: creates or re-authorizes anon.session so the API can list channels.

Run from project root (with venv activated):
  PYTHONPATH=. python -m scripts.telegram_login

Requires TG_API_ID and TG_API_HASH in .env. You will be prompted for phone number and code (and 2FA
password if enabled). The session file anon.session is written in the current working directory.

When running the backend in Docker, run this script inside the container so the session is created
in the same filesystem the backend uses:
  docker exec -it teledigest env PYTHONPATH=/app python -m scripts.telegram_login

To persist the session across container rebuilds, add a volume for the session in docker-compose,
e.g. mount ./teledigest-backend:/app and run the script from the host in that directory, or
mount a dedicated volume for anon.session.
"""

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

# Project root on PYTHONPATH
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

load_dotenv(root / ".env")

from app.services.telegram_reader.config import load_env
from telethon import TelegramClient

SESSION_NAME = "anon"


async def main() -> None:
    env = load_env()
    if not env.api_id or not env.api_hash:
        print("Error: set TG_API_ID and TG_API_HASH in .env")
        sys.exit(1)
    client = TelegramClient(
        SESSION_NAME,
        int(env.api_id),
        env.api_hash,
    )
    await client.start()
    me = await client.get_me()
    print(f"Logged in as {me.first_name or 'User'} (id={me.id}). Session saved as {SESSION_NAME}.session")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
