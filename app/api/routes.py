"""API routes: tracks, channels CRUD, generate (with background task), and Telegram channel list."""

import asyncio
import json

from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Channel, Track
from app.services.generate_task import run_generation_for_track
from app.services.telegram_reader.config import load_env
from app.services.telegram_reader.channel_list import list_telegram_channels

router = APIRouter(prefix="/api")


# --- Request/response schemas for channels ---


class ChannelCreate(BaseModel):
    """Body for POST /api/channels."""

    username: str
    display_name: str | None = None
    message_limit: int | None = None
    only_unread: bool = False
    sort_order: int = 0


class ChannelUpdate(BaseModel):
    """Body for PATCH /api/channels/{id}."""

    username: str | None = None
    display_name: str | None = None
    message_limit: int | None = None
    only_unread: bool | None = None
    sort_order: int | None = None


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


@router.get("/tracks")
def list_tracks(db: Session = Depends(get_db)):
    """Return all tracks, newest first."""
    tracks = db.query(Track).order_by(Track.created_at.desc()).all()
    return [_track_to_item(t) for t in tracks]


# --- Channels CRUD ---


@router.get("/channels")
def list_channels(db: Session = Depends(get_db)):
    """Return all channels from DB, ordered by sort_order then id."""
    channels = (
        db.query(Channel).order_by(Channel.sort_order, Channel.id).all()
    )
    return [
        {
            "id": c.id,
            "username": c.username,
            "display_name": c.display_name,
            "message_limit": c.message_limit,
            "only_unread": c.only_unread,
            "sort_order": c.sort_order,
        }
        for c in channels
    ]


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
        only_unread=body.only_unread,
        sort_order=body.sort_order,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return {
        "id": channel.id,
        "username": channel.username,
        "display_name": channel.display_name,
        "message_limit": channel.message_limit,
        "only_unread": channel.only_unread,
        "sort_order": channel.sort_order,
    }


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
    if body.only_unread is not None:
        channel.only_unread = body.only_unread
    if body.sort_order is not None:
        channel.sort_order = body.sort_order
    db.commit()
    db.refresh(channel)
    return {
        "id": channel.id,
        "username": channel.username,
        "display_name": channel.display_name,
        "message_limit": channel.message_limit,
        "only_unread": channel.only_unread,
        "sort_order": channel.sort_order,
    }


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
        channel_name = "TeleDigest"

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
