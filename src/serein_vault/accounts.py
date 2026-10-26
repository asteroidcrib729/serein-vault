"""Small local-account credential envelope; no server or global user registry."""

import json
import os
import re
from dataclasses import dataclass, replace

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .crypto import decode64, encode64, password_kdf, unique_object, validate_password
from .errors import AuthenticationError, FormatError, VaultError

VAULT_MAGIC = b"SVDB\x00\x02\r\n"
LEGACY_VAULT_MAGIC = b"SVDB\x00\x01\r\n"
MAX_ACCOUNT_HEADER = 4096
RECOVERY_PREFIX = "SRK-"
LOGIN_ERROR = "Incorrect username or password, or the vault is damaged."


def normalize_username(username: str) -> str:
    if not isinstance(username, str):
        raise VaultError("Enter a username.")
    value = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,31}", value):
        raise VaultError(
            "Use a username of 3–32 letters, numbers, dots, dashes or underscores; "
            "start with a letter or number."
        )
    return value


def account_key(username: str, password: str, salt: bytes) -> bytes:
    username = normalize_username(username)
    validate_password(password)
    return password_kdf(salt).derive(username.encode("ascii") + b"\0" + password.encode("utf-8"))


def recovery_bytes(code: str) -> bytes:
    if not isinstance(code, str) or len(code) > 100:
        raise AuthenticationError("The recovery key is invalid.")
    value = code.strip()
    if not value.startswith(RECOVERY_PREFIX) or len(value) > 100:
        raise AuthenticationError("The recovery key is invalid.")
    try:
        key = decode64(value[len(RECOVERY_PREFIX) :])
    except FormatError as exc:
        raise AuthenticationError("The recovery key is invalid.") from exc
    if len(key) != 32:
        raise AuthenticationError("The recovery key is invalid.")
    return key


@dataclass(frozen=True)
class AccountEnvelope:
    salt: bytes
    password_nonce: bytes
    password_key: bytes
    recovery_nonce: bytes
    recovery_key: bytes

    @classmethod
    def create(cls, username: str, password: str, master: bytes):
        recovery = os.urandom(32)
        salt, pw_nonce, recovery_nonce = os.urandom(16), os.urandom(12), os.urandom(12)
        value = cls(
            salt,
            pw_nonce,
            AESGCM(account_key(username, password, salt)).encrypt(
                pw_nonce, master, cls._password_aad(username, salt)
            ),
            recovery_nonce,
            AESGCM(recovery).encrypt(recovery_nonce, master, VAULT_MAGIC + b"recovery"),
        )
        return value, RECOVERY_PREFIX + encode64(recovery)

    @staticmethod
    def _password_aad(username: str, salt: bytes):
        return VAULT_MAGIC + b"password\0" + normalize_username(username).encode("ascii") + salt

    def unlock(self, username: str, password: str) -> bytes:
        try:
            return AESGCM(account_key(username, password, self.salt)).decrypt(
                self.password_nonce, self.password_key, self._password_aad(username, self.salt)
            )
        except InvalidTag as exc:
            raise AuthenticationError(LOGIN_ERROR) from exc

    def recover(self, code: str) -> bytes:
        try:
            return AESGCM(recovery_bytes(code)).decrypt(
                self.recovery_nonce, self.recovery_key, VAULT_MAGIC + b"recovery"
            )
        except InvalidTag as exc:
            raise AuthenticationError("Incorrect recovery key, or the vault is damaged.") from exc

    def change_password(self, username: str, password: str, master: bytes):
        salt, nonce = os.urandom(16), os.urandom(12)
        wrapped = AESGCM(account_key(username, password, salt)).encrypt(
            nonce, master, self._password_aad(username, salt)
        )
        return replace(self, salt=salt, password_nonce=nonce, password_key=wrapped)

    def rotate_recovery(self, master: bytes):
        key, nonce = os.urandom(32), os.urandom(12)
        wrapped = AESGCM(key).encrypt(nonce, master, VAULT_MAGIC + b"recovery")
        return replace(
            self, recovery_nonce=nonce, recovery_key=wrapped
        ), RECOVERY_PREFIX + encode64(key)

    def encode(self) -> bytes:
        data = {name: encode64(getattr(self, name)) for name in self.__dataclass_fields__}
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("ascii")

    @classmethod
    def parse(cls, raw: bytes):
        try:
            data = json.loads(raw, object_pairs_hook=unique_object)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise FormatError("The account header is damaged.") from exc
        if not isinstance(data, dict) or data.keys() != cls.__dataclass_fields__.keys():
            raise FormatError("The account header has unsupported fields.")
        values = {name: decode64(value) for name, value in data.items()}
        for name, length in {
            "salt": 16,
            "password_nonce": 12,
            "password_key": 48,
            "recovery_nonce": 12,
            "recovery_key": 48,
        }.items():
            if len(values[name]) != length:
                raise FormatError("The account header contains an invalid field length.")
        return cls(**values)
