from __future__ import annotations

from fastapi import APIRouter, Response

from ..core.deps import CurrentUser, DbSession
from ..schemas.user import MeOut, ProfileOut, ProfileUpdate, UserOut
from ..services import user_service

router = APIRouter(tags=["me"])


@router.get("/me", response_model=MeOut)
async def get_me(user: CurrentUser, db: DbSession) -> MeOut:
    profile = await user_service.get_profile(db, user.id)
    return MeOut(
        user=UserOut.model_validate(user),
        profile=ProfileOut.model_validate(profile) if profile else None,
    )


@router.patch("/me/profile", response_model=ProfileOut)
async def patch_profile(body: ProfileUpdate, user: CurrentUser, db: DbSession) -> ProfileOut:
    profile = await user_service.update_profile(
        db,
        user.id,
        resume_text=body.resume_text,
        target_role=body.target_role,
        clear_resume=body.clear_resume,
    )
    await db.commit()
    return ProfileOut.model_validate(profile)


@router.delete("/me", status_code=204)
async def delete_me(user: CurrentUser, db: DbSession) -> Response:
    """AS-05 — full deletion including object storage. See services/user_service.py."""
    await user_service.delete_user_and_all_data(db, user.id)
    await db.commit()
    return Response(status_code=204)
