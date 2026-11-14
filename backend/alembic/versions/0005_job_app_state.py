"""Job and AppState tables.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-13

Adds:
- job: id, kind (default summary), status (queued/running/done/failed),
  title, meeting_date, transcript, result (JSON), error, attempts,
  created_at, started_at, finished_at, posted_at
- app_state: key (pk), value (JSON), updated_at
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "kind",
            sa.String(50),
            nullable=False,
            server_default="summary",
        ),
        sa.Column(
            "status",
            sa.String(10),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("meeting_date", sa.Date(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "app_state",
        sa.Column("key", sa.String(100), primary_key=True, nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("app_state")
    op.drop_table("job")
