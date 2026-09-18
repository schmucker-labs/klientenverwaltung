from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from klientenverwaltung.models.base import Base

if TYPE_CHECKING:
    from klientenverwaltung.models.session import TreatmentSession


class Client(Base):
    __tablename__ = "client"

    id: Mapped[int] = mapped_column(primary_key=True)
    salutation: Mapped[str | None]
    first_name: Mapped[str]
    last_name: Mapped[str]
    birth_date: Mapped[date | None]
    street: Mapped[str | None]
    postal_code: Mapped[str | None]
    city: Mapped[str | None]
    phone: Mapped[str | None]
    email: Mapped[str | None]
    concern: Mapped[str | None] = mapped_column(Text)
    referral_source: Mapped[str | None]
    consent_date: Mapped[date | None]
    notes: Mapped[str | None] = mapped_column(Text)
    archived: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # Quoted: TreatmentSession is only imported under TYPE_CHECKING to avoid a
    # circular import, so SQLAlchemy must resolve the name via its mapper
    # registry rather than by evaluating the annotation against module globals.
    sessions: Mapped[list["TreatmentSession"]] = relationship(  # noqa: UP037
        back_populates="client",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
