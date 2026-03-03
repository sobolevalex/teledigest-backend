"""API routes: tracks list and generate (with background task)."""

import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Track
from app.services.generate_task import run_generation_for_track

router = APIRouter(prefix="/api")


def _run_generation_sync(track_id: int, config_path: str = "config.json") -> None:
    """Sync wrapper for FastAPI BackgroundTasks: run async generation in a new event loop."""
    asyncio.run(run_generation_for_track(track_id, config_path))


@router.get("/tracks")
def list_tracks(db: Session = Depends(get_db)):
    """Return all tracks, newest first."""
    tracks = db.query(Track).order_by(Track.created_at.desc()).all()
    return [
        {
            "id": t.id,
            "title": t.title,
            "channel_name": t.channel_name,
            "status": t.status,
            "file_url": t.file_url,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tracks
    ]


@router.post("/generate")
def create_generate(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Create a new Track (status='progress'), enqueue background generation,
    and return the track_id immediately.
    """
    track = Track(
        title="Daily Digest",
        channel_name="TeleDigest",
        status="progress",
        file_url=None,
    )
    db.add(track)
    db.commit()
    db.refresh(track)
    track_id = track.id

    background_tasks.add_task(_run_generation_sync, track_id, "config.json")
    return {"track_id": track_id}
