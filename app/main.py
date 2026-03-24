"""
TeleDigest FastAPI entry point.
Loads .env from project root, sets up SQLite, CORS, static media, and API routes.
"""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.core.database import Base, engine
from app.realtime.playback_hub import playback_hub
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


def _migrate_channels_add_selection_mode() -> None:
    """Add message_selection_mode and last_digest_message_id to channels if missing."""
    with engine.connect() as conn:
        # Check if channels table exists (pragma_table_info returns empty for missing table)
        result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='channels'"))
        if result.scalar() is None:
            return
        for col_name, col_type in [
            ("message_selection_mode", "VARCHAR(32)"),
            ("last_digest_message_id", "INTEGER"),
            ("last_digest_message_at", "DATETIME"),
        ]:
            result = conn.execute(
                text("SELECT 1 FROM pragma_table_info('channels') WHERE name=:name"),
                {"name": col_name},
            )
            if result.scalar() is None:
                conn.execute(text(f"ALTER TABLE channels ADD COLUMN {col_name} {col_type}"))
                conn.commit()
        # Backfill default for existing rows (SQLite does not support ADD COLUMN ... DEFAULT easily)
        conn.execute(
            text("UPDATE channels SET message_selection_mode = 'last_n' WHERE message_selection_mode IS NULL")
        )
        conn.commit()


def _migrate_tracks_add_play_metadata() -> None:
    """Add play_status and playback_position_seconds for listen state (new | started | played)."""
    with engine.connect() as conn:
        for col_name, col_type in [
            ("play_status", "VARCHAR(16) DEFAULT 'new'"),
            ("playback_position_seconds", "REAL"),
        ]:
            result = conn.execute(
                text("SELECT 1 FROM pragma_table_info('tracks') WHERE name=:name"),
                {"name": col_name},
            )
            if result.scalar() is None:
                conn.execute(text(f"ALTER TABLE tracks ADD COLUMN {col_name} {col_type}"))
                conn.commit()
        conn.execute(
            text("UPDATE tracks SET play_status = 'new' WHERE play_status IS NULL")
        )
        conn.commit()


_migrate_tracks_add_channel_id()
_migrate_tracks_add_digest_metadata()
_migrate_tracks_add_play_metadata()
_migrate_channels_add_selection_mode()

app = FastAPI(title="TeleDigest")

# Allow localhost, LAN, and any Cloudflare app subdomain (CORS).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=(
        r"https://([a-z0-9.-]+\.)?sobolevfamily\.com"
        r"|http://(192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}):3000"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount media so frontend can GET /media/{track_id}.mp3
app.mount("/media", StaticFiles(directory="media"), name="media")

app.include_router(router)


@app.websocket("/ws/track-playback")
async def websocket_track_playback(websocket: WebSocket):
    """Subscribe to listen-state updates (same payload shape as PATCH /api/tracks/{id}/listen fields)."""
    await playback_hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        playback_hub.disconnect(websocket)
