"""Symmetric at-rest encryption for user-supplied secrets (Task 4.4: bring-your-own-key
provider credentials). Deliberately narrow — this is not a general-purpose crypto module.

Fernet (AES-128-CBC + HMAC, from the `cryptography` package via `itsdangerous`-free `fernet`)
keyed off APP_SECRET, which every service already reads from the shared root `.env` (CLAUDE.md
§2). `APP_SECRET` doubles as this key's source material (already used as the refresh-token
pepper — services/api/app/core/security.py) rather than minting a fourth secret: a BYOK
provider key is lower-stakes than a session token, and one already-provisioned secret is enough
attack-surface for it.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet

from .config import get_settings


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    # Fernet keys must be 32 url-safe-base64 bytes; APP_SECRET is an arbitrary-length hex
    # string, so it's stretched through SHA-256 first.
    digest = hashlib.sha256(settings.app_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
