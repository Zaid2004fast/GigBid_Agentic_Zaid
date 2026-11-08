"""Encryption for OAuth / marketplace tokens at rest (Fernet, AES-128-CBC + HMAC).
TOKEN_ENC_KEY must be set in production; a dev key is derived only when GIGBID_ENV=dev."""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet


def _key() -> bytes:
    k = os.getenv("TOKEN_ENC_KEY")
    if k:
        return k.encode()
    if os.getenv("GIGBID_ENV", "dev") != "dev":
        raise RuntimeError("TOKEN_ENC_KEY must be set outside dev")
    return base64.urlsafe_b64encode(hashlib.sha256(b"gigbid-dev-only-key").digest())


def encrypt(plaintext: str) -> str:
    return Fernet(_key()).encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return Fernet(_key()).decrypt(ciphertext.encode()).decode()
