"""GitHub and Google OAuth, implemented directly against each provider's HTTP API (not via
Authlib's Starlette-session-coupled `OAuth` registry) because the CSRF `state` parameter is
required to live in Redis with a 10-minute TTL, single use — not in a session cookie
(docs/phase-0-BUILD.md TASK 0.5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlencode

import httpx

from ..core.config import get_settings
from ..core.exceptions import AuthProviderError

Provider = Literal["github", "google"]


@dataclass(frozen=True)
class OAuthUserInfo:
    provider_id: str
    email: str
    email_verified: bool
    name: str | None
    avatar_url: str | None


def build_authorize_url(provider: Provider, *, state: str, redirect_uri: str) -> str:
    settings = get_settings()
    if provider == "github":
        params = {
            "client_id": settings.github_client_id,
            "redirect_uri": redirect_uri,
            "scope": "read:user user:email",
            "state": state,
        }
        return f"https://github.com/login/oauth/authorize?{urlencode(params)}"

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


async def exchange_code_for_user(
    provider: Provider, *, code: str, redirect_uri: str
) -> OAuthUserInfo:
    if provider == "github":
        return await _github_exchange(code, redirect_uri)
    return await _google_exchange(code, redirect_uri)


async def _github_exchange(code: str, redirect_uri: str) -> OAuthUserInfo:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
        if token_resp.status_code != 200:
            raise AuthProviderError("github", "Token exchange failed.")
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise AuthProviderError("github", token_data.get("error_description", ""))

        auth_header = {"Authorization": f"Bearer {access_token}"}
        user_resp = await client.get("https://api.github.com/user", headers=auth_header)
        if user_resp.status_code != 200:
            raise AuthProviderError("github", "Fetching profile failed.")
        user_data = user_resp.json()

        email = user_data.get("email")
        email_verified = bool(email)
        if not email:
            emails_resp = await client.get(
                "https://api.github.com/user/emails", headers=auth_header
            )
            if emails_resp.status_code == 200:
                for entry in emails_resp.json():
                    if entry.get("primary"):
                        email = entry.get("email")
                        email_verified = bool(entry.get("verified"))
                        break

        if not email:
            raise AuthProviderError("github", "GitHub account has no accessible email address.")

        return OAuthUserInfo(
            provider_id=str(user_data["id"]),
            email=email,
            email_verified=email_verified,
            name=user_data.get("name") or user_data.get("login"),
            avatar_url=user_data.get("avatar_url"),
        )


async def _google_exchange(code: str, redirect_uri: str) -> OAuthUserInfo:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            raise AuthProviderError("google", "Token exchange failed.")
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise AuthProviderError("google", token_data.get("error_description", ""))

        user_resp = await client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if user_resp.status_code != 200:
            raise AuthProviderError("google", "Fetching profile failed.")
        user_data = user_resp.json()

        return OAuthUserInfo(
            provider_id=str(user_data["sub"]),
            email=user_data["email"],
            email_verified=bool(user_data.get("email_verified")),
            name=user_data.get("name"),
            avatar_url=user_data.get("picture"),
        )
