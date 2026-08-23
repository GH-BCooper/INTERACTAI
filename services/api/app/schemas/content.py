from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PersonaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    archetype: str
    temperament: str
    voice_id: str
    brief: str


class VoicePreviewTokenOut(BaseModel):
    """Task 4.2: scopes a browser call directly to realtime's `POST /synthesize-preview` — a
    pre-synthesised sample, without starting a session."""

    token: str
    expires_in: int
    voice_id: str


class ScenarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    family: str
    difficulty: str
    title: str
    brief: str
    opening_strategy: str
    duration_minutes: int
    tags: list[str]
    persona_id: UUID | None
    rubric_id: UUID | None


class RubricCriterionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    name: str
    description: str
    display_order: int
    anchor_descriptors: dict[str, str]


class RubricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    description: str
    criteria: list[RubricCriterionOut] = []


class RubricSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    description: str
