"""Apply listen-state transitions for tracks (play_status + in-file position)."""

from __future__ import annotations

from typing import Literal

from sqlalchemy.orm import Session

from app.models import Track

PLAY_NEW = "new"
PLAY_STARTED = "started"
PLAY_PLAYED = "played"

ListenAction = Literal["mark_new", "mark_played", "progress"]


class ListenPatchError(Exception):
    """Invalid transition or missing data."""

    def __init__(self, message: str, code: str = "invalid") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def apply_listen_patch(
    db: Session,
    track_id: int,
    action: ListenAction,
    position_seconds: float | None,
) -> Track:
    """
    Mutate track listen metadata and commit.
    Raises ListenPatchError for business-rule violations.
    """
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise ListenPatchError("Track not found", code="not_found")

    if action == "mark_new":
        track.play_status = PLAY_NEW
        track.playback_position_seconds = None
    elif action == "mark_played":
        track.play_status = PLAY_PLAYED
        track.playback_position_seconds = None
    elif action == "progress":
        if position_seconds is None:
            raise ListenPatchError("position_seconds is required for progress", code="bad_request")
        pos = max(0.0, float(position_seconds))
        # Re-listening from "played" (e.g. All tab) returns to started with the given position.
        track.play_status = PLAY_STARTED
        track.playback_position_seconds = pos
    else:
        raise ListenPatchError(f"Unknown action: {action}", code="bad_request")

    db.commit()
    db.refresh(track)
    return track
