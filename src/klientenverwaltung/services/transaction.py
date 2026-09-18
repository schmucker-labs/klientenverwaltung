from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from klientenverwaltung.services.errors import ServiceError


@contextmanager
def transaction(session: Session, error_message: str) -> Iterator[None]:
    """Commit on success; on any SQLAlchemy error, roll back and raise ServiceError.

    Keeps SQLAlchemy exceptions from ever reaching callers of the service layer,
    per the architecture rule that only ServiceError (and subclasses) with
    German-language messages cross that boundary.
    """
    try:
        yield
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise ServiceError(error_message) from exc
