from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from klientenverwaltung.models import Client, Media, SessionMedia, TreatmentSession


class MediaRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, media: Media) -> Media:
        self._session.add(media)
        self._session.flush()
        return media

    def list_all(self) -> list[Media]:
        return list(self._session.scalars(select(Media)))

    def delete(self, media: Media) -> None:
        self._session.delete(media)

    def get_by_id(self, media_id: int) -> Media | None:
        return self._session.get(Media, media_id)

    def list_by_size(self, size_bytes: int) -> list[Media]:
        stmt = select(Media).where(Media.size_bytes == size_bytes)
        return list(self._session.scalars(stmt))

    def is_linked(self, session_id: int, media_id: int) -> bool:
        return self._get_link(session_id, media_id) is not None

    def link(self, session_id: int, media_id: int) -> None:
        self._session.add(SessionMedia(session_id=session_id, media_id=media_id))
        self._session.flush()

    def unlink(self, session_id: int, media_id: int) -> bool:
        link = self._get_link(session_id, media_id)
        if link is None:
            return False
        self._session.delete(link)
        return True

    def list_for_session(self, session_id: int) -> list[tuple[Media, datetime]]:
        stmt = (
            select(Media, SessionMedia.added_at)
            .join(SessionMedia, SessionMedia.media_id == Media.id)
            .where(SessionMedia.session_id == session_id)
            .order_by(SessionMedia.added_at)
        )
        return [(media, added_at) for media, added_at in self._session.execute(stmt).all()]

    def count_for_sessions(self, session_ids: Sequence[int]) -> dict[int, int]:
        if not session_ids:
            return {}
        stmt = (
            select(SessionMedia.session_id, func.count(SessionMedia.media_id))
            .where(SessionMedia.session_id.in_(session_ids))
            .group_by(SessionMedia.session_id)
        )
        return dict(self._session.execute(stmt).all())

    def usage_counts_for_media(self, media_ids: Sequence[int]) -> dict[int, int]:
        if not media_ids:
            return {}
        stmt = (
            select(SessionMedia.media_id, func.count(SessionMedia.session_id))
            .where(SessionMedia.media_id.in_(media_ids))
            .group_by(SessionMedia.media_id)
        )
        return dict(self._session.execute(stmt).all())

    def list_usages_for_media(self, media_id: int) -> list[tuple[str, str, datetime]]:
        stmt = (
            select(Client.first_name, Client.last_name, TreatmentSession.date)
            .select_from(SessionMedia)
            .join(TreatmentSession, TreatmentSession.id == SessionMedia.session_id)
            .join(Client, Client.id == TreatmentSession.client_id)
            .where(SessionMedia.media_id == media_id)
            .order_by(TreatmentSession.date.desc())
        )
        return list(self._session.execute(stmt).all())

    def list_media_ids_for_client(self, client_id: int) -> list[int]:
        stmt = (
            select(SessionMedia.media_id)
            .join(TreatmentSession, TreatmentSession.id == SessionMedia.session_id)
            .where(TreatmentSession.client_id == client_id)
            .distinct()
        )
        return list(self._session.scalars(stmt))

    def list_unlinked_for_session(self, session_id: int) -> list[Media]:
        linked_subquery = select(SessionMedia.media_id).where(
            SessionMedia.session_id == session_id
        )
        stmt = select(Media).where(Media.id.not_in(linked_subquery))
        stmt = stmt.order_by(Media.original_filename)
        return list(self._session.scalars(stmt))

    def _get_link(self, session_id: int, media_id: int) -> SessionMedia | None:
        return self._session.get(SessionMedia, (session_id, media_id))
