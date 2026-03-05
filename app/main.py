"""
TeleDigest FastAPI entry point.
Loads .env from project root, sets up SQLite, CORS, static media, and API routes.
"""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.core.database import Base, engine
from app.models import Channel, Track  # noqa: F401 - ensure models registered with Base


def _ensure_media_dir() -> None:
    """Create media directory at project root if it does not exist."""
    root = Path(".").resolve()
    (root / "media").mkdir(parents=True, exist_ok=True)


load_dotenv()
Base.metadata.create_all(bind=engine)
_ensure_media_dir()


def _migrate_tracks_add_channel_id() -> None:
    """Add tracks.channel_id if missing (existing DBs created before Channel was added)."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT 1 FROM pragma_table_info('tracks') WHERE name='channel_id'")
        )
        if result.scalar() is None:
            conn.execute(
                text("ALTER TABLE tracks ADD COLUMN channel_id INTEGER REFERENCES channels(id)")
            )
            conn.commit()


def _migrate_tracks_add_digest_metadata() -> None:
    """Add digest metadata columns if missing (messages range, creation time, channels list)."""
    new_columns = [
        ("messages_start_at", "DATETIME"),
        ("messages_end_at", "DATETIME"),
        ("digest_created_at", "DATETIME"),
        ("channels_used", "TEXT"),
    ]
    with engine.connect() as conn:
        for col_name, col_type in new_columns:
            result = conn.execute(
                text("SELECT 1 FROM pragma_table_info('tracks') WHERE name=:name"),
                {"name": col_name},
            )
            if result.scalar() is None:
                conn.execute(text(f"ALTER TABLE tracks ADD COLUMN {col_name} {col_type}"))
                conn.commit()


_migrate_tracks_add_channel_id()
_migrate_tracks_add_digest_metadata()

app = FastAPI(title="TeleDigest")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount media so frontend can GET /media/{track_id}.mp3
app.mount("/media", StaticFiles(directory="media"), name="media")

app.include_router(router)
