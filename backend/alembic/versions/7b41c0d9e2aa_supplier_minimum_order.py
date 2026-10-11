"""supplier minimum order

Revision ID: 7b41c0d9e2aa
Revises: 02896443d4eb

The smallest order a shop will accept, which is a different constraint from
delivery and is the one that actually blocks small baskets. Nullable, because
"this shop publishes no minimum" and "this shop's minimum is zero" are not the
same statement and only one of them is true of most shops.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '7b41c0d9e2aa'
down_revision: Union[str, Sequence[str], None] = '02896443d4eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'suppliers',
        sa.Column('minimum_order', sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('suppliers', 'minimum_order')
