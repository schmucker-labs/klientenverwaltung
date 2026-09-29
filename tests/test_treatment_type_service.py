from datetime import datetime

import pytest

from klientenverwaltung.models import Client, TreatmentType
from klientenverwaltung.services import ConflictError, NotFoundError, ValidationError
from klientenverwaltung.services.treatment_session_service import (
    TreatmentSessionService,
)
from klientenverwaltung.services.treatment_type_service import TreatmentTypeService


def test_create_treatment_type_persists(
    treatment_type_service: TreatmentTypeService,
) -> None:
    treatment_type = treatment_type_service.create_treatment_type(
        name="Meditation", description="Gefuehrte Meditation"
    )

    fetched = treatment_type_service.get_treatment_type(treatment_type.id)
    assert fetched.name == "Meditation"
    assert fetched.active is True


def test_create_treatment_type_rejects_empty_name(
    treatment_type_service: TreatmentTypeService,
) -> None:
    with pytest.raises(ValidationError):
        treatment_type_service.create_treatment_type(name="   ")


def test_create_treatment_type_rejects_duplicate_name(
    treatment_type_service: TreatmentTypeService, treatment_type: TreatmentType
) -> None:
    with pytest.raises(ConflictError):
        treatment_type_service.create_treatment_type(name=treatment_type.name)


def test_update_treatment_type_changes_name_and_description(
    treatment_type_service: TreatmentTypeService, treatment_type: TreatmentType
) -> None:
    updated = treatment_type_service.update_treatment_type(
        treatment_type.id, name="Neuer Name", description="Neue Beschreibung"
    )
    assert updated.name == "Neuer Name"
    assert updated.description == "Neue Beschreibung"


def test_update_treatment_type_to_existing_name_raises_conflict(
    treatment_type_service: TreatmentTypeService, treatment_type: TreatmentType
) -> None:
    other = treatment_type_service.create_treatment_type(name="Andere Art")

    with pytest.raises(ConflictError):
        treatment_type_service.update_treatment_type(other.id, name=treatment_type.name)


def test_update_unknown_treatment_type_raises_not_found(
    treatment_type_service: TreatmentTypeService,
) -> None:
    with pytest.raises(NotFoundError):
        treatment_type_service.update_treatment_type(999, name="Egal")


def test_delete_unused_treatment_type_removes_it(
    treatment_type_service: TreatmentTypeService, treatment_type: TreatmentType
) -> None:
    treatment_type_service.delete_treatment_type(treatment_type.id)

    with pytest.raises(NotFoundError):
        treatment_type_service.get_treatment_type(treatment_type.id)


def test_delete_used_treatment_type_raises_conflict_with_usage_count(
    treatment_type_service: TreatmentTypeService,
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 1, 1, 10, 0),
        duration_minutes=60,
    )

    with pytest.raises(ConflictError, match="1 Sitzung"):
        treatment_type_service.delete_treatment_type(treatment_type.id)


def test_count_sessions_using_treatment_type(
    treatment_type_service: TreatmentTypeService,
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    assert treatment_type_service.count_sessions_using(treatment_type.id) == 0

    treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 1, 1, 10, 0),
        duration_minutes=60,
    )

    assert treatment_type_service.count_sessions_using(treatment_type.id) == 1


def test_deactivate_and_activate_treatment_type(
    treatment_type_service: TreatmentTypeService, treatment_type: TreatmentType
) -> None:
    treatment_type_service.deactivate_treatment_type(treatment_type.id)
    assert treatment_type_service.get_treatment_type(treatment_type.id).active is False

    treatment_type_service.activate_treatment_type(treatment_type.id)
    assert treatment_type_service.get_treatment_type(treatment_type.id).active is True


def test_list_selectable_for_session_excludes_inactive_by_default(
    treatment_type_service: TreatmentTypeService, treatment_type: TreatmentType
) -> None:
    treatment_type_service.deactivate_treatment_type(treatment_type.id)

    selectable = treatment_type_service.list_selectable_for_session()

    assert treatment_type.id not in [t.id for t in selectable]


def test_list_selectable_for_session_includes_current_even_if_inactive(
    treatment_type_service: TreatmentTypeService, treatment_type: TreatmentType
) -> None:
    treatment_type_service.deactivate_treatment_type(treatment_type.id)

    selectable = treatment_type_service.list_selectable_for_session(
        current_treatment_type_id=treatment_type.id
    )

    assert treatment_type.id in [t.id for t in selectable]


def test_has_treatment_types_and_has_active_treatment_types_when_none_exist(
    treatment_type_service: TreatmentTypeService,
) -> None:
    assert treatment_type_service.has_treatment_types() is False
    assert treatment_type_service.has_active_treatment_types() is False


def test_has_active_treatment_types_false_when_all_deactivated(
    treatment_type_service: TreatmentTypeService, treatment_type: TreatmentType
) -> None:
    treatment_type_service.deactivate_treatment_type(treatment_type.id)

    assert treatment_type_service.has_treatment_types() is True
    assert treatment_type_service.has_active_treatment_types() is False


def test_has_active_treatment_types_true_when_one_is_active(
    treatment_type_service: TreatmentTypeService, treatment_type: TreatmentType
) -> None:
    assert treatment_type_service.has_treatment_types() is True
    assert treatment_type_service.has_active_treatment_types() is True


def test_list_treatment_types_can_exclude_inactive(
    treatment_type_service: TreatmentTypeService, treatment_type: TreatmentType
) -> None:
    treatment_type_service.deactivate_treatment_type(treatment_type.id)
    treatment_type_service.create_treatment_type(name="Aktive Art")

    active_only = treatment_type_service.list_treatment_types(include_inactive=False)
    assert treatment_type.id not in [t.id for t in active_only]

    all_types = treatment_type_service.list_treatment_types()
    assert treatment_type.id in [t.id for t in all_types]


def test_treatment_type_names_are_unique_regardless_of_case(
    treatment_type_service: TreatmentTypeService,
) -> None:
    existing = treatment_type_service.create_treatment_type(name="Meditation")
    other = treatment_type_service.create_treatment_type(name="Reiki")

    with pytest.raises(ConflictError):
        treatment_type_service.create_treatment_type(name="meditation")
    with pytest.raises(ConflictError):
        treatment_type_service.update_treatment_type(other.id, name="MEDITATION")
    # renaming a type to a different casing of its own name stays allowed
    renamed = treatment_type_service.update_treatment_type(
        existing.id, name="MEDITATION"
    )
    assert renamed.name == "MEDITATION"
