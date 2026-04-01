"""add_sla_and_budget_fields

Revision ID: de96fdc811ae
Revises: 330f267d9b26
Create Date: 2026-04-01 13:48:51.317268

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'de96fdc811ae'
down_revision: Union[str, Sequence[str], None] = '330f267d9b26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('projects', sa.Column('sla_max_latency_ms', sa.Float(), nullable=True))
    op.add_column('projects', sa.Column('sla_max_cost_per_call', sa.Float(), nullable=True))
    op.add_column('projects', sa.Column('sla_max_hallucination_rate', sa.Float(), nullable=True))
    op.add_column('projects', sa.Column('monthly_budget_limit', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('projects', 'monthly_budget_limit')
    op.drop_column('projects', 'sla_max_hallucination_rate')
    op.drop_column('projects', 'sla_max_cost_per_call')
    op.drop_column('projects', 'sla_max_latency_ms')
