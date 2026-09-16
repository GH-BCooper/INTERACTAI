from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PromoteRequest(BaseModel):
    candidate_version_id: UUID


class RollbackRequest(BaseModel):
    target_version_id: UUID


class ModelVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    name: str
    base_model: str
    status: str
    seed_count: int
    dataset_revision_hash: str | None
