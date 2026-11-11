"""SQLAlchemy models. Every change here needs a new Alembic migration (docs/backend.md)."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
