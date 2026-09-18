from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from klientenverwaltung.models import TreatmentType


class TreatmentTypeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, treatment_type: TreatmentType) -> TreatmentType:
        self._session.add(treatment_type)
        self._session.flush()
        return treatment_type

    def get_by_id(self, treatment_type_id: int) -> TreatmentType | None:
        return self._session.get(TreatmentType, treatment_type_id)

    def delete(self, treatment_type: TreatmentType) -> None:
        self._session.delete(treatment_type)

    def get_by_name(self, name: str) -> TreatmentType | None:
        stmt = select(TreatmentType).where(TreatmentType.name == name)
        return self._session.scalars(stmt).one_or_none()

    def list(self, *, include_inactive: bool = True) -> list[TreatmentType]:
        stmt = select(TreatmentType)
        if not include_inactive:
            stmt = stmt.where(TreatmentType.active.is_(True))
        stmt = stmt.order_by(TreatmentType.name)
        return list(self._session.scalars(stmt))
