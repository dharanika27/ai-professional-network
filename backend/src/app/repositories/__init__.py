"""Repositories package — Layer 3b (data access).

Each repository module provides pure data-access functions or classes
operating on an injected SQLAlchemy Session. No business logic, no HTTP,
no commit/rollback/close calls. Transaction boundaries are owned by the caller.
"""

from app.repositories import ai_log_repository
from app.repositories.ai_log_repository import log_request
from app.repositories.job_repository import (
    get_job_by_id,
    get_job_count,
    retrieve_top_jobs,
    upsert_job,
)
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.profile_repository import (
    ProfileUpdateData,
    compute_completion_percentage,
    get_profile_by_user_id,
    update_profile,
)
from app.repositories.refresh_token_repository import (
    is_refresh_token_valid,
    revoke_refresh_token,
    store_refresh_token,
)
from app.repositories.resume_repository import (
    FileTooLargeError,
    InvalidMimeTypeError,
    delete_resume,
    get_resume_by_hash,
    get_resume_by_id,
    save_resume,
)
from app.repositories.user_repository import (
    DuplicateEmailError,
    create_user,
    get_user_by_email,
    get_user_by_id,
)

__all__ = [
    # ai_log_repository
    "ai_log_repository",
    "log_request",
    # user_repository
    "DuplicateEmailError",
    "create_user",
    "get_user_by_email",
    "get_user_by_id",
    # refresh_token_repository
    "store_refresh_token",
    "revoke_refresh_token",
    "is_refresh_token_valid",
    # profile_repository
    "ProfileUpdateData",
    "compute_completion_percentage",
    "get_profile_by_user_id",
    "update_profile",
    # resume_repository
    "InvalidMimeTypeError",
    "FileTooLargeError",
    "save_resume",
    "delete_resume",
    "get_resume_by_hash",
    "get_resume_by_id",
    # knowledge_repository
    "KnowledgeRepository",
    # job_repository
    "upsert_job",
    "retrieve_top_jobs",
    "get_job_by_id",
    "get_job_count",
]
