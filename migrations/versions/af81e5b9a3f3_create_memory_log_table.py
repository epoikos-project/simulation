"""create memory log table

Revision ID: af81e5b9a3f3
Revises: 3755545ac6cc
Create Date: 2025-07-07 14:09:39.514540

"""

import sqlalchemy as sa
import sqlmodel  # New
from alembic import op

# revision identifiers, used by Alembic.
revision = "af81e5b9a3f3"
down_revision = "f7276b3fdcbb"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###

    op.create_table(
        "memorylog",
        sa.Column("created_at", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("simulation_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("memory", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("agent_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("tick", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agent.id"],
        ),
        sa.ForeignKeyConstraint(
            ["simulation_id"],
            ["simulation.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_memorylog_simulation_id"), "memorylog", ["simulation_id"], unique=False
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    # op.drop_column("simulation", "last_used")
    # op.drop_column("configuration", "last_used")
    op.drop_index(op.f("ix_memorylog_simulation_id"), table_name="memorylog")
    op.drop_table("memorylog")
    # ### end Alembic commands ###
