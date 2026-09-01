"""add_indexes

Revision ID: 90210f63f1ae
Revises: 8511f63f1ad8
Create Date: 2026-09-01 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '90210f63f1ae'
down_revision: Union[str, Sequence[str], None] = '8511f63f1ad8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_expenses_user_id_date', 'expenses', ['user_id', 'date'])
    op.create_index('ix_expenses_user_id', 'expenses', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_expenses_user_id_date', table_name='expenses')
    op.drop_index('ix_expenses_user_id', table_name='expenses')
