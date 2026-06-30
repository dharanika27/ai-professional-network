"""DB package — Layer 3a (persistence substrate).

Imports only from app/types and app/config (and SQLAlchemy/pgvector).
Never imports from app/services or app/api.
"""

from app.db.base import Base
from app.db.health import DBHealthStatus, check_db_health
from app.db.session import get_engine, get_session, get_session_factory, init_db

__all__ = [
    "Base",
    "DBHealthStatus",
    "check_db_health",
    "get_engine",
    "get_session",
    "get_session_factory",
    "init_db",
]
