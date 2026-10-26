"""Versioned hybrid envelopes using PyCA primitives, with bounded parsing."""

import base64
import hashlib
import json
import os
import struct
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

from .errors import AuthenticationError, FormatError, VaultError
from .filesystem import AtomicOutput
from .operations import OperationControl

FILE_MAGIC = b"SVFILE\x01\n"
MESSAGE_MAGIC = b"SVMSG\x00\x01\n"
MESSAGE_PREFIX = "SEREIN1:"
CHUNK_SIZE = 1024 * 1024
MAX_MESSAGE_BYTES = 1024 * 1024
MAX_HEADER_BYTES = 4096
OAEP_LABEL = b"Serein Vault envelope v1"


def validate_password(password: str):
    if not isinstance(password, str) or not 12 <= len(password) <= 1024 or not password.strip():
        raise VaultError("Use a password or passphrase of 12–1024 characters.")
    # Validate encoding consistently, including at creation and password change.
    try:
        password.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise VaultError("The password contains an invalid Unicode character.") from exc


def password_kdf(salt: bytes) -> Argon2id:
    return Argon2id(salt=salt, length=32, iterations=3, lanes=4, memory_cost=65536)


def derive_vault_key(password: str, salt: bytes) -> bytes:
    validate_password(password)
    return password_kdf(salt).derive(password.encode("utf-8"))


def password_hash(password: str) -> str:
    validate_password(password)
    return password_kdf(os.urandom(16)).derive_phc_encoded(password.encode("utf-8"))


def encode64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def decode64(text: str) -> bytes:
    if not isinstance(text, str):
        raise FormatError("An encoded field has an invalid type.")
    try:
        return base64.b64decode(text.encode("ascii"), altchars=b"-_", validate=True)
    except (ValueError, UnicodeError) as exc:
        raise FormatError("An encoded field is damaged.") from exc


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise FormatError("Duplicate JSON fields are not supported.")
        result[key] = value
    return result


@dataclass(frozen=True)
class KeyPair:
    private: rsa.RSAPrivateKey

    @classmethod
    def generate(cls):
        return cls(rsa.generate_private_key(public_exponent=65537, key_size=3072))

    @classmethod
    def load(cls, private_der: bytes, public_der: bytes):
        try:
            private = serialization.load_der_private_key(private_der, password=None)
            if not isinstance(private, rsa.RSAPrivateKey) or private.key_size != 3072:
                raise FormatError("The vault identity is not supported.")
            pair = cls(private)
            if pair.public_der != public_der:
                raise FormatError("The vault identity is inconsistent.")
            return pair
        except (TypeError, ValueError) as exc:
            raise FormatError("The vault identity is damaged.") from exc

    @property
    def private_der(self) -> bytes:
        # This value is stored ONLY inside the fully encrypted SQLite image.
        return self.private.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )

    @property
    def public_der(self) -> bytes:
        return self.private.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )

    @property
    def key_id(self) -> str:
        return hashlib.sha256(self.public_der).hexdigest()

    def wrap(self, data_key: bytes) -> bytes:
        return self.private.public_key().encrypt(data_key, self._padding())

    def unwrap(self, wrapped: bytes) -> bytes:
        try:
            key = self.private.decrypt(wrapped, self._padding())
        except ValueError as exc:
            raise AuthenticationError(
                "The encryption key is damaged or belongs to another vault."
            ) from exc
        if len(key) != 32:
            raise FormatError("The encrypted data key has an invalid length.")
        return key

    @staticmethod
    def _padding():
        return padding.OAEP(
            mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=OAEP_LABEL
        )


@dataclass(frozen=True)
class EncryptionRecord:
    record_id: str
    kind: str
    label: str
    data_key: bytes
    token: str | None = None


