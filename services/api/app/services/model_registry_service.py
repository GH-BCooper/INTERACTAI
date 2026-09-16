"""docs/phase-5-BUILD.md TASK 5.5c — the model registry. `model_versions.status` moves
`training -> candidate -> active -> retired`; the partial unique index on `(role) WHERE
status='active'` (migration e5f6a7b8c9d0) is the actual guarantee, this module is just the one
place that's allowed to change status, so every promotion/rollback goes through the same
kappa-comparison rule.
"""

from __future__ import annotations

import uuid as std_uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import NotFoundError, ValidationAppError
from ..models import DeploymentEvent, EvalRun, ModelVersion


class PromotionRejectedError(ValidationAppError):
    """Distinct from a generic validation error so a caller (or the eval harness's own CLI
    output) can tell "the request was malformed" apart from "the request was well-formed but the
    candidate simply isn't good enough yet" — the latter is an expected, common outcome, not a
    bug."""


async def _seed_qwks(db: AsyncSession, model_version_id: std_uuid.UUID) -> list[float]:
    """TASK 5.5's own methodology rule: only *published* test-split rows count — an
    unpublished run (one that never touched --publish) has no standing in a promotion decision,
    matching TASK 5.5b's "the harness must refuse to evaluate on the reporting split unless
    explicitly flagged --publish" — a promotion decision is exactly the kind of access that flag
    exists to gate."""
    result = await db.execute(
        select(EvalRun.qwk).where(
            EvalRun.model_version_id == model_version_id,
            EvalRun.split == "test",
            EvalRun.published.is_(True),
            EvalRun.qwk.is_not(None),
        )
    )
    return [row[0] for row in result.all()]


async def get_active(db: AsyncSession, role: str) -> ModelVersion | None:
    result = await db.execute(
        select(ModelVersion).where(ModelVersion.role == role, ModelVersion.status == "active")
    )
    return result.scalar_one_or_none()


async def promote(
    db: AsyncSession, *, candidate_version_id: std_uuid.UUID, min_seeds: int = 3
) -> ModelVersion:
    """TASK 5.5c: "Promotion to active requires beating the current active version on held-out
    kappa across all three seeds — not on one lucky run." Every one of the candidate's published
    test-split seed kappas must individually exceed the current active version's own test kappa;
    if any single seed falls short, the whole promotion is rejected (that's the "not on one
    lucky run" guarantee — an average that happens to clear the bar isn't enough).
    """
    candidate = await db.get(ModelVersion, candidate_version_id)
    if candidate is None:
        raise NotFoundError("Candidate model version not found.")
    if candidate.status not in ("candidate", "training"):
        raise PromotionRejectedError(
            f"Candidate has status {candidate.status!r}; only 'candidate' or 'training' "
            "versions may be promoted."
        )

    candidate_qwks = await _seed_qwks(db, candidate.id)
    if len(candidate_qwks) < min_seeds:
        raise PromotionRejectedError(
            f"Candidate has {len(candidate_qwks)} published test-split seed(s), needs "
            f'>= {min_seeds} (docs/phase-5-BUILD.md TASK 5.4: "Three seeds per configuration, '
            'always").'
        )

    current_active = await get_active(db, candidate.role)
    if current_active is not None:
        active_qwks = await _seed_qwks(db, current_active.id)
        active_reference_qwk = max(active_qwks) if active_qwks else float("-inf")
        losing_seeds = [q for q in candidate_qwks if q <= active_reference_qwk]
        if losing_seeds:
            raise PromotionRejectedError(
                f"Candidate does not beat the current active version "
                f"({active_reference_qwk:.4f} qwk) on all seeds - "
                f"{len(losing_seeds)}/{len(candidate_qwks)} seed(s) did not clear it."
            )
        current_active.status = "retired"

    candidate.status = "active"
    db.add(
        DeploymentEvent(
            kind="model_promoted",
            label=f"{candidate.role}: {candidate.name}",
            model_version_id=candidate.id,
        )
    )
    await db.flush()
    return candidate


async def rollback(db: AsyncSession, *, target_version_id: std_uuid.UUID) -> ModelVersion:
    """TASK 5.5c: "Rollback is a status change, not a redeploy." No kappa comparison — an
    operator override for exactly the situation where the numbers said promote but production
    behaviour said otherwise.
    """
    target = await db.get(ModelVersion, target_version_id)
    if target is None:
        raise NotFoundError("Target model version not found.")
    if target.status not in ("retired", "candidate"):
        raise ValidationAppError(
            f"Target has status {target.status!r}; only 'retired' or 'candidate' versions can "
            "be rolled back to."
        )

    current_active = await get_active(db, target.role)
    if current_active is not None and current_active.id != target.id:
        current_active.status = "retired"

    target.status = "active"
    db.add(
        DeploymentEvent(
            kind="model_rolled_back",
            label=f"{target.role}: rollback to {target.name}",
            model_version_id=target.id,
        )
    )
    await db.flush()
    return target


async def register_dataset_revision_summary(db: AsyncSession, role: str) -> dict[str, object]:
    """Not a Task 5.5c requirement on its own — a small read-only convenience the frontend/CLI
    can use to show "what's active and what did it score" without hand-assembling the join."""
    active = await get_active(db, role)
    if active is None:
        return {"role": role, "active": None}
    seed_qwks = await _seed_qwks(db, active.id)
    return {
        "role": role,
        "active": {
            "id": str(active.id),
            "name": active.name,
            "base_model": active.base_model,
            "dataset_revision_hash": active.dataset_revision_hash,
            "seed_qwks": seed_qwks,
            "mean_qwk": (sum(seed_qwks) / len(seed_qwks)) if seed_qwks else None,
        },
    }


async def count_versions_by_role(db: AsyncSession, role: str) -> int:
    result = await db.execute(
        select(func.count()).select_from(ModelVersion).where(ModelVersion.role == role)
    )
    return result.scalar_one()
