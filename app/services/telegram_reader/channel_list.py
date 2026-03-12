"""
List Telegram channels the logged-in account has access to.
Uses the same session and API credentials as the rest of the app.
"""

from telethon import TelegramClient
from telethon.tl.types import Channel


class TelegramSessionUnauthorizedError(Exception):
    """Raised when the Telegram session file exists but is not logged in."""

    pass


async def list_telegram_channels(
    api_id: int,
    api_hash: str,
    session_name: str = "anon",
) -> list[dict]:
    """
    Return all channels and megagroups the Telegram account has access to.
    Each item: {"kind": "channel" | "megagroup", "title": str, "username": str | None, "id": int}.
    Uses connect() + is_user_authorized() to avoid triggering interactive login prompts.
    """
    result: list[dict] = []
    client = TelegramClient(session_name, api_id, api_hash)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise TelegramSessionUnauthorizedError(
                "Telegram session not authorized. Create or re-auth the session (e.g. run the login script) "
                f"so that {session_name}.session exists and is logged in."
            )
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
    finally:
        await client.disconnect()