class EnvelopeCodec:
    def __init__(self, identity: KeyPair):
        self.identity = identity

    def header(self, kind: str, data_key: bytes):
        record_id = uuid.uuid4().hex
        nonce = os.urandom(12)
        metadata = {
            "version": 1,
            "id": record_id,
            "kind": kind,
            "key_id": self.identity.key_id,
            "nonce": encode64(nonce),
            "wrapped_key": encode64(self.identity.wrap(data_key)),
        }
        raw = json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("ascii")
        magic = MESSAGE_MAGIC if kind == "message" else FILE_MAGIC
        return record_id, nonce, magic + struct.pack(">I", len(raw)) + raw

    def parse(self, stream, kind: str):
        magic = MESSAGE_MAGIC if kind == "message" else FILE_MAGIC
        prefix = stream.read(len(magic) + 4)
        if len(prefix) != len(magic) + 4 or prefix[: len(magic)] != magic:
            raise FormatError("This is not a supported Serein Vault encrypted item.")
        length = struct.unpack(">I", prefix[-4:])[0]
        if not 0 < length <= MAX_HEADER_BYTES:
            raise FormatError("The encrypted header has an invalid size.")
        raw = stream.read(length)
        if len(raw) != length:
            raise FormatError("The encrypted header is incomplete.")
        try:
            metadata = json.loads(raw, object_pairs_hook=unique_object)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise FormatError("The encrypted header is damaged.") from exc
        expected = {"version", "id", "kind", "key_id", "nonce", "wrapped_key"}
        if not isinstance(metadata, dict) or metadata.keys() != expected:
            raise FormatError("The encrypted header has unsupported fields.")
        if type(metadata["version"]) is not int or metadata["version"] != 1:
            raise FormatError("This encrypted format version is not supported.")
        if metadata["kind"] != kind:
            raise FormatError("The encrypted item has the wrong type.")
        record_id = metadata["id"]
        if not isinstance(record_id, str) or len(record_id) != 32:
            raise FormatError("The item identifier is invalid.")
        try:
            if uuid.UUID(hex=record_id).hex != record_id:
                raise ValueError
        except ValueError as exc:
            raise FormatError("The item identifier is invalid.") from exc
        if metadata["key_id"] != self.identity.key_id:
            raise AuthenticationError(
                "This item belongs to a different vault. Open its original vault."
            )
        nonce = decode64(metadata["nonce"])
        wrapped = decode64(metadata["wrapped_key"])
        if len(nonce) != 12 or len(wrapped) != 384:
            raise FormatError("The encrypted header contains an invalid key or nonce.")
        return nonce, self.identity.unwrap(wrapped), prefix + raw

    def encrypt_message(self, text: str) -> EncryptionRecord:
        try:
            raw = text.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise VaultError("The message contains an invalid Unicode character.") from exc
        if not raw or len(raw) > MAX_MESSAGE_BYTES:
            raise VaultError("Enter a message between 1 byte and 1 MiB in UTF-8.")
        data_key = os.urandom(32)
        record_id, nonce, header = self.header("message", data_key)
        payload = header + AESGCM(data_key).encrypt(nonce, raw, header)
        token = MESSAGE_PREFIX + encode64(payload)
        return EncryptionRecord(record_id, "message", "Encrypted message", data_key, token)

    def decrypt_message(self, token: str) -> str:
        import io

        if not token.startswith(MESSAGE_PREFIX) or len(token) > 2 * MAX_MESSAGE_BYTES:
            raise FormatError("Paste a supported SEREIN1 encrypted message.")
        payload = decode64(token[len(MESSAGE_PREFIX) :])
        stream = io.BytesIO(payload)
        nonce, data_key, header = self.parse(stream, "message")
        try:
            return AESGCM(data_key).decrypt(nonce, stream.read(), header).decode("utf-8")
        except (InvalidTag, UnicodeError) as exc:
            raise AuthenticationError(
                "The message was modified, truncated, or encrypted incorrectly."
            ) from exc


class FileCipher:
    def __init__(self, identity: KeyPair):
        self.codec = EnvelopeCodec(identity)

    @staticmethod
    def validate_paths(source: Path, destination: Path):
        if not source.is_file():
            raise VaultError("Select an existing regular input file.")
        if source.resolve() == destination.resolve():
            raise VaultError("Choose a separate output file. Originals are always preserved.")
        if destination.exists():
            raise VaultError("The output already exists. Choose a new filename.")

    def encrypt(self, source: Path, destination: Path, save_record: Callable, control=None):
        control = control or OperationControl()
        control.check()
        self.validate_paths(source, destination)
        with source.open("rb") as reader:
            total = os.fstat(reader.fileno()).st_size
            control.report(0, total)
            if reader.read(len(FILE_MAGIC)) == FILE_MAGIC:
                raise VaultError("This file is already encrypted. Select the original file.")
            reader.seek(0)
            key = os.urandom(32)
            record_id, nonce, header = self.codec.header("file", key)
            encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
            encryptor.authenticate_additional_data(header)
            with AtomicOutput(destination) as output:
                output.stream.write(header)
                completed = 0
                while chunk := reader.read(CHUNK_SIZE):
                    control.check()
                    output.stream.write(encryptor.update(chunk))
                    completed += len(chunk)
                    control.report(completed, total)
                output.stream.write(encryptor.finalize())
                output.stream.write(encryptor.tag)
                # Persist the recovery record BEFORE publishing the output.
                control.check()
                save_record(EncryptionRecord(record_id, "file", source.name, key))
                control.check()
                output.publish()
        return destination

    def decrypt(self, source: Path, destination: Path, control=None):
        control = control or OperationControl()
        control.check()
        self.validate_paths(source, destination)
        with source.open("rb") as reader:
            nonce, key, header = self.codec.parse(reader, "file")
            start = reader.tell()
            length = os.fstat(reader.fileno()).st_size - start - 16
            if length < 0:
                raise FormatError("The encrypted file is incomplete.")
            control.report(0, length)
            reader.seek(-16, os.SEEK_END)
            tag = reader.read(16)
            reader.seek(start)
            decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
            decryptor.authenticate_additional_data(header)
            with AtomicOutput(destination) as output:
                remaining = length
                while remaining:
                    control.check()
                    chunk = reader.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        raise FormatError("The encrypted file was truncated during decryption.")
                    remaining -= len(chunk)
                    output.stream.write(decryptor.update(chunk))
                    control.report(length - remaining, length)
                try:
                    output.stream.write(decryptor.finalize())
                except InvalidTag as exc:
                    raise AuthenticationError(
                        "The encrypted file was modified or damaged."
                    ) from exc
                control.check()
                output.publish()
        return destination
