from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import settings


def _derive_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt(plaintext: str) -> str:
    f = Fernet(_derive_key(settings.SECRET_KEY))
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    f = Fernet(_derive_key(settings.SECRET_KEY))
    return f.decrypt(ciphertext.encode()).decode()
