"""
List Telegram channels the logged-in account has access to.
Uses the same session and API credentials as the rest of the app.
"""

from telethon import TelegramClient
from telethon.tl.types import Channel


async def list_telegram_channels(
    api_id: int,
    api_hash: str,
    session_name: str = "anon",
) -> list[dict]:
    """
    Return all channels and megagroups the Telegram account has access to.
    Each item: {"kind": "channel" | "megagroup", "title": str, "username": str | None, "id": int}.
    """
    result: list[dict] = []
    async with TelegramClient(session_name, api_id, api_hash) as client:
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if not isinstance(entity, Channel):
                continue
            kind = "channel" if entity.broadcast else "megagroup"
            username = getattr(entity, "username", None)
            result.append(
                {
                    "kind": kind,
                    "title": entity.title,
                    "username": username,
                    "id": entity.id,
                }
            )
    return sorted(result, key=lambda x: x["title"].lower())
