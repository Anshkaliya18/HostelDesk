"""add ai recommendation insight columns

Revision ID: c4d1a7e0f2b9
Revises: 66ae9ccc1b8a
Create Date: 2026-10-27 09:30:00.000000

Additive, nullable columns for the richer queue-aware AI recommendation
(reason, confidence, safety flag, possible duplicate, model provenance).
Idempotent where possible; must be applied BEFORE deploying the backend that
writes these fields.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4d1a7e0f2b9'
down_revision: Union[str, None] = '66ae9ccc1b8a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_COLUMNS = (
    sa.Column("reason", sa.Text(), nullable=True),
    sa.Column("confidence", sa.String(length=10), nullable=True),
    sa.Column("safety_flag", sa.Boolean(), nullable=True),
    sa.Column("duplicate_of_complaint_id", sa.Integer(), nullable=True),
    sa.Column("model", sa.String(length=100), nullable=True),
)


def _existing_columns(bind) -> set[str]:
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns("ai_recommendations")}


def upgrade() -> None:
    bind = op.get_bind()
    existing = _existing_columns(bind)
    for column in _NEW_COLUMNS:
        if column.name not in existing:
            op.add_column("ai_recommendations", column.copy())


def downgrade() -> None:
    bind = op.get_bind()
    existing = _existing_columns(bind)
    for column in reversed(_NEW_COLUMNS):
        if column.name in existing:
            op.drop_column("ai_recommendations", column.name)
