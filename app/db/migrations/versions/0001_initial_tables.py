"""initial tables

Revision ID: 0001
Revises:
Create Date: 2026-10-09

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "shoes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("brand", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("drop_mm", sa.Numeric(4, 1)),
        sa.Column("stack_heel_mm", sa.Numeric(4, 1)),
        sa.Column("stack_forefoot_mm", sa.Numeric(4, 1)),
        sa.Column("weight_g", sa.Integer()),
        sa.Column("widths_available", postgresql.ARRAY(sa.String(16))),
        sa.Column("toe_box", sa.String(16)),
        sa.Column("upper_volume", sa.String(16)),
        sa.Column("heel_lock", sa.Boolean()),
        sa.Column("price_usd", sa.Numeric(8, 2)),
        sa.UniqueConstraint("brand", "model", "version", name="uq_shoes_brand_model_version"),
        sa.CheckConstraint(
            "category IN ('daily', 'tempo', 'race', 'stability', 'max-cushion')",
            name="ck_shoes_category",
        ),
        sa.CheckConstraint("toe_box IN ('narrow', 'medium', 'roomy')", name="ck_shoes_toe_box"),
        sa.CheckConstraint(
            "upper_volume IN ('low', 'medium', 'high')", name="ck_shoes_upper_volume"
        ),
        sa.CheckConstraint(
            "widths_available <@ ARRAY['standard', 'wide', 'extra-wide']::varchar[]",
            name="ck_shoes_widths_available",
        ),
    )

    op.create_table(
        "fit_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "shoe_id",
            sa.Integer(),
            sa.ForeignKey("shoes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(384)),
    )
    op.create_index("ix_fit_notes_shoe_id", "fit_notes", ["shoe_id"])
    op.create_index(
        "ix_fit_notes_embedding_hnsw",
        "fit_notes",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "size_charts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("brand", sa.String(64), nullable=False),
        sa.Column("us_size", sa.Numeric(3, 1), nullable=False),
        sa.Column("length_mm_min", sa.Numeric(5, 1), nullable=False),
        sa.Column("length_mm_max", sa.Numeric(5, 1), nullable=False),
        sa.Column("sizing_note", sa.Text()),
    )
    op.create_index("ix_size_charts_brand", "size_charts", ["brand"])

    op.create_table(
        "offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "shoe_id",
            sa.Integer(),
            sa.ForeignKey("shoes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("retailer", sa.String(64), nullable=False),
        sa.Column("us_size", sa.Numeric(3, 1), nullable=False),
        sa.Column("width", sa.String(16), nullable=False),
        sa.Column("price_usd", sa.Numeric(8, 2)),
        sa.Column("in_stock", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("affiliate_url", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "shoe_id", "retailer", "us_size", "width", name="uq_offers_shoe_retailer_size_width"
        ),
        sa.CheckConstraint("width IN ('standard', 'wide', 'extra-wide')", name="ck_offers_width"),
    )
    op.create_index("ix_offers_pair", "offers", ["shoe_id", "us_size", "width"])

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("foot_profile", postgresql.JSONB()),
        sa.Column("questionnaire", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "scans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("raw_file_path", sa.Text(), nullable=False),
        sa.Column("parsed_profile", postgresql.JSONB()),
        sa.Column("parser_version", sa.String(32)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_scans_user_id", "scans", ["user_id"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("error", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')", name="ck_tasks_status"
        ),
    )
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"])

    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "shoe_id",
            sa.Integer(),
            sa.ForeignKey("shoes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("us_size", sa.Numeric(3, 1), nullable=False),
        sa.Column("width", sa.String(16), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_feedback_rating"),
        sa.CheckConstraint("width IN ('standard', 'wide', 'extra-wide')", name="ck_feedback_width"),
    )
    op.create_index("ix_feedback_user_id", "feedback", ["user_id"])


def downgrade() -> None:
    for table in (
        "feedback",
        "tasks",
        "scans",
        "users",
        "offers",
        "size_charts",
        "fit_notes",
        "shoes",
    ):
        op.drop_table(table)
