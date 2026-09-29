from __future__ import annotations

from dataclasses import dataclass

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
from klientenverwaltung.services.transaction import database_errors_as, transaction

_LOAD_ERROR = "Die Behandlungsarten konnten nicht geladen werden."


@dataclass(frozen=True)
class TreatmentTypeEntry:
    """A treatment type as the UI shows and edits it (a plain value)."""

    id: int
    name: str
    description: str | None
    active: bool


def _same_name(repo: TreatmentTypeRepository, name: str) -> TreatmentType | None:
    """The existing type whose name equals name ignoring case - "Meditation"
    and "meditation" are the same treatment to the user. Compared in
    Python: the table holds a handful of rows, and SQLite's own case
    folding ignores umlauts."""
    wanted = name.casefold()
    return next(
        (existing for existing in repo.list() if existing.name.casefold() == wanted),
        None,
    )


def _entry(treatment_type: TreatmentType) -> TreatmentTypeEntry:
    return TreatmentTypeEntry(
        id=treatment_type.id,
        name=treatment_type.name,
        description=treatment_type.description,
        active=treatment_type.active,
    )


class TreatmentTypeService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    @database_errors_as("Behandlungsart konnte nicht gespeichert werden.")
    def create_treatment_type(
        self, *, name: str, description: str | None = None
    ) -> TreatmentTypeEntry:
        name = self._validate_name(name)
        with self._session_factory() as session:
            repo = TreatmentTypeRepository(session)
            if _same_name(repo, name) is not None:
                raise ConflictError(
                    f'Eine Behandlungsart mit dem Namen "{name}" existiert bereits.'
                )
            treatment_type = TreatmentType(name=name, description=description)
            with transaction(
                session, "Behandlungsart konnte nicht gespeichert werden."
            ):
                repo.add(treatment_type)
            return _entry(treatment_type)

    @database_errors_as(_LOAD_ERROR)
    def get_treatment_type(self, treatment_type_id: int) -> TreatmentTypeEntry:
        with self._session_factory() as session:
            treatment_type = TreatmentTypeRepository(session).get_by_id(
                treatment_type_id
            )
            if treatment_type is None:
                raise NotFoundError(
                    f"Behandlungsart mit ID {treatment_type_id} wurde nicht gefunden."
                )
            return _entry(treatment_type)

    @database_errors_as(_LOAD_ERROR)
    def list_treatment_types(
        self, *, include_inactive: bool = True
    ) -> list[TreatmentTypeEntry]:
        with self._session_factory() as session:
            return [
                _entry(treatment_type)
                for treatment_type in TreatmentTypeRepository(session).list(
                    include_inactive=include_inactive
                )
            ]

    @database_errors_as(_LOAD_ERROR)
    def has_treatment_types(self) -> bool:
        """True if any treatment type exists at all, active or not.

        Distinguishes "none created yet" from "all deactivated" for the
        "Neue Sitzung" hint text (Auftrag D1) - has_active_treatment_types()
        alone can't tell those two cases apart.
        """
        with self._session_factory() as session:
            return len(TreatmentTypeRepository(session).list(include_inactive=True)) > 0

    @database_errors_as(_LOAD_ERROR)
    def has_active_treatment_types(self) -> bool:
        with self._session_factory() as session:
            return (
                len(TreatmentTypeRepository(session).list(include_inactive=False)) > 0
            )

    @database_errors_as(_LOAD_ERROR)
    def list_selectable_for_session(
        self, *, current_treatment_type_id: int | None = None
    ) -> list[TreatmentTypeEntry]:
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
            return [_entry(treatment_type) for treatment_type in types]

    @database_errors_as("Behandlungsart konnte nicht gespeichert werden.")
    def update_treatment_type(
        self, treatment_type_id: int, *, name: str, description: str | None = None
    ) -> TreatmentTypeEntry:
        name = self._validate_name(name)
        with self._session_factory() as session:
            repo = TreatmentTypeRepository(session)
            treatment_type = repo.get_by_id(treatment_type_id)
            if treatment_type is None:
                raise NotFoundError(
                    f"Behandlungsart mit ID {treatment_type_id} wurde nicht gefunden."
                )
            existing = _same_name(repo, name)
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
            return _entry(treatment_type)

    @database_errors_as(_LOAD_ERROR)
    def count_sessions_using(self, treatment_type_id: int) -> int:
        with self._session_factory() as session:
            return TreatmentSessionRepository(session).count_for_treatment_type(
                treatment_type_id
            )

    @database_errors_as("Behandlungsart konnte nicht gelöscht werden.")
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

    @database_errors_as("Behandlungsart konnte nicht aktualisiert werden.")
    def activate_treatment_type(self, treatment_type_id: int) -> None:
        self._set_active(treatment_type_id, active=True)

    @database_errors_as("Behandlungsart konnte nicht aktualisiert werden.")
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
