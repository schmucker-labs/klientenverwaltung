from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from klientenverwaltung.models.base import Base


class Media(Base):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(primary_key=True)
    stored_filename: Mapped[str] = mapped_column(unique=True)
    original_filename: Mapped[str]
    media_kind: Mapped[str]
    size_bytes: Mapped[int] = mapped_column(index=True)
    sha256: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class SessionMedia(Base):
    __tablename__ = "session_media"

    session_id: Mapped[int] = mapped_column(
        ForeignKey("session.id", ondelete="CASCADE"), primary_key=True
    )
    media_id: Mapped[int] = mapped_column(
        ForeignKey("media.id", ondelete="RESTRICT"), primary_key=True
    )
    added_at: Mapped[datetime] = mapped_column(server_default=func.now())
