"""Encrypted SQLite with one local owner and recoverable account credentials."""

import hashlib
import hmac
import os
import sqlite3
import struct
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .accounts import (
    LEGACY_VAULT_MAGIC,
    LOGIN_ERROR,
    MAX_ACCOUNT_HEADER,
    VAULT_MAGIC,
    AccountEnvelope,
    normalize_username,
)
from .crypto import EncryptionRecord, KeyPair, derive_vault_key, password_hash, validate_password
from .errors import AuthenticationError, FormatError, VaultError
from .filesystem import AtomicOutput, VaultFileLock

MAX_DATABASE_BYTES = 64 * 1024 * 1024
SCHEMA = """
PRAGMA user_version=2;
CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE identity (
    key_id TEXT PRIMARY KEY, public_key BLOB NOT NULL, private_key BLOB NOT NULL
);
CREATE TABLE items (
    record_id TEXT PRIMARY KEY, kind TEXT NOT NULL, label TEXT NOT NULL,
    created_at TEXT NOT NULL, data_key BLOB NOT NULL, token TEXT
);
"""


def timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class EncryptedVault:
    def __init__(self, path: Path):
        self.path = Path(path).expanduser().resolve()
        self.lock = threading.RLock()
        self._file_lock = VaultFileLock(self.path)
        self._connection: sqlite3.Connection | None = None
        self._key: bytes | None = None
        self._credentials: AccountEnvelope | None = None
        self._fingerprint: bytes | None = None

    @staticmethod
    def _connect():
        connection = sqlite3.connect(":memory:", check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA temp_store=MEMORY")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @classmethod
    def create(cls, path: Path, username: str, password: str):
        username = normalize_username(username)
        validate_password(password)
        vault = cls(path)
        vault.path.parent.mkdir(parents=True, exist_ok=True)
        vault._file_lock.acquire()
        try:
            if vault.path.exists():
                raise VaultError(
                    "An account vault already exists here. Log in or choose another file."
                )
            vault._key = os.urandom(32)
            vault._credentials, recovery = AccountEnvelope.create(username, password, vault._key)
            vault._connection = vault._connect()
            vault._connection.executescript(SCHEMA)
            vault._connection.executemany(
                "INSERT INTO metadata VALUES (?, ?)",
                [
                    ("username", username),
                    ("password_hash", password_hash(password)),
                    ("created_at", timestamp()),
                ],
            )
            pair = KeyPair.generate()
            vault._connection.execute(
                "INSERT INTO identity VALUES (?, ?, ?)",
                (pair.key_id, pair.public_der, pair.private_der),
            )
            vault._connection.commit()
            vault._save(replace=False)
            return vault, recovery
        except BaseException:
            vault.close()
            raise

    @classmethod
    def open(cls, path: Path, username: str, password: str):
        username = normalize_username(username)
        validate_password(password)
        return cls._load(path, username, password=password)

    @classmethod
    def _load(cls, path: Path, username: str, *, password=None, recovery=None):
        vault = cls(path)
        if not vault.path.is_file():
            raise VaultError(
                "The account vault does not exist. Sign up or choose an existing file."
            )
        vault._file_lock.acquire()
        try:
            payload = vault._read_payload()
            if payload.startswith(LEGACY_VAULT_MAGIC):
                raise FormatError(
                    "This password-only vault needs an upgrade. Use Upgrade old vault."
                )
            if not payload.startswith(VAULT_MAGIC) or len(payload) < 40:
                raise FormatError("This is not a supported Serein Vault account database.")
            length = struct.unpack(">I", payload[8:12])[0]
            if not 0 < length <= MAX_ACCOUNT_HEADER or len(payload) < 12 + length + 28:
                raise FormatError("The account vault header is incomplete or invalid.")
            vault._credentials = AccountEnvelope.parse(payload[12 : 12 + length])
            if recovery is None:
                vault._key = vault._credentials.unlock(username, password)
            else:
                vault._key = vault._credentials.recover(recovery)
            header = payload[: 12 + length]
            vault._decrypt_image(payload[12 + length :], header)
            vault._validate_schema()
            if vault.username != username:
                raise AuthenticationError(
                    LOGIN_ERROR if recovery is None else "Username or recovery key is incorrect."
                )
            vault._fingerprint = hashlib.sha256(payload).digest()
            vault.identity()
            return vault
        except BaseException:
            vault.close()
            raise

    def _decrypt_image(self, encrypted: bytes, header: bytes):
        try:
            image = AESGCM(self._key).decrypt(encrypted[:12], encrypted[12:], header)
        except InvalidTag as exc:
            raise AuthenticationError(LOGIN_ERROR) from exc
        self._connection = self._connect()
        try:
            self._connection.deserialize(image)
        except sqlite3.Error as exc:
            raise FormatError("The encrypted SQLite database is damaged.") from exc

    def _validate_schema(self, *, legacy=False):
        connection = self.connection
        try:
            if connection.execute("PRAGMA user_version").fetchone()[0] != (1 if legacy else 2):
                raise FormatError("This database version is not supported.")
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise FormatError("The vault database integrity check failed.")
            connection.execute("SELECT key_id, public_key, private_key FROM identity LIMIT 0")
            connection.execute(
                "SELECT record_id, kind, label, created_at, data_key, token FROM items LIMIT 0"
            )
            row = connection.execute(
                "SELECT value FROM metadata WHERE name='password_hash'"
            ).fetchone()
            if row is None or not isinstance(row[0], str) or not row[0].startswith("$argon2id$"):
                raise FormatError("The password record is missing or invalid.")
            if not legacy:
                normalize_username(self.username)
        except sqlite3.Error as exc:
            raise FormatError("The vault schema is damaged or unsupported.") from exc

    @property
    def connection(self):
        if self._connection is None:
            raise VaultError("The vault is locked. Log in before continuing.")
        return self._connection

    @property
    def username(self) -> str:
        row = self.connection.execute("SELECT value FROM metadata WHERE name='username'").fetchone()
        if row is None or not isinstance(row[0], str):
            raise FormatError("The account owner is missing.")
        return row[0]

    @property
    def is_open(self):
        return self._connection is not None

    def _read_payload(self):
        with self.path.open("rb") as stream:
            payload = stream.read(MAX_DATABASE_BYTES + MAX_ACCOUNT_HEADER + 128)
        if len(payload) > MAX_DATABASE_BYTES + MAX_ACCOUNT_HEADER + 64:
            raise FormatError("The vault exceeds the supported 64 MiB database size.")
        return payload

    def _assert_current(self):
        if self._fingerprint is not None:
            try:
                current = hashlib.sha256(self._read_payload()).digest()
            except OSError as exc:
                raise VaultError(
                    "The vault was moved or removed. Restore it before continuing."
                ) from exc
            if not hmac.compare_digest(current, self._fingerprint):
                raise VaultError("The vault changed outside this session. Log out and reopen it.")

    def _save(self, *, replace=True):
        image = self.connection.serialize()
        if len(image) > MAX_DATABASE_BYTES:
            raise VaultError(
                "The vault reached its 64 MiB limit. Use a separate vault for new records."
            )
        self._assert_current()
        raw = self._credentials.encode()
        header = VAULT_MAGIC + struct.pack(">I", len(raw)) + raw
        nonce = os.urandom(12)
        payload = header + nonce + AESGCM(self._key).encrypt(nonce, image, header)
        with AtomicOutput(self.path, replace=replace) as output:
            output.stream.write(payload)
            output.publish()
        self._fingerprint = hashlib.sha256(payload).digest()

    @contextmanager
    def transaction(self):
        with self.lock:
            connection = self.connection
            previous = connection.serialize()
            old_credentials = self._credentials
            try:
                yield connection
                connection.commit()
                self._save()
            except BaseException:
                connection.rollback()
                connection.deserialize(previous)
                self._credentials = old_credentials
                raise

    def identity(self):
        with self.lock:
            rows = self.connection.execute("SELECT * FROM identity").fetchall()
            if len(rows) != 1:
                raise FormatError("The vault identity is missing or ambiguous.")
            pair = KeyPair.load(rows[0]["private_key"], rows[0]["public_key"])
            if pair.key_id != rows[0]["key_id"]:
                raise FormatError("The vault key identifier is inconsistent.")
            return pair

    @staticmethod
    def insert_record(connection, record: EncryptionRecord):
        connection.execute(
            "INSERT INTO items VALUES (?, ?, ?, ?, ?, ?)",
            (
                record.record_id,
                record.kind,
                record.label,
                timestamp(),
                record.data_key,
                record.token,
            ),
        )

    def add_record(self, record):
        with self.transaction() as connection:
            self.insert_record(connection, record)

    def items(self):
        with self.lock:
            return [
                dict(row)
                for row in self.connection.execute(
                    "SELECT record_id, kind, label, created_at FROM items ORDER BY rowid DESC"
                )
            ]

    def label_message(self, record_id: str, label: str):
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT kind FROM items WHERE record_id=?", (record_id,)
            ).fetchone()
            if row is None or row[0] not in {"message", "legacy_message"}:
                raise VaultError("Select a message to edit its label.")
            connection.execute("UPDATE items SET label=? WHERE record_id=?", (label, record_id))

    def health(self):
        with self.lock:
            self._assert_current()
            integrity = self.connection.execute("PRAGMA quick_check").fetchone()[0]
            if integrity != "ok":
                raise FormatError("The database integrity check failed. Restore a verified backup.")
            self.identity()
            count = self.connection.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            return {
                "integrity": "ok",
                "owner": self.username,
                "records": count,
                "encrypted_bytes": self.path.stat().st_size,
            }

    def item(self, record_id):
        with self.lock:
            row = self.connection.execute(
                "SELECT * FROM items WHERE record_id=?", (record_id,)
            ).fetchone()
            if row is None:
                raise VaultError("This history item does not exist in the current vault.")
            return dict(row)

    def change_password(self, current: str, new: str):
        validate_password(new)
        with self.lock:
            owner = self.username
            if not hmac.compare_digest(self._credentials.unlock(owner, current), self._key):
                raise AuthenticationError("The current password is incorrect.")
            credentials = self._credentials.change_password(owner, new, self._key)
            with self.transaction() as connection:
                connection.execute(
                    "UPDATE metadata SET value=? WHERE name='password_hash'", (password_hash(new),)
                )
                self._credentials = credentials

    @classmethod
    def reset_password(cls, path: Path, username: str, recovery: str, new_password: str):
        username = normalize_username(username)
        validate_password(new_password)
        vault = cls._load(path, username, recovery=recovery)
        try:
            credentials, new_recovery = AccountEnvelope.create(username, new_password, vault._key)
            with vault.transaction() as connection:
                connection.execute(
                    "UPDATE metadata SET value=? WHERE name='password_hash'",
                    (password_hash(new_password),),
                )
                vault._credentials = credentials
            return new_recovery
        finally:
            vault.close()

    def rotate_recovery(self, current_password: str):
        with self.lock:
            owner = self.username
            if not hmac.compare_digest(
                self._credentials.unlock(owner, current_password), self._key
            ):
                raise AuthenticationError("The current password is incorrect.")
            credentials, recovery = self._credentials.rotate_recovery(self._key)
            with self.transaction():
                self._credentials = credentials
            return recovery

    @classmethod
    def upgrade(cls, path: Path, username: str, password: str):
        """Upgrade v1 explicitly, preserving a separate encrypted original backup."""
        username = normalize_username(username)
        validate_password(password)
        vault = cls(path)
        if not vault.path.is_file():
            raise VaultError("Select an existing password-only vault.")
        vault._file_lock.acquire()
        try:
            payload = vault._read_payload()
            if not payload.startswith(LEGACY_VAULT_MAGIC) or len(payload) < 52:
                raise FormatError("Select a version-one password-only Serein vault.")
            salt = payload[8:24]
            vault._key = derive_vault_key(password, salt)
            vault._decrypt_image(payload[24:], payload[:24])
            vault._validate_schema(legacy=True)
            vault.identity()
            backup = vault.path.with_name(
                vault.path.stem + ".before-account-" + uuid.uuid4().hex[:8] + ".svdb"
            )
            with AtomicOutput(backup) as output:
                output.stream.write(payload)
                output.publish()
            vault._fingerprint = hashlib.sha256(payload).digest()
            # Re-encrypt the image under a random master key, wrapped by both credentials.
            vault._key = os.urandom(32)
            credentials, recovery = AccountEnvelope.create(username, password, vault._key)
            with vault.transaction() as connection:
                connection.execute("INSERT INTO metadata VALUES ('username', ?)", (username,))
                connection.execute("PRAGMA user_version=2")
                vault._credentials = credentials
            return vault, recovery
        except BaseException:
            vault.close()
            raise

    def backup(self, destination: Path):
        with self.lock:
            _ = self.connection
            self._assert_current()
            if Path(destination).resolve() == self.path:
                raise VaultError("Choose a separate backup file.")
            with AtomicOutput(destination) as output:
                output.stream.write(self._read_payload())
                output.publish()
        return destination

    def close(self):
        with self.lock:
            if self._connection is not None:
                self._connection.close()
            self._connection = None
            self._key = self._credentials = self._fingerprint = None
            self._file_lock.release()
