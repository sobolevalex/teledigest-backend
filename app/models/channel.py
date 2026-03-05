"""Channel model: Telegram channel stored in DB (username, per-channel fetch options)."""

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Channel(Base):
    """
    A Telegram channel to fetch messages from.
    username = Telegram handle (e.g. nexta_live); display_name is optional UI label.
    """

    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Null = no cap (or "all unread" when only_unread is True)
    message_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    only_unread: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    tracks: Mapped[list["Track"]] = relationship(
        "Track", back_populates="channel", foreign_keys="Track.channel_id"
    )
