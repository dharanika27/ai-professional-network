"""SQLAlchemy declarative base and shared metadata.

All ORM model classes inherit from Base. Alembic uses Base.metadata
as its target_metadata for autogenerate.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    pass
