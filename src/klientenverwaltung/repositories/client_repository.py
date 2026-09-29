from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from klientenverwaltung.models import Client


class ClientRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, client: Client) -> Client:
        self._session.add(client)
        self._session.flush()
        return client

    def get_by_id(self, client_id: int) -> Client | None:
        return self._session.get(Client, client_id)

    def delete(self, client: Client) -> None:
        self._session.delete(client)

    def list(self, *, include_archived: bool = False) -> list[Client]:
        # Text search happens in the service (services/search.py) - SQLite's
        # LIKE is ASCII-only case-insensitive.
        stmt = select(Client)
        if not include_archived:
            stmt = stmt.where(Client.archived.is_(False))
        stmt = stmt.order_by(Client.last_name, Client.first_name)
        return list(self._session.scalars(stmt))
