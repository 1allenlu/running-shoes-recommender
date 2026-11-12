"""LastFit user-side tables: preferences, shoe history, recommendations, new feedback.

Replaces `tasks` with `recommendations`, moves the confirmed profile from `users` onto
`scans`, and turns feedback's 1-5 rating into a loved/fine/hated outcome with issue tags.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ISSUE_TAGS = (
    "toe_pressure",
    "heel_slip",
    "too_narrow",
    "too_much_volume",
    "arch_discomfort",
    "too_soft",
    "too_firm",
)
TAGS_CHECK = "issues <@ ARRAY[{}]::varchar[]".format(", ".join(repr(t) for t in ISSUE_TAGS))
RATINGS_IN = "IN ('loved', 'fine', 'hated')"


def _user_fk() -> sa.Column:
    return sa.Column(
        "user_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )


def upgrade() -> None:
    op.drop_column("users", "foot_profile")
    op.drop_column("users", "questionnaire")

    op.add_column(
        "scans",
        sa.Column(
            "raw_file_paths", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"
        ),
    )
    op.execute("UPDATE scans SET raw_file_paths = ARRAY[raw_file_path]")
    op.drop_column("scans", "raw_file_path")
    op.add_column("scans", sa.Column("confirmed_profile", postgresql.JSONB()))

    op.create_table(
        "preferences",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("weekly_km", sa.Numeric(6, 1)),
        sa.Column("goals", postgresql.ARRAY(sa.String(64)), nullable=False, server_default="{}"),
        sa.Column("surface", sa.String(16)),
        sa.Column("feel", sa.String(16)),
        sa.Column("budget_usd", sa.Numeric(8, 2)),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("feel IN ('soft', 'balanced', 'firm')", name="ck_preferences_feel"),
    )

    op.create_table(
        "shoe_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        _user_fk(),
        sa.Column("shoe_id", sa.Integer(), sa.ForeignKey("shoes.id", ondelete="SET NULL")),
        sa.Column("raw_name", sa.Text(), nullable=False),
        sa.Column("us_size", sa.Numeric(3, 1)),
        sa.Column("width", sa.String(16)),
        sa.Column("rating", sa.String(8), nullable=False),
        sa.Column("issues", postgresql.ARRAY(sa.String(32)), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"rating {RATINGS_IN}", name="ck_shoe_history_rating"),
        sa.CheckConstraint(TAGS_CHECK, name="ck_shoe_history_issues"),
    )
    op.create_index("ix_shoe_history_user_id", "shoe_history", ["user_id"])

    op.drop_table("tasks")
    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _user_fk(),
        sa.Column("task_status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("ranker_version", sa.String(32)),
        sa.Column("candidates", postgresql.JSONB()),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("error", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "task_status IN ('queued', 'running', 'done', 'failed')",
            name="ck_recommendations_task_status",
        ),
    )
    op.create_index("ix_recommendations_user_id", "recommendations", ["user_id"])

    op.drop_constraint("ck_feedback_rating", "feedback", type_="check")
    op.add_column("feedback", sa.Column("outcome", sa.String(8)))
    op.execute(
        "UPDATE feedback SET outcome = CASE WHEN rating >= 4 THEN 'loved' "
        "WHEN rating = 3 THEN 'fine' ELSE 'hated' END"
    )
    op.alter_column("feedback", "outcome", nullable=False)
    op.drop_column("feedback", "rating")
    op.add_column(
        "feedback",
        sa.Column(
            "recommendation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recommendations.id", ondelete="SET NULL"),
        ),
    )
    op.add_column("feedback", sa.Column("kept", sa.Boolean()))
    op.add_column(
        "feedback",
        sa.Column("issues", postgresql.ARRAY(sa.String(32)), nullable=False, server_default="{}"),
    )
    op.create_check_constraint("ck_feedback_outcome", "feedback", f"outcome {RATINGS_IN}")
    op.create_check_constraint("ck_feedback_issues", "feedback", TAGS_CHECK)


def downgrade() -> None:
    op.drop_constraint("ck_feedback_issues", "feedback", type_="check")
    op.drop_constraint("ck_feedback_outcome", "feedback", type_="check")
    op.drop_column("feedback", "issues")
    op.drop_column("feedback", "kept")
    op.drop_column("feedback", "recommendation_id")
    op.add_column("feedback", sa.Column("rating", sa.SmallInteger()))
    op.execute(
        "UPDATE feedback SET rating = CASE outcome WHEN 'loved' THEN 5 WHEN 'fine' THEN 3 "
        "ELSE 1 END"
    )
    op.alter_column("feedback", "rating", nullable=False)
    op.drop_column("feedback", "outcome")
    op.create_check_constraint("ck_feedback_rating", "feedback", "rating BETWEEN 1 AND 5")

    op.drop_table("recommendations")
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _user_fk(),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("error", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')", name="ck_tasks_status"
        ),
    )
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"])
    op.drop_table("shoe_history")
    op.drop_table("preferences")

    op.drop_column("scans", "confirmed_profile")
    op.add_column("scans", sa.Column("raw_file_path", sa.Text()))
    op.execute("UPDATE scans SET raw_file_path = coalesce(raw_file_paths[1], '')")
    op.alter_column("scans", "raw_file_path", nullable=False)
    op.drop_column("scans", "raw_file_paths")

    op.add_column("users", sa.Column("questionnaire", postgresql.JSONB()))
    op.add_column("users", sa.Column("foot_profile", postgresql.JSONB()))
