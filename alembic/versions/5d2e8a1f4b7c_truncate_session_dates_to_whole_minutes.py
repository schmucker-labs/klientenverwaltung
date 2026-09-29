"""truncate session dates to whole minutes

Revision ID: 5d2e8a1f4b7c
Revises: c66a9fbe6d01
Create Date: 2026-09-29 22:30:00.000000

Session times are planned and shown in whole minutes, but a start derived
from "now" used to keep invisible seconds/microseconds - which made
back-to-back appointments collide in the overlap check. The service layer
now stores minute precision; this brings existing rows in line.

Truncation cannot create new overlaps: durations are whole minutes, so if
one session ended at or before the next one started, it still does after
both starts are rounded down to the minute.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5d2e8a1f4b7c"
down_revision: str | Sequence[str] | None = "c66a9fbe6d01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Read and written through sa.DateTime, not string functions, so the
    # stored text keeps SQLAlchemy's exact format (string comparisons in
    # WHERE clauses depend on it).
    session_table = sa.table(
        "session", sa.column("id", sa.Integer()), sa.column("date", sa.DateTime())
    )
    connection = op.get_bind()
    rows = connection.execute(sa.select(session_table.c.id, session_table.c.date)).all()
    for session_id, date in rows:
        truncated = date.replace(second=0, microsecond=0)
        if truncated != date:
            connection.execute(
                session_table.update()
                .where(session_table.c.id == session_id)
                .values(date=truncated)
            )


def downgrade() -> None:
    """Downgrade schema."""
    # Nothing to restore: the dropped seconds were never visible or meaningful.
