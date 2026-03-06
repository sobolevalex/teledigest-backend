"""Telegram digest fetcher: collect today's messages from configured channels."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.tl.functions.messages import GetPeerDialogsRequest

from app.services.telegram_reader.config import (
    AppConfig,
    ChannelConfig,
    MODE_LAST_N,
    MODE_SINCE_LAST_DIGEST,
)
from app.services.telegram_reader.text_utils import filter_links, replace_question_marks_to_retorical_questions

logger = logging.getLogger(__name__)

# Max messages to request per channel before applying limit filter
ITER_MESSAGES_LIMIT: int = 50


@dataclass
class FetchResult:
    """Structured result of a digest fetch: data-only content and metadata (no prompt stored)."""

    content_data_only: str
    prompt_prefix: str
    first_message_at: datetime | None
    last_message_at: datetime | None
    channel_names: list[str]
    # Per-channel max message id included (for updating last_digest_message_id bookmark)
    channel_last_message_ids: dict[str, int]
    # Per-channel datetime of last message (for updating last_digest_message_at)
    channel_last_message_dates: dict[str, datetime]


class TelegramDigestFetcher:
    """Fetches messages from configured channels and builds digest body with AI instructions."""

    def __init__(
        self,
        client: TelegramClient,
        config: AppConfig,
        channel_configs: list[ChannelConfig],
    ) -> None:
        self._client = client
        self._config = config
        self._channel_configs = channel_configs
        self._log = logger

    async def fetch(self) -> FetchResult | None:
        """
        Iterate over channel_configs, collect messages per selection mode (last_n or
        since_last_digest), build blocks with filter_links, then prepend system prompt
        and return full content plus first/last message times and channel names.
        Returns None if no messages.
        """
        usernames = [c.username for c in self._channel_configs]
        self._log.info("Starting message collection for channels: %s", usernames)
        full_body: list[str] = []
        channel_names: list[str] = []
        channel_last_message_ids: dict[str, int] = {}
        channel_last_message_dates: dict[str, datetime] = {}
        first_message_at: datetime | None = None
        last_message_at: datetime | None = None

        for ch_cfg in self._channel_configs:
            target = ch_cfg.username
            try:
                entity = await self._client.get_entity(target)
                title = entity.title if hasattr(entity, "title") else str(target)
                self._log.info("Scanning: %s...", title)

                unread_count: int | None = None
                if self._config.show_unread_count:
                    try:
                        peer = await self._client.get_input_entity(entity)
                        result = await self._client(
                            GetPeerDialogsRequest(peers=[peer])
                        )
                        if result.dialogs:
                            dialog = result.dialogs[0]
                            unread_count = (
                                getattr(dialog, "unread_count", 0) or 0
                            )
                    except Exception:
                        pass

                limit_for_channel = ch_cfg.message_limit or ITER_MESSAGES_LIMIT
                mode = getattr(ch_cfg, "message_selection_mode", None) or MODE_LAST_N
                min_id: int | None = None
                use_today_start = False  # when True: fetch from today 00:00:01 UTC (offset_date + reverse)
                if mode == MODE_SINCE_LAST_DIGEST:
                    last_at = getattr(ch_cfg, "last_digest_message_at", None)
                    last_id = getattr(ch_cfg, "last_digest_message_id", None)
                    if last_at is not None:
                        now_utc = datetime.now(timezone.utc)
                        # DB stores UTC as naive; ensure we have timezone for comparison
                        last_at_utc = last_at.astimezone(timezone.utc) if getattr(last_at, "tzinfo", None) else last_at.replace(tzinfo=timezone.utc)
                        if (now_utc - last_at_utc) > timedelta(hours=24):
                            use_today_start = True
                            self._log.info(
                                "Channel %s: since_last_digest bookmark older than 24h (last_at=%s); using today start",
                                target,
                                last_at,
                            )
                    if not use_today_start and last_id is not None:
                        min_id = last_id
                        self._log.info(
                            "Channel %s: since_last_digest with min_id=%s (last_digest_message_id)",
                            target,
                            min_id,
                        )

                # (message_date, line_text, message_id) for first/last times and bookmark
                msgs: list[tuple[datetime, str, int]] = []
                max_read_id: int | None = None

                kwargs: dict = {"limit": limit_for_channel}
                if use_today_start:
                    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=1, microsecond=0)
                    kwargs["offset_date"] = today_start
                    kwargs["reverse"] = True
                elif min_id is not None:
                    kwargs["min_id"] = min_id

                async for message in self._client.iter_messages(entity, **kwargs):
                    if not message.text:
                        continue
                    if max_read_id is None:
                        max_read_id = message.id

                    time_str = message.date.astimezone().strftime("%H:%M")
                    sender_name = ""
                    if message.sender and hasattr(
                        message.sender, "first_name"
                    ):
                        sender_name = f"{message.sender.first_name}: "
                    line = f"[{time_str}] {sender_name}{message.text}"
                    msgs.append((message.date, line, message.id))

                    if len(msgs) >= limit_for_channel:
                        break

                if msgs:
                    # With min_id we get newest-first; with offset_date+reverse we get oldest-first
                    if not use_today_start:
                        msgs.reverse()
                    dates = [d for d, _, _ in msgs]
                    ch_first = min(dates)
                    ch_last = max(dates)
                    if first_message_at is None or ch_first < first_message_at:
                        first_message_at = ch_first
                    if last_message_at is None or ch_last > last_message_at:
                        last_message_at = ch_last
                    channel_names.append(title)
                    channel_last_message_ids[ch_cfg.username] = max(mid for _, _, mid in msgs)
                    channel_last_message_dates[ch_cfg.username] = ch_last
                    self._log.info(
                        "Channel %s (%s): collected %d messages (mode=%s, min_id=%s, use_today_start=%s)",
                        target,
                        title,
                        len(msgs),
                        mode,
                        min_id,
                        use_today_start,
                    )

                    header = f"=== Начало канала: {title} ==="
                    if unread_count is not None:
                        header += f" (непрочитанных в диалоге: {unread_count})"
                    header += "\n"
                    block = header + "\n\n".join(line for _, line, _ in msgs)
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
                else:
                    self._log.warning(
                        "Channel %s (%s): 0 messages collected (mode=%s, min_id=%s, use_today_start=%s)",
                        target,
                        title,
                        mode,
                        min_id,
                        use_today_start,
                    )
            except ValueError:
                self._log.warning("Channel not found: %s", target)
            except Exception as err:
                self._log.exception("Error with %s: %s", target, err)

        if not full_body:
            self._log.warning(
                "Returning None: no messages collected from any channel (channels tried: %s)",
                usernames,
            )
            return None

        date_str = datetime.now().strftime("%d.%m.%Y")
        time_str = datetime.now().strftime("%H:%M")
        prompt_prefix = (
            f"\n\n--- ИНСТРУКЦИЯ ДЛЯ AI (GEMINI) ---\n"
            f"{self._config.ai_instructions}\n\n"
            f"-----------------------------------\n\n"
            f"--- НАЧАЛО ДАННЫХ ({date_str} - {time_str}) ---\n"
        )
        data_only = "\n\n".join(full_body)
        return FetchResult(
            content_data_only=data_only,
            prompt_prefix=prompt_prefix,
            first_message_at=first_message_at,
            last_message_at=last_message_at,
            channel_names=channel_names,
            channel_last_message_ids=channel_last_message_ids,
            channel_last_message_dates=channel_last_message_dates,
        )
