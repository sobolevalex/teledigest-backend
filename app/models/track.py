"""Track model: one digest generation job (title, channel, status, file_url)."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.channel import Channel


class Track(Base):
    """A single digest track (e.g. Daily Digest); status progresses to 'new' when MP3 is ready."""

    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), default="Daily Digest", nullable=False)
    channel_name: Mapped[str] = mapped_column(String(255), default="TeleDigest", nullable=False)
    channel_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("channels.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="progress", nullable=False)
    file_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    channel: Mapped["Channel | None"] = relationship(
        "Channel", back_populates="tracks", foreign_keys=[channel_id]
    )
