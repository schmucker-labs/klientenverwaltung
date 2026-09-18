"""require duration minutes on session

Revision ID: 71b6a09c0da8
Revises: 9ac5d775d208
Create Date: 2026-09-18 19:01:06.252031

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "71b6a09c0da8"
down_revision: str | Sequence[str] | None = "9ac5d775d208"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _session_table(*, duration_minutes_nullable: bool) -> sa.Table:
    # Written out explicitly (not reflected, not imported from the current
    # models module) so batch mode recreates the table with the same
    # ON DELETE CASCADE / RESTRICT behaviour it already has: SQLAlchemy's
    # SQLite reflection drops those ondelete clauses, so letting
    # batch_alter_table reflect the table itself would silently lose them.
    return sa.Table(
        "session",
        sa.MetaData(),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("treatment_type_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=duration_minutes_nullable),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["client_id"], ["client.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["treatment_type_id"], ["treatment_type.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def upgrade() -> None:
    """Upgrade schema."""
    session_table = sa.table("session", sa.column("duration_minutes", sa.Integer()))
    op.execute(
        session_table.update()
        .where(session_table.c.duration_minutes.is_(None))
        .values(duration_minutes=60)
    )
    with op.batch_alter_table(
        "session", copy_from=_session_table(duration_minutes_nullable=True)
    ) as batch_op:
        batch_op.alter_column(
            "duration_minutes", existing_type=sa.Integer(), nullable=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table(
        "session", copy_from=_session_table(duration_minutes_nullable=False)
    ) as batch_op:
        batch_op.alter_column(
            "duration_minutes", existing_type=sa.Integer(), nullable=True
        )
