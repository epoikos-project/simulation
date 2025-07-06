"""add_last_used_to_simulation

Revision ID: c3b2e1d0f9a8
Revises: ad169b99b7a8
Create Date: 2025-07-05 00:00:00.000000

"""

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision = "c3b2e1d0f9a8"
down_revision = "ad169b99b7a8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "simulation",
        sa.Column(
            "last_used",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column("simulation", "last_used")