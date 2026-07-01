#!/usr/bin/env python3
"""Job seeding script — loads jobs_seed.json, embeds descriptions, upserts to DB.

Run from the backend/ directory:
    uv run python scripts/seed_jobs.py

Requires DATABASE_URL and JWT_SECRET in environment or .env file.
Seeding is idempotent: re-running does not duplicate rows (keyed on external_ref).
"""

from __future__ import annotations

import logging
import pathlib
import sys

# Ensure src/ and project root are on the path when run as a script
_HERE = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(_HERE / "src"))
sys.path.insert(1, str(_HERE))

from app.config.settings import get_settings  # noqa: E402
from app.db.session import get_session_factory, init_db  # noqa: E402
from app.repositories.job_repository import get_job_count, upsert_job  # noqa: E402
from app.services.ai.embedding_provider import get_embedding_provider  # noqa: E402
from seeds.loaders.job_loader import SeedJobLoader  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

SEED_FILE = _HERE / "seeds" / "jobs" / "jobs_seed.json"

# Batch size for embedding (controls memory usage)
EMBED_BATCH_SIZE = 32


def main() -> None:
    """Initialize DB, embed job descriptions, upsert rows, commit, and report."""
    settings = get_settings()
    init_db(settings.database_url)

    session_factory = get_session_factory()
    provider = get_embedding_provider(model_name=settings.embedding_model)
    loader = SeedJobLoader(SEED_FILE)

    logger.info("Loading job records from seed file", extra={"seed_file": str(SEED_FILE)})
    records = loader.load()
    total_records = len(records)
    logger.info("Loaded %d job records", total_records)

    session = session_factory()

    try:
        for batch_start in range(0, total_records, EMBED_BATCH_SIZE):
            batch = records[batch_start : batch_start + EMBED_BATCH_SIZE]

            # Embed all descriptions in the batch at once
            descriptions = [r.description for r in batch]
            embeddings = provider.embed_batch(descriptions)

            for record, embedding in zip(batch, embeddings, strict=True):
                upsert_job(session=session, record=record, embedding=embedding)

            batch_end = min(batch_start + EMBED_BATCH_SIZE, total_records)
            if batch_start % (EMBED_BATCH_SIZE * 5) == 0 or batch_end == total_records:
                logger.info(
                    "Progress: %d/%d records processed",
                    batch_end,
                    total_records,
                )

        session.commit()
        final_count = get_job_count(session)
        logger.info("Seed complete. Final job count in DB: %d", final_count)

    except Exception:
        session.rollback()
        logger.exception("Seed failed, rolling back")
        sys.exit(1)
    finally:
        session.close()

    print(f"\nJob seeding complete — {total_records} records processed")
    print(f"Total jobs in database: {final_count}")
    print("(Re-seeding is idempotent — no duplicates created)")


if __name__ == "__main__":
    main()
