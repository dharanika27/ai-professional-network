"""Job loader interface and seed file implementation.

Provides:
  - JobRecord dataclass — a job record from any loader source
  - JobLoader Protocol — interface for loading job records
  - SeedJobLoader — reads from the static seeds/jobs/jobs_seed.json fixture

No imports from app.db, app.services, or app.repositories.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class JobRecord:
    """A job record from any loader source."""

    external_ref: str
    title: str
    company: str
    location: str
    employment_type: str | None
    description: str
    skills: list[str]
    seniority: str | None
    source: str  # "seed" or "api"


@runtime_checkable
class JobLoader(Protocol):
    """Interface for loading job records from any source.

    The seed implementation reads from a JSON file.
    A future API implementation would fetch from an external jobs API.
    """

    def load(self) -> list[JobRecord]:
        """Load and return all job records."""
        ...


class SeedJobLoader:
    """Loads jobs from the static seeds/jobs/jobs_seed.json fixture."""

    def __init__(self, seed_file: pathlib.Path) -> None:
        self._seed_file = seed_file

    def load(self) -> list[JobRecord]:
        """Load job records from the JSON seed file."""
        raw = json.loads(self._seed_file.read_text(encoding="utf-8"))
        records: list[JobRecord] = []
        for item in raw:
            records.append(
                JobRecord(
                    external_ref=item["external_ref"],
                    title=item["title"],
                    company=item["company"],
                    location=item["location"],
                    employment_type=item.get("employment_type"),
                    description=item["description"],
                    skills=item.get("skills", []),
                    seniority=item.get("seniority"),
                    source=item.get("source", "seed"),
                )
            )
        return records
