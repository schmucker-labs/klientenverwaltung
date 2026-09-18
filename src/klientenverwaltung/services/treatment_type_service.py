from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from klientenverwaltung.models import TreatmentType
from klientenverwaltung.repositories import (
    TreatmentSessionRepository,
    TreatmentTypeRepository,
)
from klientenverwaltung.services.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from klientenverwaltung.services.transaction import transaction


class TreatmentTypeService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create_treatment_type(
        self, *, name: str, description: str | None = None
    ) -> TreatmentType:
        name = self._validate_name(name)
        with self._session_factory() as session:
            repo = TreatmentTypeRepository(session)
            if repo.get_by_name(name) is not None:
                raise ConflictError(
                    f'Eine Behandlungsart mit dem Namen "{name}" existiert bereits.'
                )
            treatment_type = TreatmentType(name=name, description=description)
            with transaction(
                session, "Behandlungsart konnte nicht gespeichert werden."
            ):
                repo.add(treatment_type)
        return treatment_type

    def get_treatment_type(self, treatment_type_id: int) -> TreatmentType:
        with self._session_factory() as session:
            treatment_type = TreatmentTypeRepository(session).get_by_id(
                treatment_type_id
            )
        if treatment_type is None:
            raise NotFoundError(
                f"Behandlungsart mit ID {treatment_type_id} wurde nicht gefunden."
            )
        return treatment_type

    def list_treatment_types(
        self, *, include_inactive: bool = True
    ) -> list[TreatmentType]:
        with self._session_factory() as session:
            return TreatmentTypeRepository(session).list(
                include_inactive=include_inactive
            )

    def list_selectable_for_session(
        self, *, current_treatment_type_id: int | None = None
    ) -> list[TreatmentType]:
        """Active treatment types, plus the given one even if it has since been deactivated.

        Used to populate a session's treatment-type dropdown: new sessions may
        only use active types, but editing an existing session must not lose
        or silently change a historical, since-deactivated type.
        """
        with self._session_factory() as session:
            repo = TreatmentTypeRepository(session)
            types = repo.list(include_inactive=False)
            if (
                current_treatment_type_id is not None
                and current_treatment_type_id not in {t.id for t in types}
            ):
                current = repo.get_by_id(current_treatment_type_id)
                if current is not None:
                    types = [*types, current]
            return types

    def update_treatment_type(
        self, treatment_type_id: int, *, name: str, description: str | None = None
    ) -> TreatmentType:
        name = self._validate_name(name)
        with self._session_factory() as session:
            repo = TreatmentTypeRepository(session)
            treatment_type = repo.get_by_id(treatment_type_id)
            if treatment_type is None:
                raise NotFoundError(
                    f"Behandlungsart mit ID {treatment_type_id} wurde nicht gefunden."
                )
            existing = repo.get_by_name(name)
            if existing is not None and existing.id != treatment_type_id:
                raise ConflictError(
                    f'Eine Behandlungsart mit dem Namen "{name}" existiert bereits.'
                )
            treatment_type.name = name
            treatment_type.description = description
            with transaction(
                session, "Behandlungsart konnte nicht gespeichert werden."
            ):
                pass
        return treatment_type

    def count_sessions_using(self, treatment_type_id: int) -> int:
        with self._session_factory() as session:
            return TreatmentSessionRepository(session).count_for_treatment_type(
                treatment_type_id
            )

    def delete_treatment_type(self, treatment_type_id: int) -> None:
        with self._session_factory() as session:
            repo = TreatmentTypeRepository(session)
            treatment_type = repo.get_by_id(treatment_type_id)
            if treatment_type is None:
                raise NotFoundError(
                    f"Behandlungsart mit ID {treatment_type_id} wurde nicht gefunden."
                )
            usage_count = TreatmentSessionRepository(session).count_for_treatment_type(
                treatment_type_id
            )
            if usage_count > 0:
                raise ConflictError(
                    f'Die Behandlungsart "{treatment_type.name}" wird noch in '
                    f"{usage_count} Sitzung(en) verwendet und kann nicht gelöscht "
                    "werden. Deaktivieren Sie sie stattdessen."
                )
            with transaction(session, "Behandlungsart konnte nicht gelöscht werden."):
                repo.delete(treatment_type)

    def activate_treatment_type(self, treatment_type_id: int) -> None:
        self._set_active(treatment_type_id, active=True)

    def deactivate_treatment_type(self, treatment_type_id: int) -> None:
        self._set_active(treatment_type_id, active=False)

    def _set_active(self, treatment_type_id: int, *, active: bool) -> None:
        with self._session_factory() as session:
            treatment_type = TreatmentTypeRepository(session).get_by_id(
                treatment_type_id
            )
            if treatment_type is None:
                raise NotFoundError(
                    f"Behandlungsart mit ID {treatment_type_id} wurde nicht gefunden."
                )
            treatment_type.active = active
            with transaction(
                session, "Behandlungsart konnte nicht aktualisiert werden."
            ):
                pass

    @staticmethod
    def _validate_name(name: str) -> str:
        name = name.strip()
        if not name:
            raise ValidationError("Der Name der Behandlungsart darf nicht leer sein.")
        return name
