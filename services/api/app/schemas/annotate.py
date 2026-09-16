"""docs/phase-5-BUILD.md TASK 5.3 — the admin-only annotation tool at /app/annotate. Deliberately
a separate schema module from schemas/session.py's `AnnotationCreate`/`AnnotationOut` (Task
3.4e/CS-15) — that endpoint lets a user rate turns from their *own* session; this one lets an
admin annotator pull from a cross-session queue with anchor descriptors, audio and pre-labelling,
none of which the self-serve control needs or should expose.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AnnotationQueueItem(BaseModel):
    """TASK 5.3a: "the question, the answer text (PII-scrubbed version only), the audio, the
    criterion being scored, the full anchor descriptors for all five points." `pre_label_score`
    is populated only for train-split items when the caller explicitly requests pre-labelling
    (TASK 5.3d) — never for validation/test items, enforced server-side, not just by the client
    choosing not to ask.
    """

    model_config = ConfigDict(from_attributes=True)

    turn_id: UUID
    session_id: UUID
    question: str
    # Task 5.3a: "PII-scrubbed version only." Falls back to the raw transcript only when no
    # report has generated yet to produce a scrubbed version (turns.text_scrubbed is NULL until
    # then) — documented explicitly in the queue-building service, not silently.
    answer_text: str
    answer_is_scrubbed: bool
    audio_url: str | None
    audio_start_ms: int
    audio_end_ms: int
    criterion_key: str
    criterion_name: str
    anchor_descriptors: dict[str, str]
    split: str
    double_labeled: bool
    pre_label_score: int | None = None


class AnnotationSubmit(BaseModel):
    turn_id: UUID
    criterion_key: str
    score: int = Field(ge=1, le=5)
    notes: str | None = None
    # Echoes back whatever pre_label_score the queue item showed, if any — TASK 5.3d's
    # correction-rate accounting needs to know what was suggested versus what was kept, and the
    # server should not have to trust a client's claim about a value it never sent back;
    # instead the server re-derives whether this was a pre-labelled item and only accepts this
    # field as confirmation for the audit trail, not as an override of eligibility.
    pre_label_score: int | None = None


class AnnotationSubmitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    turn_id: UUID
    criterion_key: str
    round: int
    score: int
    created_at: datetime


class AnnotationProgress(BaseModel):
    dataset_revision_hash: str | None
    total_candidate_pairs: int
    labeled_pairs: int
    double_labeled_target: int
    double_labeled_with_two_annotators: int
    disagreements_pending_adjudication: int
