"""Application configuration: AppConfig from JSON and env vars."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Default voice for TTS (radio mode)
DEFAULT_RADIO_VOICE: str = "ru-RU-DmitryNeural"

# System instruction for Gemini in radio mode
RADIO_SYSTEM_INSTRUCTION: str = """
## РОЛЬ
Ты — ведущий радиоэфира в формате "Марафон новостей".
Твоя задача: Последовательно прочитать слушателю содержимое ленты Telegram-каналов.

## СТРУКТУРА ЭФИРА
1.  **Вступление:** Приветствие, дата.
2.  **Блок 1: Русскоязычные каналы.** (Читаешь подряд).
3.  **Блок 2: Украиноязычные каналы.** (Перевод на русский).
4.  **Блок 3: Иврит/Английский.** (Перевод на русский).
5.  **Заключение.**

## ГЛАВНЫЕ ПРАВИЛА (СТРОГОЕ СОБЛЮДЕНИЕ)

1.  🛑 **ЗАПРЕТ НА ГРУППИРОВКУ (NO CLUSTERING):**
    * КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО объединять разные сообщения в общие темы (например, нельзя создавать рубрики "Военная хроника" или "Политика", сливая туда 5 сообщений).
    * **ОДНО СООБЩЕНИЕ ИЗ ЛОГА = ОДИН ОТДЕЛЬНЫЙ РАССКАЗ В ЭФИРЕ.**
    * Ты должен идти строго хронологически по списку сообщений канала. Прочитал первое -> перешел ко второму -> к третьему. Не перескакивай.

2.  🔍 **ПОЛНОТА КОНТЕНТА:**
    * Если в канале за день вышло 20 постов — в твоем сценарии должно быть озвучено 20 новостей (за исключением рекламы и 100% повторов).
    * Не используй фразы "среди прочих новостей", "также сообщалось о ряде инцидентов". Озвучивай КАЖДЫЙ инцидент отдельно.

3.  ♻️ **УМНАЯ ДЕДУПЛИКАЦИЯ:**
    * Только если новость Б — это *точная копия* новости А (те же факты, то же событие), тогда скажи: *"Канал [Имя] также подтверждает эту информацию"*.
    * Если есть хоть одна новая деталь — читай полностью.

4.  🗑️ **ФИЛЬТР:**
    * Игнорируй только явный мусор: рекламу курсов/казино, просьбы подписаться, одиночные смайлики.

5.  🎙️ **ПОДАЧА:**
    * Используй короткие перебивки между сообщениями, чтобы слушатель понимал, что началась следующая новость: *"Идем дальше...", "Следующее сообщение...", "Тем временем...", "Еще одна новость..."*.
    * Язык: ТОЛЬКО РУССКИЙ.

## ПРИМЕР ПРАВИЛЬНОЙ ОБРАБОТКИ
ВХОД:
[10:00] Удар по Бейруту.
[10:05] Цены на бензин выросли.
[10:10] Удар по Бейруту (повтор).
[10:15] В зоопарке родился слон.

ПРАВИЛЬНЫЙ ВЫХОД:
"Сначала срочная новость: нанесен удар по Бейруту... (подробности).
Следующая тема: водителям придется платить больше — цены на бензин выросли... (подробности).
Канал Х также пишет об ударе по Бейруту, подтверждая данные.
И напоследок позитив: в зоопарке пополнение, там родился слон..."

(НЕПРАВИЛЬНЫЙ ВЫХОД: "Главные темы часа — ситуация в Ливане и экономика. Был удар по Бейруту, а бензин подорожал. Также родился слон.")
"""


@dataclass
class AppConfig:
    """Configuration loaded from config.json."""

    channels: list[str]
    message_limit_per_channel: int
    email_subject_prefix: str
    show_unread_count: bool
    mark_as_read_after_fetch: bool
    only_unread: bool
    output_mode: str  # "email" | "radio"
    ai_instructions: str  # normalized string (list joined by newlines)


@dataclass
class EnvVars:
    """Required environment variables (loaded at entry point)."""

    api_id: str
    api_hash: str
    gmail_user: str
    gmail_pass: str
    to_email: str
    gemini_key: str | None = None


def _normalize_ai_instructions(raw: Any) -> str:
    """Convert ai_instructions from list or string to single string."""
    if isinstance(raw, list):
        return "\n".join(str(line) for line in raw)
    return str(raw or "")


def load_config(path: str | Path) -> AppConfig:
    """
    Load AppConfig from a JSON file.
    Raises FileNotFoundError if the file does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)

    raw_instructions = data.get("ai_instructions", [])
    ai_instructions = _normalize_ai_instructions(raw_instructions)

    return AppConfig(
        channels=data.get("channels", []),
        message_limit_per_channel=int(data.get("message_limit_per_channel", 10)),
        email_subject_prefix=str(data.get("email_subject_prefix", "Telegram Digest")),
        show_unread_count=bool(data.get("show_unread_count", True)),
        mark_as_read_after_fetch=bool(data.get("mark_as_read_after_fetch", False)),
        only_unread=bool(data.get("only_unread", False)),
        output_mode=str(data.get("output_mode", "email")),
        ai_instructions=ai_instructions,
    )


def load_env() -> EnvVars:
    """Load env vars from os.environ (call after load_dotenv())."""
    return EnvVars(
        api_id=os.getenv("TG_API_ID", "").strip(),
        api_hash=os.getenv("TG_API_HASH", "").strip(),
        gmail_user=os.getenv("GMAIL_USER", "").strip(),
        gmail_pass=os.getenv("GMAIL_PASS", "").strip(),
        to_email=os.getenv("TO_EMAIL", "").strip(),
        gemini_key=os.getenv("GEMINI_KEY", "").strip() or None,
    )
