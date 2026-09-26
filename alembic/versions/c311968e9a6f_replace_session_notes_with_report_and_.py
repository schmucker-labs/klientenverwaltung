"""replace session notes with report and impulses

Revision ID: c311968e9a6f
Revises: 71b6a09c0da8
Create Date: 2026-09-26 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c311968e9a6f"
down_revision: str | Sequence[str] | None = "71b6a09c0da8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _session_table(*, note_columns: list[sa.Column]) -> sa.Table:
    # Written out explicitly (not reflected) so batch mode recreates the
    # table with the same ON DELETE CASCADE / RESTRICT behaviour it already
    # has - see 71b6a09c0da8 for why reflection can't be trusted with this.
    return sa.Table(
        "session",
        sa.MetaData(),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("treatment_type_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        *note_columns,
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
    # No data carried over: only test data exists so far (see CLAUDE.md).
    with op.batch_alter_table(
        "session",
        copy_from=_session_table(
            note_columns=[sa.Column("notes", sa.Text(), nullable=True)]
        ),
    ) as batch_op:
        batch_op.drop_column("notes")
        batch_op.add_column(sa.Column("report", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("impulses", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table(
        "session",
        copy_from=_session_table(
            note_columns=[
                sa.Column("report", sa.Text(), nullable=True),
                sa.Column("impulses", sa.Text(), nullable=True),
            ]
        ),
    ) as batch_op:
        batch_op.drop_column("report")
        batch_op.drop_column("impulses")
        batch_op.add_column(sa.Column("notes", sa.Text(), nullable=True))
