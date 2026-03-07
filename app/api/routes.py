"""API routes: tracks, channels CRUD, generate (with background task), and Telegram channel list."""

import asyncio
import base64
import json
from datetime import datetime

from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Channel, Track
from app.services.generate_task import run_generation_for_track
from app.services.telegram_reader.config import MODE_LAST_N, load_env
from app.services.telegram_reader.channel_list import list_telegram_channels

router = APIRouter(prefix="/api")


# --- Request/response schemas for channels ---


class ChannelCreate(BaseModel):
    """Body for POST /api/channels."""

    username: str
    display_name: str | None = None
    message_limit: int | None = None
    sort_order: int = 0
    message_selection_mode: str | None = None  # "last_n" | "since_last_digest"; default last_n


class ChannelUpdate(BaseModel):
    """Body for PATCH /api/channels/{id}."""

    username: str | None = None
    display_name: str | None = None
    message_limit: int | None = None
    sort_order: int | None = None
    message_selection_mode: str | None = None


class GenerateBody(BaseModel):
    """Optional body for POST /api/generate."""

    channel_id: int | None = None


def _run_generation_sync(
    track_id: int,
    config_path: str = "config.json",
    channel_id: int | None = None,
) -> None:
    """Sync wrapper for FastAPI BackgroundTasks: run async generation in a new event loop."""
    asyncio.run(run_generation_for_track(track_id, config_path, channel_id))


def _track_to_item(t):
    """Build track dict for API response; includes digest metadata and transcript_url."""
    channels_used = None
    if t.channels_used:
        try:
            channels_used = json.loads(t.channels_used)
        except (json.JSONDecodeError, TypeError):
            channels_used = []
    transcript_url = None
    if t.file_url and t.file_url.endswith(".mp3"):
        transcript_url = t.file_url[:-4] + ".txt"
    return {
        "id": t.id,
        "title": t.title,
        "channel_name": t.channel_name,
        "channel_id": t.channel_id,
        "status": t.status,
        "file_url": t.file_url,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "messages_start_at": t.messages_start_at.isoformat() if t.messages_start_at else None,
        "messages_end_at": t.messages_end_at.isoformat() if t.messages_end_at else None,
        "digest_created_at": t.digest_created_at.isoformat() if t.digest_created_at else None,
        "channels_used": channels_used,
        "transcript_url": transcript_url,
    }


def _decode_cursor(cursor_str: str) -> tuple[datetime, int] | None:
    """Decode opaque cursor to (created_at, id). Returns None if invalid."""
    try:
        raw = base64.urlsafe_b64decode(cursor_str.encode("utf-8"))
        data = json.loads(raw.decode("utf-8"))
        created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        return (created_at, int(data["id"]))
    except (ValueError, KeyError, TypeError):
        return None


def _encode_cursor(created_at: datetime, track_id: int) -> str:
    """Encode (created_at, id) into an opaque cursor string."""
    payload = {"created_at": created_at.isoformat(), "id": track_id}
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")


