#!/usr/bin/env python3
"""KB ingestion script — reads kb/*.md, chunks, embeds, and upserts to DB.

Run from the backend/ directory:
    uv run python scripts/ingest_kb.py

Requires DATABASE_URL and JWT_SECRET in environment or .env file.
"""

from __future__ import annotations

import logging
import pathlib
import sys

# Ensure src/ is on the path when run as a script
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from app.config.settings import get_settings
from app.db.session import get_session_factory, init_db
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.ai.embedding_provider import get_embedding_provider
from app.services.ai.kb_ingestion import ingest_kb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

KB_DIR = pathlib.Path(__file__).parent.parent / "kb"


def main() -> None:
    """Initialize DB, run ingestion, commit, and report results."""
    settings = get_settings()
    init_db(settings.database_url)

    session_factory = get_session_factory()
    provider = get_embedding_provider(model_name=settings.embedding_model)
    knowledge_repo = KnowledgeRepository()

    session = session_factory()
    try:
        results = ingest_kb(
            session=session,
            provider=provider,
            kb_dir=KB_DIR,
            knowledge_repo=knowledge_repo,
        )
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Ingestion failed, rolling back")
        sys.exit(1)
    finally:
        session.close()

    total = sum(results.values())
    print(f"\nKB ingestion complete — {total} chunks inserted total")
    print("-" * 50)
    for filename, count in sorted(results.items()):
        status = f"{count} inserted" if count > 0 else "skipped (already exists)"
        print(f"  {filename:<35} {status}")
    print("-" * 50)


if __name__ == "__main__":
    main()
