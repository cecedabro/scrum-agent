"""SQLAlchemy models. Every change here needs a new Alembic migration (docs/backend.md)."""

from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, String, Text, Time
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.clock import now_utc


class Base(DeclarativeBase):
    pass


class Deadline(Base):
    __tablename__ = "deadline"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    external_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now_utc
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now_utc, onupdate=now_utc
    )
