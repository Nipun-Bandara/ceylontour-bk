"""Initial schema: the seven tables in plan.md section 8.

Plain lat/lon float columns, no PostGIS. 15 to 20 fixed markers do not need it
(plan.md section 9, cut 2).

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "destinations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("district", sa.String(length=80), nullable=False),
        sa.Column("region", sa.String(length=80), nullable=False),
        sa.Column("landscape_type", sa.String(length=80), nullable=False),
        sa.Column("activities", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("cost_band", sa.String(length=40), nullable=False),
        sa.Column("typical_days", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_destinations_region", "destinations", ["region"])

    op.create_table(
        "destination_factors",
        sa.Column("destination_id", sa.Integer(), nullable=False),
        sa.Column("environmental", sa.Float(), nullable=False),
        sa.Column("community", sa.Float(), nullable=False),
        sa.Column("crowd", sa.Float(), nullable=False),
        sa.Column("infrastructure", sa.Float(), nullable=False),
        sa.Column("suitability", sa.Float(), nullable=False),
        # Not optional. These power the confidence labels the proposal promised.
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(
            ["destination_id"], ["destinations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("destination_id"),
    )

    op.create_table(
        "region_pressure_history",
        sa.Column("region", sa.String(length=80), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("occupancy_rate", sa.Float(), nullable=False),
        sa.Column("arrivals", sa.Integer(), nullable=False),
        sa.Column("guest_nights", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("region", "year", "month"),
    )

    op.create_table(
        "pressure_forecast",
        sa.Column("region", sa.String(length=80), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(length=40), nullable=False),
        sa.Column("predicted_pressure", sa.Float(), nullable=False),
        sa.Column("band", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("region", "month", "model_version"),
    )

    op.create_table(
        "index_weights",
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("factor", sa.String(length=40), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("version", "factor"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "search_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("params_json", postgresql.JSONB(), nullable=False),
        sa.Column("results_json", postgresql.JSONB(), nullable=False),
        sa.Column("accepted_destination_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["accepted_destination_id"], ["destinations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("search_log")
    op.drop_table("users")
    op.drop_table("index_weights")
    op.drop_table("pressure_forecast")
    op.drop_table("region_pressure_history")
    op.drop_table("destination_factors")
    op.drop_index("ix_destinations_region", table_name="destinations")
    op.drop_table("destinations")
