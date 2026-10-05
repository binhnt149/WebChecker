from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class SecurityManager:
    """Small Fernet wrapper used for secrets stored in SQLite."""

    def __init__(self, key_path: str | Path = "data/fernet.key") -> None:
        self.key_path = Path(key_path)
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        self._fernet = Fernet(self._load_or_create_key())

    def _load_or_create_key(self) -> bytes:
        if self.key_path.exists():
            return self.key_path.read_bytes().strip()

        key = Fernet.generate_key()
        self.key_path.write_bytes(key)
        return key

    def encrypt(self, value: object | None) -> str:
        if value is None:
            return ""
        text = str(value)
        if text == "":
            return ""
        return self._fernet.encrypt(text.encode("utf-8")).decode("utf-8")

    def decrypt(self, token: object | None) -> str:
        if token is None:
            return ""
        text = str(token)
        if text == "":
            return ""
        try:
            return self._fernet.decrypt(text.encode("utf-8")).decode("utf-8")
        except (InvalidToken, ValueError):
            return ""
