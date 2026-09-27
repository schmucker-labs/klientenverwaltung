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
    # func.now() alone would store SQLite's CURRENT_TIMESTAMP, which is
    # UTC - the app displays this value with strftime as if it were
    # already local (matching how session.date is a naive local value),
    # so a Python-side default is needed too; it takes precedence over the
    # server_default for any row actually inserted through the ORM, which
    # is the only way this app writes here. server_default stays as a
    # backstop for a row inserted any other way.
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), default=datetime.now
    )


class SessionMedia(Base):
    __tablename__ = "session_media"

    session_id: Mapped[int] = mapped_column(
        ForeignKey("session.id", ondelete="CASCADE"), primary_key=True
    )
    media_id: Mapped[int] = mapped_column(
        ForeignKey("media.id", ondelete="RESTRICT"), primary_key=True
    )
    added_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), default=datetime.now
    )