@router.get("/tracks")
def list_tracks(
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    cursor: str | None = Query(None, description="Opaque cursor for next page"),
):
    """
    Return tracks newest first, with cursor-based pagination.
    Use next_cursor from the response as the cursor query param for the next page.
    """
    query = db.query(Track).order_by(Track.created_at.desc(), Track.id.desc())

    if cursor:
        decoded = _decode_cursor(cursor)
        if decoded:
            cursor_created_at, cursor_id = decoded
            # Rows strictly before cursor: (created_at < cursor) or (same created_at and id < cursor_id)
            query = query.filter(
                or_(
                    Track.created_at < cursor_created_at,
                    and_(
                        Track.created_at == cursor_created_at,
                        Track.id < cursor_id,
                    ),
                )
            )
        # Invalid cursor is ignored; first page is returned

    tracks = query.limit(limit + 1).all()
    has_more = len(tracks) > limit
    if has_more:
        tracks = tracks[:limit]
    next_cursor = None
    if has_more and tracks:
        last = tracks[-1]
        next_cursor = _encode_cursor(last.created_at, last.id)

    return {
        "items": [_track_to_item(t) for t in tracks],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


# --- Channels CRUD ---


def _channel_to_item(c) -> dict:
    """Build channel dict for API response."""
    last_at = getattr(c, "last_digest_message_at", None)
    return {
        "id": c.id,
        "username": c.username,
        "display_name": c.display_name,
        "message_limit": c.message_limit,
        "sort_order": c.sort_order,
        "message_selection_mode": getattr(c, "message_selection_mode", None) or MODE_LAST_N,
        "last_digest_message_at": last_at.isoformat() if last_at else None,
    }


@router.get("/channels")
def list_channels(db: Session = Depends(get_db)):
    """Return all channels from DB, ordered by sort_order then id."""
    channels = (
        db.query(Channel).order_by(Channel.sort_order, Channel.id).all()
    )
    return [_channel_to_item(c) for c in channels]


@router.get("/channels/{channel_id}")
def get_channel(channel_id: int, db: Session = Depends(get_db)):
    """Return a single channel by ID. Returns 404 if not found."""
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    return _channel_to_item(channel)


@router.post("/channels")
def create_channel(body: ChannelCreate, db: Session = Depends(get_db)):
    """Add a channel by Telegram username. Returns 409 if username already exists."""
    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="username is required")
    existing = db.query(Channel).filter(Channel.username == username).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Channel with username '{username}' already exists",
        )
    channel = Channel(
        username=username,
        display_name=body.display_name.strip() if body.display_name else None,
        message_limit=body.message_limit,
        sort_order=body.sort_order,
        message_selection_mode=body.message_selection_mode or MODE_LAST_N,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return _channel_to_item(channel)


@router.patch("/channels/{channel_id}")
def update_channel(
    channel_id: int,
    body: ChannelUpdate,
    db: Session = Depends(get_db),
):
    """Update channel by id. Returns 404 if not found."""
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if body.username is not None:
        username = body.username.strip()
        if username:
            other = db.query(Channel).filter(Channel.username == username).first()
            if other and other.id != channel_id:
                raise HTTPException(
                    status_code=409,
                    detail=f"Channel with username '{username}' already exists",
                )
            channel.username = username
    if body.display_name is not None:
        channel.display_name = body.display_name.strip() or None
    if body.message_limit is not None:
        channel.message_limit = body.message_limit
    if body.sort_order is not None:
        channel.sort_order = body.sort_order
    if body.message_selection_mode is not None:
        channel.message_selection_mode = body.message_selection_mode
    db.commit()
    db.refresh(channel)
    return _channel_to_item(channel)


@router.delete("/channels/{channel_id}")
def delete_channel(channel_id: int, db: Session = Depends(get_db)):
    """Remove channel by id. Returns 404 if not found."""
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    db.delete(channel)
    db.commit()
    return {"ok": True}


# --- Telegram: list channels from account ---


@router.get("/telegram/channels")
async def list_telegram_channels_api():
    """
    Return all channels (and megagroups) the Telegram account has access to.
    Requires TG_API_ID and TG_API_HASH in .env and a valid anon.session.
    """
    load_dotenv()
    env = load_env()
    if not env.api_id or not env.api_hash:
        raise HTTPException(
            status_code=503,
            detail="Telegram not configured: set TG_API_ID and TG_API_HASH in .env",
        )
    try:
        channels = await list_telegram_channels(
            int(env.api_id), env.api_hash, session_name="anon"
        )
        return {"channels": channels}
    except Exception as err:
        raise HTTPException(
            status_code=502,
            detail=f"Telegram error: {err!s}",
        )


# --- Generate ---


@router.post("/generate")
def create_generate(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    body: GenerateBody | None = Body(None),
):
    """
    Create a new Track (status='progress'), enqueue background generation,
    and return the track_id immediately.
    Optional body: { "channel_id": 2 } to run conversion only for that channel.
    If no channels in DB and no channel_id, returns 400.
    """
    channel_id = body.channel_id if body else None
    if channel_id is not None:
        channel = db.query(Channel).filter(Channel.id == channel_id).first()
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        title = channel.display_name or channel.username
        channel_name = title
    else:
        # Full digest: ensure at least one channel exists
        channel_count = db.query(Channel).count()
        if channel_count == 0:
            raise HTTPException(
                status_code=400,
                detail="No channels in DB. Add channels first or pass channel_id.",
            )
        title = "Daily Digest"
        channel_name = "Various channels"

    track = Track(
        title=title,
        channel_name=channel_name,
        channel_id=channel_id,
        status="progress",
        file_url=None,
    )
    db.add(track)
    db.commit()
    db.refresh(track)
    track_id = track.id

    background_tasks.add_task(
        _run_generation_sync, track_id, "config.json", channel_id
    )
    return {"track_id": track_id}
