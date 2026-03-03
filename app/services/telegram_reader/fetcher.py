"""Telegram digest fetcher: collect today's messages from configured channels."""

import logging
from datetime import datetime, timezone

from telethon import TelegramClient
from telethon.tl.functions.messages import GetPeerDialogsRequest

from app.services.telegram_reader.config import AppConfig
from app.services.telegram_reader.text_utils import filter_links, replace_question_marks_to_retorical_questions

logger = logging.getLogger(__name__)

# Max messages to request per channel before applying limit filter
ITER_MESSAGES_LIMIT: int = 50


class TelegramDigestFetcher:
    """Fetches messages from configured channels and builds digest body with AI instructions."""

    def __init__(self, client: TelegramClient, config: AppConfig) -> None:
        self._client = client
        self._config = config
        self._log = logger

    async def fetch(self) -> str | None:
        """
        Iterate over config.channels, collect today's messages (optionally only unread),
        build blocks with filter_links, then prepend system prompt and return full content.
        Returns None if no messages were collected.
        """
        self._log.info("Starting message collection...")
        local_midnight = datetime.now().astimezone().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today = local_midnight.astimezone(timezone.utc)
        full_body: list[str] = []

        for target in self._config.channels:
            try:
                entity = await self._client.get_entity(target)
                title = entity.title if hasattr(entity, "title") else str(target)
                self._log.info("Scanning: %s...", title)

                unread_count: int | None = None
                read_inbox_max_id: int = 0
                if self._config.show_unread_count or self._config.only_unread:
                    try:
                        peer = await self._client.get_input_entity(entity)
                        result = await self._client(
                            GetPeerDialogsRequest(peers=[peer])
                        )
                        if result.dialogs:
                            dialog = result.dialogs[0]
                            if self._config.show_unread_count:
                                unread_count = (
                                    getattr(dialog, "unread_count", 0) or 0
                                )
                            if self._config.only_unread:
                                read_inbox_max_id = (
                                    getattr(dialog, "read_inbox_max_id", 0)
                                    or 0
                                )
                    except Exception:
                        pass

                msgs: list[str] = []
                max_read_id: int | None = None
                async for message in self._client.iter_messages(
                    entity, limit=ITER_MESSAGES_LIMIT
                ):
                    if not (message.date > today and message.text):
                        continue
                    if (
                        self._config.only_unread
                        and message.id <= read_inbox_max_id
                    ):
                        continue
                    if max_read_id is None:
                        max_read_id = message.id

                    time_str = message.date.astimezone().strftime("%H:%M")
                    sender_name = ""
                    if message.sender and hasattr(
                        message.sender, "first_name"
                    ):
                        sender_name = f"{message.sender.first_name}: "
                    msgs.append(f"[{time_str}] {sender_name}{message.text}")

                    if len(msgs) >= self._config.message_limit_per_channel:
                        break

                if msgs:
                    msgs.reverse()
                    header = f"=== Начало канала: {title} ==="
                    if unread_count is not None:
                        header += f" (непрочитанных в диалоге: {unread_count})"
                    header += "\n"
                    block = header + "\n\n".join(msgs)
                    block = filter_links(block)
                    block = replace_question_marks_to_retorical_questions(block)
                    full_body.append(block)

                if (
                    self._config.mark_as_read_after_fetch
                    and max_read_id is not None
                ):
                    try:
                        await self._client.send_read_acknowledge(
                            entity, max_id=max_read_id
                        )
                        self._log.info(
                            "Marked read up to id=%s", max_read_id
                        )
                    except Exception as err:
                        self._log.warning(
                            "Could not mark as read: %s", err
                        )

            except ValueError:
                self._log.warning("Channel not found: %s", target)
            except Exception as err:
                self._log.exception("Error with %s: %s", target, err)

        if not full_body:
            self._log.info("No new messages for today.")
            return None

        date_str = datetime.now().strftime("%d.%m.%Y")
        time_str = datetime.now().strftime("%H:%M")
        system_prompt = (
            f"\n\n--- ИНСТРУКЦИЯ ДЛЯ AI (GEMINI) ---\n"
            f"{self._config.ai_instructions}\n\n"
            f"-----------------------------------\n\n"
            f"--- НАЧАЛО ДАННЫХ ({date_str} - {time_str}) ---\n"
        )
        final_content = system_prompt + "\n\n".join(full_body)
        return final_content
