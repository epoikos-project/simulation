"""init

Revision ID: b51835aeed6c
Revises:
Create Date: 2025-07-04 23:38:26.524497

"""

import sqlalchemy as sa
import sqlmodel  # New
from alembic import op

# revision identifiers, used by Alembic.
revision = "b51835aeed6c"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "agent",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("collection_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("simulation_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "harvesting_resource_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column(
            "participating_in_plan_id",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("model", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("energy_level", sa.Float(), nullable=False),
        sa.Column("last_action", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("last_error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("hunger", sa.Float(), nullable=False),
        sa.Column("x_coord", sa.Integer(), nullable=False),
        sa.Column("y_coord", sa.Integer(), nullable=False),
        sa.Column("visibility_range", sa.Integer(), nullable=False),
        sa.Column("range_per_move", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "configuration",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("agents", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("settings", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "plan",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("owner_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("goal", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("total_expected_payoff", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_plan_owner_id"), "plan", ["owner_id"], unique=False)
    op.create_table(
        "simulation",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "collection_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False
        ),
        sa.Column("running", sa.Boolean(), nullable=False),
        sa.Column("tick", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "conversation",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("simulation_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("agent_a_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("agent_b_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("tick", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_conversation_agent_a_id"), "conversation", ["agent_a_id"], unique=False
    )
    op.create_index(
        op.f("ix_conversation_agent_b_id"), "conversation", ["agent_b_id"], unique=False
    )
    op.create_index(
        op.f("ix_conversation_simulation_id"),
        "conversation",
        ["simulation_id"],
        unique=False,
    )
    op.create_table(
        "relationship",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("agent_a_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("agent_b_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("total_sentiment", sa.Float(), nullable=False),
        sa.Column("update_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "world",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("simulation_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("size_x", sa.Integer(), nullable=False),
        sa.Column("size_y", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "message",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("agent_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("conversation_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("serial_number", sa.Integer(), nullable=False),
        sa.Column("content", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("tick", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_message_agent_id"), "message", ["agent_id"], unique=False)
    op.create_index(
        op.f("ix_message_conversation_id"), "message", ["conversation_id"], unique=False
    )
    op.create_index(
        op.f("ix_message_serial_number"), "message", ["serial_number"], unique=False
    )
    op.create_index(op.f("ix_message_tick"), "message", ["tick"], unique=False)
    op.create_table(
        "region",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("simulation_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("world_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("x_1", sa.Integer(), nullable=False),
        sa.Column("y_1", sa.Integer(), nullable=False),
        sa.Column("x_2", sa.Integer(), nullable=False),
        sa.Column("y_2", sa.Integer(), nullable=False),
        sa.Column("speed_mltply", sa.Float(), nullable=False),
        sa.Column("resource_density", sa.Float(), nullable=False),
        sa.Column("resource_cluster", sa.Integer(), nullable=False),
        sa.Column("region_energy_cost", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "resource",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("simulation_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("world_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("region_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("x_coord", sa.Integer(), nullable=False),
        sa.Column("y_coord", sa.Integer(), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("energy_yield", sa.Integer(), nullable=False),
        sa.Column("mining_time", sa.Integer(), nullable=False),
        sa.Column("regrow_time", sa.Integer(), nullable=False),
        sa.Column("harvesting_area", sa.Integer(), nullable=False),
        sa.Column("required_agents", sa.Integer(), nullable=False),
        sa.Column("energy_yield_var", sa.Float(), nullable=False),
        sa.Column("regrow_var", sa.Float(), nullable=False),
        sa.Column("being_harvested", sa.Boolean(), nullable=False),
        sa.Column("start_harvest", sa.Integer(), nullable=False),
        sa.Column("time_harvest", sa.Integer(), nullable=False),
        sa.Column("last_harvest", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "task",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("plan_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("target_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("worker_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("payoff", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_plan_id"), "task", ["plan_id"], unique=False)
    op.create_index(op.f("ix_task_worker_id"), "task", ["worker_id"], unique=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f("ix_task_worker_id"), table_name="task")
    op.drop_index(op.f("ix_task_plan_id"), table_name="task")
    op.drop_table("task")
    op.drop_table("resource")
    op.drop_table("region")
    op.drop_index(op.f("ix_message_tick"), table_name="message")
    op.drop_index(op.f("ix_message_serial_number"), table_name="message")
    op.drop_index(op.f("ix_message_conversation_id"), table_name="message")
    op.drop_index(op.f("ix_message_agent_id"), table_name="message")
    op.drop_table("message")
    op.drop_table("world")
    op.drop_table("relationship")
    op.drop_index(op.f("ix_conversation_simulation_id"), table_name="conversation")
    op.drop_index(op.f("ix_conversation_agent_b_id"), table_name="conversation")
    op.drop_index(op.f("ix_conversation_agent_a_id"), table_name="conversation")
    op.drop_table("conversation")
    op.drop_table("simulation")
    op.drop_index(op.f("ix_plan_owner_id"), table_name="plan")
    op.drop_table("plan")
    op.drop_table("configuration")
    op.drop_table("agent")
    # ### end Alembic commands ###
