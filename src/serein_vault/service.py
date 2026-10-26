"""Application operations independent of the Tkinter presentation."""

import threading
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from .crypto import EnvelopeCodec, FileCipher
from .errors import AuthenticationError, VaultError
from .legacy import LegacyImporter
from .storage import EncryptedVault


class VaultService:
    def __init__(self, vault: EncryptedVault):
        self.vault = vault
        self._lock = threading.RLock()
        self._username = vault.username

    @classmethod
    def signup(cls, path: Path, username: str, password: str):
        vault, recovery = EncryptedVault.create(path, username, password)
        return cls(vault), recovery

    @classmethod
    def login(cls, path: Path, username: str, password: str):
        return cls(EncryptedVault.open(path, username, password))

    @classmethod
    def upgrade(cls, path: Path, username: str, password: str):
        vault, recovery = EncryptedVault.upgrade(path, username, password)
        return cls(vault), recovery

    @staticmethod
    def reset_password(path: Path, username: str, recovery: str, new_password: str):
        return EncryptedVault.reset_password(path, username, recovery, new_password)

    @property
    def username(self):
        return self._username

    @contextmanager
    def _authorized(self):
        with self._lock:
            if not self.vault.is_open or self._username is None:
                raise VaultError("The vault is locked. Log in before continuing.")
            if self.vault.username != self._username:
                raise AuthenticationError("This session is not authorized for the vault owner.")
            yield

    def _guard_paths(self, *paths: Path):
        protected = {self.vault.path, self.vault.path.with_name(self.vault.path.name + ".lock")}
        for path in paths:
            if Path(path).resolve() in protected:
                raise VaultError(
                    "The active vault and its lock file cannot be used as input or output."
                )

    @staticmethod
    def _label(value):
        if not isinstance(value, str) or len(value) > 80 or any(ord(c) < 32 for c in value):
            raise VaultError("Use a single-line message label of at most 80 characters.")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise VaultError("The label contains invalid Unicode.") from exc
        return value.strip() or "Encrypted message"

    def encrypt_message(self, text: str, label: str = "") -> str:
        with self._authorized():
            label = self._label(label)
            record = EnvelopeCodec(self.vault.identity()).encrypt_message(text)
            self.vault.add_record(replace(record, label=label))
            return record.token

    def decrypt_message(self, token: str) -> str:
        with self._authorized():
            return EnvelopeCodec(self.vault.identity()).decrypt_message(token)

    def encrypt_file(self, source: Path, destination: Path, control=None):
        with self._authorized():
            self._guard_paths(source, destination)
            return FileCipher(self.vault.identity()).encrypt(
                source, destination, self.vault.add_record, control
            )

    def decrypt_file(self, source: Path, destination: Path, control=None):
        with self._authorized():
            self._guard_paths(source, destination)
            return FileCipher(self.vault.identity()).decrypt(source, destination, control)

    def history(self, query: str = "") -> list[dict]:
        with self._authorized():
            if not isinstance(query, str) or len(query) > 128:
                raise VaultError("Keep the history search within 128 characters.")
            query = query.casefold().strip()
            return [
                row
                for row in self.vault.items()
                if query in " ".join((row["kind"], row["label"], row["created_at"])).casefold()
            ]

    def label_message(self, record_id: str, label: str):
        with self._authorized():
            self.vault.label_message(record_id, self._label(label))

    def health(self):
        with self._authorized():
            return self.vault.health()

    def history_message(self, record_id: str, *, decrypt: bool = False) -> str:
        with self._authorized():
            record = self.vault.item(record_id)
            if record["kind"] == "legacy_message":
                if decrypt:
                    return LegacyImporter(self.vault).decrypt_message(record_id)
                raise VaultError("Use Recover message for imported legacy messages.")
            if record["kind"] != "message":
                raise VaultError("Select a message in the history list.")
            return self.decrypt_message(record["token"]) if decrypt else record["token"]

    def import_legacy(self, path: Path, kind: str):
        with self._authorized():
            self._guard_paths(path)
            importer = LegacyImporter(self.vault)
            if kind == "password":
                importer.import_password_hash(path)
                return "Archived the legacy password hash inside the encrypted database."
            count = importer.import_keys(path, kind)
            return f"Imported {count} legacy {kind} key(s). Original files were preserved."

    def recover_legacy_file(self, record_id: str, source: Path, destination: Path):
        with self._authorized():
            self._guard_paths(source, destination)
            return LegacyImporter(self.vault).decrypt_file(record_id, source, destination)

    def change_password(self, current: str, new: str):
        with self._authorized():
            self.vault.change_password(current, new)

    def rotate_recovery(self, current_password: str):
        with self._authorized():
            return self.vault.rotate_recovery(current_password)

    def backup(self, destination: Path):
        with self._authorized():
            self._guard_paths(destination)
            return self.vault.backup(destination)

    def close(self):
        with self._lock:
            self.vault.close()
            self._username = None
