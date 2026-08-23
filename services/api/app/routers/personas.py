from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from ..core.deps import CurrentUser, DbSession
from ..core.exceptions import NotFoundError
from ..core.security import VOICE_PREVIEW_TOKEN_TTL_SECONDS, mint_voice_preview_token
from ..schemas.content import PersonaOut, VoicePreviewTokenOut
from ..services import content_service

router = APIRouter(prefix="/personas", tags=["personas"])


@router.get("", response_model=list[PersonaOut])
async def list_personas(db: DbSession) -> list[PersonaOut]:
    personas = await content_service.list_personas(db)
    return [PersonaOut.model_validate(p) for p in personas]


@router.post("/{persona_id}/voice-preview-token", response_model=VoicePreviewTokenOut)
async def mint_persona_voice_preview_token(
    persona_id: UUID, user: CurrentUser, db: DbSession
) -> VoicePreviewTokenOut:
    """Task 4.2: "Voice preview plays a pre-synthesised sample without starting a session."
    Any signed-in user can preview any persona's voice — persona voices aren't private data, so
    the only real check here is that the persona exists."""
    persona = await content_service.get_persona(db, persona_id)
    if persona is None:
        raise NotFoundError("Persona not found.")
    token = mint_voice_preview_token(persona.voice_id, str(user.id))
    return VoicePreviewTokenOut(
        token=token, expires_in=VOICE_PREVIEW_TOKEN_TTL_SECONDS, voice_id=persona.voice_id
    )
