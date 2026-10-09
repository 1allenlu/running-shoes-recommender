"""SQLAlchemy tables. Mirrors ROADMAP.md section 5; change both together."""

import uuid
from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIM = 384  # BAAI/bge-small-en-v1.5

SHOE_CATEGORIES = ("daily", "tempo", "race", "stability", "max-cushion")
SHOE_WIDTHS = ("standard", "wide", "extra-wide")
TOE_BOXES = ("narrow", "medium", "roomy")
UPPER_VOLUMES = ("low", "medium", "high")
TASK_STATUSES = ("queued", "running", "done", "failed")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    pass


class Shoe(Base):
    __tablename__ = "shoes"
    __table_args__ = (
        UniqueConstraint("brand", "model", "version", name="uq_shoes_brand_model_version"),
        CheckConstraint(_in("category", SHOE_CATEGORIES), name="ck_shoes_category"),
        CheckConstraint(_in("toe_box", TOE_BOXES), name="ck_shoes_toe_box"),
        CheckConstraint(_in("upper_volume", UPPER_VOLUMES), name="ck_shoes_upper_volume"),
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
    widths_available: Mapped[list[str]] = mapped_column(
        ARRAY(String(16)), server_default="{standard}"
    )
    toe_box: Mapped[str | None] = mapped_column(String(16))
    upper_volume: Mapped[str | None] = mapped_column(String(16))
    heel_lock: Mapped[bool | None] = mapped_column(Boolean)
    price_usd: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))


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
    foot_profile: Mapped[dict | None] = mapped_column(JSONB)
    questionnaire: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    raw_file_path: Mapped[str] = mapped_column(Text)
    parsed_profile: Mapped[dict | None] = mapped_column(JSONB)
    parser_version: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (CheckConstraint(_in("status", TASK_STATUSES), name="ck_tasks_status"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), server_default="queued")
    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_feedback_rating"),
        CheckConstraint(_in("width", SHOE_WIDTHS), name="ck_feedback_width"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    shoe_id: Mapped[int] = mapped_column(ForeignKey("shoes.id", ondelete="CASCADE"))
    us_size: Mapped[Decimal] = mapped_column(Numeric(3, 1))
    width: Mapped[str] = mapped_column(String(16))
    rating: Mapped[int] = mapped_column(SmallInteger)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
