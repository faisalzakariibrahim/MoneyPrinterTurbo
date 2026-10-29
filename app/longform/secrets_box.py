"""AES-256-GCM for OAuth refresh tokens stored in the database.

Format (base64): 12-byte IV | ciphertext | 16-byte tag — identical to what the
Next.js app writes with ``crypto.createCipheriv('aes-256-gcm', ...)``.
The key is ``LF_TOKEN_ENC_KEY`` (32 bytes, base64) and lives only in server env.
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _key() -> bytes:
    raw = os.environ.get("LF_TOKEN_ENC_KEY", "")
    try:
        key = base64.b64decode(raw)
    except ValueError as e:
        raise RuntimeError("LF_TOKEN_ENC_KEY is not valid base64") from e
    if len(key) != 32:
        raise RuntimeError("LF_TOKEN_ENC_KEY must decode to 32 bytes")
    return key


def encrypt(plaintext: str) -> str:
    iv = os.urandom(12)
    ct = AESGCM(_key()).encrypt(iv, plaintext.encode(), None)
    return base64.b64encode(iv + ct).decode()


def decrypt(token: str) -> str:
    blob = base64.b64decode(token)
    iv, ct = blob[:12], blob[12:]
    return AESGCM(_key()).decrypt(iv, ct, None).decode()
