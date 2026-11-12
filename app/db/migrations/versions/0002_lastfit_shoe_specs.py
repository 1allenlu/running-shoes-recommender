"""LastFit shoe specs for the stage 1 fit scorer, and per-row size offsets.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MM_COLUMNS = ("toebox_width_mm", "toebox_width_bigtoe_mm", "forefoot_width_mm", "heel_width_mm")
_LEVEL_CHECKS = {
    "upper_stretch": ("low", "medium", "high"),
    "heel_counter": ("soft", "medium", "firm"),
    "midsole_softness": ("soft", "balanced", "firm"),
}


def upgrade() -> None:
    for name in _MM_COLUMNS:
        op.add_column("shoes", sa.Column(name, sa.Numeric(4, 1)))
    for name, values in _LEVEL_CHECKS.items():
        op.add_column("shoes", sa.Column(name, sa.String(16)))
        allowed = ", ".join(repr(v) for v in values)
        op.create_check_constraint(f"ck_shoes_{name}", "shoes", f"{name} IN ({allowed})")
    op.add_column("shoes", sa.Column("stability_features", sa.Boolean()))
    op.add_column(
        "size_charts",
        sa.Column("size_offset", sa.Numeric(3, 1), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("size_charts", "size_offset")
    op.drop_column("shoes", "stability_features")
    for name in _LEVEL_CHECKS:
        op.drop_constraint(f"ck_shoes_{name}", "shoes", type_="check")
        op.drop_column("shoes", name)
    for name in _MM_COLUMNS:
        op.drop_column("shoes", name)
