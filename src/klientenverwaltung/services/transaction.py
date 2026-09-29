from __future__ import annotations

import functools
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import ParamSpec, TypeVar

from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import Session

from klientenverwaltung.services.errors import DataUnavailableError, ServiceError

_P = ParamSpec("_P")
_R = TypeVar("_R")

DATA_UNAVAILABLE_MESSAGE = (
    "Die Verbindung zur Datenplatte wurde unterbrochen. Bitte die Datenplatte "
    "wieder anschließen und den Vorgang wiederholen. Falls das nicht hilft, "
    "das Programm neu starten."
)


def service_error_for(exc: SQLAlchemyError, error_message: str) -> ServiceError:
    """The ServiceError a caller of the service layer sees for exc.

    A lost connection (storage.open_database() reports a vanished data
    drive as a disconnect) gets its own message and type - the user can
    fix it by plugging the drive back in; everything else gets the
    operation's own message.
    """
    if isinstance(exc, DBAPIError) and exc.connection_invalidated:
        return DataUnavailableError(DATA_UNAVAILABLE_MESSAGE)
    return ServiceError(error_message)


@contextmanager
def transaction(session: Session, error_message: str) -> Iterator[None]:
    """Commit on success; on any SQLAlchemy error, roll back and raise ServiceError."""
    try:
        yield
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise service_error_for(exc, error_message) from exc


def database_errors_as(
    error_message: str,
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Decorates a public service method so that no SQLAlchemy exception
    ever reaches its caller - reads included, and every query a write runs
    before its transaction() block - per the architecture rule that only
    ServiceError (and subclasses) with German messages cross that boundary.
    """

    def decorator(func: Callable[_P, _R]) -> Callable[_P, _R]:
        @functools.wraps(func)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            try:
                return func(*args, **kwargs)
            except SQLAlchemyError as exc:
                raise service_error_for(exc, error_message) from exc

        return wrapper

    return decorator
