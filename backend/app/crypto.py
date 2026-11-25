"""Encrypts OAuth tokens at rest. The key lives only in .env (SECRET_KEY)."""
from __future__ import annotations

import json

from cryptography.fernet import Fernet

from .config import env


def _fernet() -> Fernet:
    if not env.secret_key:
        raise RuntimeError("SECRET_KEY is not set. Generate one with: "
                           "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
    return Fernet(env.secret_key.encode())


def encrypt_json(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_json(token: str) -> dict:
    return json.loads(_fernet().decrypt(token.encode()))
