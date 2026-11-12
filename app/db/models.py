"""SQLAlchemy tables. Mirrors CLAUDE_CODE_PROMPT.md section 4; change both together."""

import uuid
from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIM = 384  # BAAI/bge-small-en-v1.5

SHOE_CATEGORIES = ("daily", "tempo", "race", "stability", "max-cushion")
SHOE_WIDTHS = ("standard", "wide", "extra-wide")
TOE_BOXES = ("narrow", "medium", "roomy")
UPPER_VOLUMES = ("low", "medium", "high")
UPPER_STRETCH = ("low", "medium", "high")
HEEL_COUNTERS = ("soft", "medium", "firm")
MIDSOLE_SOFTNESS = ("soft", "balanced", "firm")
TASK_STATUSES = ("queued", "running", "done", "failed")
FEELS = ("soft", "balanced", "firm")
RATINGS = ("loved", "fine", "hated")
ISSUE_TAGS = (
    "toe_pressure",
    "heel_slip",
    "too_narrow",
    "too_much_volume",
    "arch_discomfort",
    "too_soft",
    "too_firm",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _tags(column: str) -> str:
    return f"{column} <@ ARRAY[{', '.join(repr(t) for t in ISSUE_TAGS)}]::varchar[]"


class Base(DeclarativeBase):
    pass


class Shoe(Base):
    __tablename__ = "shoes"
    __table_args__ = (
        UniqueConstraint("brand", "model", "version", name="uq_shoes_brand_model_version"),
        CheckConstraint(_in("category", SHOE_CATEGORIES), name="ck_shoes_category"),
        CheckConstraint(_in("toe_box", TOE_BOXES), name="ck_shoes_toe_box"),
        CheckConstraint(_in("upper_volume", UPPER_VOLUMES), name="ck_shoes_upper_volume"),
        CheckConstraint(_in("upper_stretch", UPPER_STRETCH), name="ck_shoes_upper_stretch"),
        CheckConstraint(_in("heel_counter", HEEL_COUNTERS), name="ck_shoes_heel_counter"),
        CheckConstraint(
            _in("midsole_softness", MIDSOLE_SOFTNESS), name="ck_shoes_midsole_softness"
        ),
        CheckConstraint(
            f"widths_available <@ ARRAY[{', '.join(repr(w) for w in SHOE_WIDTHS)}]::varchar[]",
            name="ck_shoes_widths_available",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    brand: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(16))
    # Specs are nullable so unconfirmed values can stay empty (TODO) instead of guessed.
    drop_mm: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    stack_heel_mm: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    stack_forefoot_mm: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    weight_g: Mapped[int | None]
    widths_available: Mapped[list[str] | None] = mapped_column(ARRAY(String(16)))
    toe_box: Mapped[str | None] = mapped_column(String(16))
    upper_volume: Mapped[str | None] = mapped_column(String(16))
    # Heel lock eyelet (an extra lacing hole for a runner's loop): LastFit's heel_lock_eyelet.
    heel_lock: Mapped[bool | None] = mapped_column(Boolean)
    price_usd: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    # Measured widths (mm), entered by hand from brand pages; null until verified.
    toebox_width_mm: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    toebox_width_bigtoe_mm: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    forefoot_width_mm: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    heel_width_mm: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    upper_stretch: Mapped[str | None] = mapped_column(String(16))
    heel_counter: Mapped[str | None] = mapped_column(String(16))
    midsole_softness: Mapped[str | None] = mapped_column(String(16))
    stability_features: Mapped[bool | None] = mapped_column(Boolean)


class FitNote(Base):
    __tablename__ = "fit_notes"
    __table_args__ = (
        Index(
            "ix_fit_notes_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shoe_id: Mapped[int] = mapped_column(ForeignKey("shoes.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))


class SizeChart(Base):
    __tablename__ = "size_charts"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand: Mapped[str] = mapped_column(String(64), index=True)
    us_size: Mapped[Decimal] = mapped_column(Numeric(3, 1))
    length_mm_min: Mapped[Decimal] = mapped_column(Numeric(5, 1))
    length_mm_max: Mapped[Decimal] = mapped_column(Numeric(5, 1))
    # Added to the size when this brand runs small (+0.5) or large (-0.5).
    size_offset: Mapped[Decimal] = mapped_column(Numeric(3, 1), server_default="0")
    sizing_note: Mapped[str | None] = mapped_column(Text)


class Offer(Base):
    """One buyable pair at one retailer. "That exact pair" = shoe_id + us_size + width."""

    __tablename__ = "offers"
    __table_args__ = (
        UniqueConstraint(
            "shoe_id", "retailer", "us_size", "width", name="uq_offers_shoe_retailer_size_width"
        ),
        CheckConstraint(_in("width", SHOE_WIDTHS), name="ck_offers_width"),
        Index("ix_offers_pair", "shoe_id", "us_size", "width"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shoe_id: Mapped[int] = mapped_column(ForeignKey("shoes.id", ondelete="CASCADE"))
    retailer: Mapped[str] = mapped_column(String(64))
    us_size: Mapped[Decimal] = mapped_column(Numeric(3, 1))
    width: Mapped[str] = mapped_column(String(16))
    price_usd: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    in_stock: Mapped[bool] = mapped_column(Boolean, server_default="true")
    affiliate_url: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Scan(Base):
    """One uploaded report. Only `confirmed_profile` is used for ranking."""

    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    raw_file_paths: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    parsed_profile: Mapped[dict | None] = mapped_column(JSONB)  # null for manual entry
    confirmed_profile: Mapped[dict | None] = mapped_column(JSONB)
    parser_version: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Preferences(Base):
    __tablename__ = "preferences"
    __table_args__ = (CheckConstraint(_in("feel", FEELS), name="ck_preferences_feel"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    weekly_km: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    goals: Mapped[list[str]] = mapped_column(ARRAY(String(64)), server_default="{}")
    surface: Mapped[str | None] = mapped_column(String(16))
    feel: Mapped[str | None] = mapped_column(String(16))
    budget_usd: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ShoeHistory(Base):
    """A shoe the runner has run in. Training data for stages 2 and 3: tags, not free text."""

    __tablename__ = "shoe_history"
    __table_args__ = (
        CheckConstraint(_in("rating", RATINGS), name="ck_shoe_history_rating"),
        CheckConstraint(_tags("issues"), name="ck_shoe_history_issues"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    shoe_id: Mapped[int | None] = mapped_column(ForeignKey("shoes.id", ondelete="SET NULL"))
    raw_name: Mapped[str] = mapped_column(Text)
    us_size: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    width: Mapped[str | None] = mapped_column(String(16))
    rating: Mapped[str] = mapped_column(String(8))
    issues: Mapped[list[str]] = mapped_column(ARRAY(String(32)), server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Recommendation(Base):
    """One /recommend run: the ranker's full candidate list and the result shown."""

    __tablename__ = "recommendations"
    __table_args__ = (
        CheckConstraint(_in("task_status", TASK_STATUSES), name="ck_recommendations_task_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    task_status: Mapped[str] = mapped_column(String(16), server_default="queued")
    ranker_version: Mapped[str | None] = mapped_column(String(32))
    candidates: Mapped[list | None] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Feedback(Base):
    """How a recommended shoe worked out, reported after a few runs."""

    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint(_in("outcome", RATINGS), name="ck_feedback_outcome"),
        CheckConstraint(_in("width", SHOE_WIDTHS), name="ck_feedback_width"),
        CheckConstraint(_tags("issues"), name="ck_feedback_issues"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recommendations.id", ondelete="SET NULL")
    )
    shoe_id: Mapped[int] = mapped_column(ForeignKey("shoes.id", ondelete="CASCADE"))
    us_size: Mapped[Decimal] = mapped_column(Numeric(3, 1))
    width: Mapped[str] = mapped_column(String(16))
    outcome: Mapped[str] = mapped_column(String(8))
    kept: Mapped[bool | None] = mapped_column(Boolean)
    issues: Mapped[list[str]] = mapped_column(ARRAY(String(32)), server_default="{}")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
