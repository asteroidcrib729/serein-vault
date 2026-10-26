"""Explicit, non-destructive recovery of the prototype's Fernet key files."""

import base64
import json
import re
import uuid
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .crypto import EncryptionRecord, unique_object
from .errors import AuthenticationError, FormatError, VaultError
from .filesystem import AtomicOutput
from .storage import EncryptedVault

MAX_LEGACY_BYTES = 64 * 1024 * 1024


class LegacyImporter:
    def __init__(self, vault: EncryptedVault):
        self.vault = vault

    def import_keys(self, path: Path, kind: str) -> int:
        if kind not in {"file", "message"}:
            raise FormatError("Choose file keys or message keys.")
        with path.open("rb") as stream:
            raw = stream.read(10 * 1024 * 1024 + 1)
        if len(raw) > 10 * 1024 * 1024:
            raise FormatError("The legacy key file exceeds 10 MiB.")
        try:
            data = json.loads(raw, object_pairs_hook=unique_object)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise FormatError("The legacy key file contains invalid JSON.") from exc
        if not isinstance(data, dict) or not data or len(data) > 10000:
            raise FormatError("The legacy key file must contain 1–10,000 key records.")
        records = []
        for reference, key in data.items():
            if not isinstance(reference, str) or not reference or not isinstance(key, str):
                raise FormatError("Legacy key records must map strings to Fernet keys.")
            try:
                fernet = Fernet(key.encode("ascii"))
                if kind == "message":
                    token = base64.b64decode(reference.encode("ascii"), validate=True)
                    fernet.decrypt(token).decode("utf-8")
            except (ValueError, UnicodeError, InvalidToken) as exc:
                raise FormatError(
                    "A legacy key or message is invalid. Nothing was imported."
                ) from exc
            record = EncryptionRecord(
                uuid.uuid4().hex,
                "legacy_" + kind,
                reference if kind == "file" else "Imported legacy message",
                key.encode("ascii"),
                reference if kind == "message" else None,
            )
            records.append(record)
        # Validate the entire batch before mutating; one atomic encrypted save.
        with self.vault.transaction() as connection:
            for record in records:
                self.vault.insert_record(connection, record)
        return len(records)

    def import_password_hash(self, path: Path):
        with path.open("rb") as stream:
            raw = stream.read(1025)
        try:
            value = raw.decode("ascii").strip()
        except UnicodeError as exc:
            raise FormatError("The legacy password hash is invalid.") from exc
        if not re.fullmatch(r"[0-9a-fA-F]{128}", value):
            raise FormatError("The legacy file must contain one SHA3-512 hexadecimal hash.")
        with self.vault.transaction() as connection:
            connection.execute(
                "INSERT INTO metadata VALUES ('legacy_password_hash', ?) "
                "ON CONFLICT(name) DO UPDATE SET value=excluded.value",
                (value,),
            )

    def decrypt_message(self, record_id: str) -> str:
        record = self.vault.item(record_id)
        if record["kind"] != "legacy_message":
            raise VaultError("Select an imported legacy message.")
        try:
            return (
                Fernet(record["data_key"])
                .decrypt(base64.b64decode(record["token"].encode("ascii"), validate=True))
                .decode("utf-8")
            )
        except (ValueError, UnicodeError, InvalidToken) as exc:
            raise AuthenticationError("The legacy message or key is damaged.") from exc

    def decrypt_file(self, record_id: str, source: Path, destination: Path):
        from .crypto import FileCipher

        FileCipher.validate_paths(source, destination)
        record = self.vault.item(record_id)
        if record["kind"] != "legacy_file":
            raise VaultError("Select an imported legacy file key.")
        with source.open("rb") as stream:
            raw = stream.read(MAX_LEGACY_BYTES + 1)
        if len(raw) > MAX_LEGACY_BYTES:
            raise VaultError("Legacy recovery supports encrypted files up to 64 MiB.")
        try:
            plaintext = Fernet(record["data_key"]).decrypt(raw)
        except (ValueError, InvalidToken) as exc:
            raise AuthenticationError("This legacy key does not match the selected file.") from exc
        with AtomicOutput(destination) as output:
            output.stream.write(plaintext)
            output.publish()
        return destination
