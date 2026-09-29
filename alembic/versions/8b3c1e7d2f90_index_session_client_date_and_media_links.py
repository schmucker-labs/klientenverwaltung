"""index session client/date and media links

Revision ID: 8b3c1e7d2f90
Revises: 5d2e8a1f4b7c
Create Date: 2026-09-29 23:00:00.000000

SQLite does not index foreign keys by itself. Every client window filters
sessions by client_id, the overlap check and the client list filter by
date, and media usage counts (plus the ON DELETE RESTRICT check when a
medium is deleted) look up session_media by media_id alone - which the
(session_id, media_id) primary key cannot serve. Plain CREATE INDEX, no
table rebuild.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8b3c1e7d2f90"
down_revision: str | Sequence[str] | None = "5d2e8a1f4b7c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index("ix_session_client_id", "session", ["client_id"])
    op.create_index("ix_session_date", "session", ["date"])
    op.create_index("ix_session_media_media_id", "session_media", ["media_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_session_media_media_id", table_name="session_media")
    op.drop_index("ix_session_date", table_name="session")
    op.drop_index("ix_session_client_id", table_name="session")
