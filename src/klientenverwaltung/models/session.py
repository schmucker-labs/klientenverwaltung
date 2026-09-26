from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from klientenverwaltung.models.base import Base
from klientenverwaltung.models.client import Client
from klientenverwaltung.models.treatment_type import TreatmentType


class TreatmentSession(Base):
    __tablename__ = "session"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id", ondelete="CASCADE"))
    treatment_type_id: Mapped[int] = mapped_column(
        ForeignKey("treatment_type.id", ondelete="RESTRICT")
    )
    date: Mapped[datetime]
    duration_minutes: Mapped[int]
    report: Mapped[str | None] = mapped_column(Text)
    impulses: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    client: Mapped[Client] = relationship(back_populates="sessions")
    treatment_type: Mapped[TreatmentType] = relationship(back_populates="sessions")
