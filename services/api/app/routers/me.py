from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Query, Response

from ..core.deps import CurrentUser, DbSession
from ..models import ProviderCredential
from ..schemas.progress import DashboardOut, ProgressOut, ScenarioProgressOut
from ..schemas.user import (
    ConnectionTestStatus,
    MeOut,
    ModelsSettingsOut,
    ModelsSettingsUpdate,
    PrivacySettingsOut,
    PrivacySettingsUpdate,
    ProfileOut,
    ProfileUpdate,
    ProviderConnectionTestOut,
    ProviderCredentialCreate,
    ProviderCredentialOut,
    ProviderName,
    UserOut,
)
from ..services import progress_service, session_service, user_service

router = APIRouter(tags=["me"])


def _provider_credential_out(credential: ProviderCredential) -> ProviderCredentialOut:
    return ProviderCredentialOut(
        provider=cast(ProviderName, credential.provider),
        has_key=True,
        last_test_status=cast(ConnectionTestStatus, credential.last_test_status),
        last_tested_at=credential.last_tested_at,
    )


@router.get("/me", response_model=MeOut)
async def get_me(user: CurrentUser, db: DbSession) -> MeOut:
    profile = await user_service.get_profile(db, user.id)
    minutes = await session_service.practice_minutes_this_week(db, user.id)
    return MeOut(
        user=UserOut.model_validate(user),
        profile=ProfileOut.model_validate(profile) if profile else None,
        practice_minutes_this_week=minutes,
    )


@router.patch("/me/profile", response_model=ProfileOut)
async def patch_profile(body: ProfileUpdate, user: CurrentUser, db: DbSession) -> ProfileOut:
    profile = await user_service.update_profile(
        db,
        user.id,
        resume_text=body.resume_text,
        target_role=body.target_role,
        clear_resume=body.clear_resume,
        goal=body.goal,
        experience_level=body.experience_level,
        focus_areas=body.focus_areas,
        captions_default=body.captions_default,
        speaking_rate=body.speaking_rate,
        noise_suppression=body.noise_suppression,
        echo_cancellation=body.echo_cancellation,
    )
    await db.commit()
    return ProfileOut.model_validate(profile)


@router.post("/me/onboarding/complete", response_model=UserOut)
async def complete_onboarding(user: CurrentUser, db: DbSession) -> UserOut:
    """Task 4.3: onboarding step 4 calls this the moment the first session launches — "Onboarding
    ends inside the practice room, not on a dashboard." Idempotent: a user who is already
    onboarded gets the same `onboarded_at` back, never a second timestamp."""
    updated = await user_service.complete_onboarding(db, user.id)
    await db.commit()
    return UserOut.model_validate(updated)


@router.get("/me/privacy", response_model=PrivacySettingsOut)
async def get_privacy_settings(user: CurrentUser) -> PrivacySettingsOut:
    return PrivacySettingsOut(
        training_consent=user.training_consent, audio_retention_days=user.audio_retention_days
    )


@router.patch("/me/privacy", response_model=PrivacySettingsOut)
async def patch_privacy_settings(
    body: PrivacySettingsUpdate, user: CurrentUser, db: DbSession
) -> PrivacySettingsOut:
    """AS-03/AS-04. Turning `training_consent` off cascades immediately — see
    services/user_service.py::update_privacy_settings."""
    updated = await user_service.update_privacy_settings(
        db,
        user.id,
        training_consent=body.training_consent,
        audio_retention_days=body.audio_retention_days,
    )
    await db.commit()
    return PrivacySettingsOut(
        training_consent=updated.training_consent,
        audio_retention_days=updated.audio_retention_days,
    )


@router.get("/me/models", response_model=ModelsSettingsOut)
async def get_models_settings(user: CurrentUser) -> ModelsSettingsOut:
    return ModelsSettingsOut(prefer_local_models=user.prefer_local_models)


@router.patch("/me/models", response_model=ModelsSettingsOut)
async def patch_models_settings(
    body: ModelsSettingsUpdate, user: CurrentUser, db: DbSession
) -> ModelsSettingsOut:
    if body.prefer_local_models is not None:
        user.prefer_local_models = body.prefer_local_models
        await db.commit()
    return ModelsSettingsOut(prefer_local_models=user.prefer_local_models)


@router.get("/me/providers", response_model=list[ProviderCredentialOut])
async def list_providers(user: CurrentUser, db: DbSession) -> list[ProviderCredentialOut]:
    credentials = await user_service.list_provider_credentials(db, user.id)
    return [_provider_credential_out(c) for c in credentials]


@router.put("/me/providers/{provider}", response_model=ProviderCredentialOut, status_code=201)
async def upsert_provider(
    provider: ProviderName, body: ProviderCredentialCreate, user: CurrentUser, db: DbSession
) -> ProviderCredentialOut:
    credential = await user_service.upsert_provider_credential(
        db, user.id, provider=provider, api_key=body.api_key
    )
    await db.commit()
    return _provider_credential_out(credential)


@router.delete("/me/providers/{provider}", status_code=204)
async def delete_provider(provider: ProviderName, user: CurrentUser, db: DbSession) -> Response:
    await user_service.delete_provider_credential(db, user.id, provider)
    await db.commit()
    return Response(status_code=204)


@router.post("/me/providers/{provider}/test", response_model=ProviderConnectionTestOut)
async def test_provider(
    provider: ProviderName, user: CurrentUser, db: DbSession
) -> ProviderConnectionTestOut:
    """Task 4.4: "a connection test per provider... reports success and failure accurately" —
    a real call against the provider, not a format check (services/user_service.py)."""
    success, message = await user_service.test_provider_connection(db, user.id, provider)
    await db.commit()
    return ProviderConnectionTestOut(
        provider=provider,
        success=success,
        message=message,
        tested_at=datetime.now(UTC),
    )


@router.get("/me/export")
async def export_me(user: CurrentUser, db: DbSession) -> dict[str, object]:
    """Task 4.4: "Export produces a JSON archive of profile, sessions, transcripts and scores.\""""
    return await user_service.export_user_data(db, user.id)


@router.get("/me/dashboard", response_model=DashboardOut)
async def get_dashboard(user: CurrentUser, db: DbSession) -> DashboardOut:
    return await progress_service.get_dashboard(db, user)


@router.get("/me/progress", response_model=ProgressOut)
async def get_progress(
    user: CurrentUser, db: DbSession, family: Annotated[str | None, Query()] = None
) -> ProgressOut:
    return await progress_service.get_progress(db, user, family)


@router.get("/me/scenario-progress", response_model=dict[str, ScenarioProgressOut])
async def get_scenario_progress(user: CurrentUser, db: DbSession) -> dict[str, ScenarioProgressOut]:
    """Task 4.2's scenario library card: "the user's own best score if attempted." Keyed by
    scenario id (stringified — Pydantic dict response models need string keys)."""
    raw = await progress_service.get_scenario_progress(db, user)
    return {str(scenario_id): progress for scenario_id, progress in raw.items()}


@router.delete("/me", status_code=204)
async def delete_me(user: CurrentUser, db: DbSession) -> Response:
    """AS-05 — full deletion including object storage. See services/user_service.py."""
    await user_service.delete_user_and_all_data(db, user.id)
    await db.commit()
    return Response(status_code=204)
