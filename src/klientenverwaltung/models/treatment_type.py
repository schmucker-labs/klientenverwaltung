from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from klientenverwaltung.models.base import Base

if TYPE_CHECKING:
    from klientenverwaltung.models.session import TreatmentSession


class TreatmentType(Base):
    __tablename__ = "treatment_type"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(default=True)

    # Quoted: TreatmentSession is only imported under TYPE_CHECKING to avoid a
    # circular import, so SQLAlchemy must resolve the name via its mapper
    # registry rather than by evaluating the annotation against module globals.
    sessions: Mapped[list["TreatmentSession"]] = relationship(  # noqa: UP037
        back_populates="treatment_type",
        passive_deletes=True,
    )
