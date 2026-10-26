import io
import json
import os
import struct

import pytest

from serein_vault.crypto import FILE_MAGIC, MESSAGE_PREFIX, EnvelopeCodec, decode64, encode64
from serein_vault.errors import AuthenticationError, FormatError, VaultError
from serein_vault.service import VaultService

from .conftest import PASSWORD, USERNAME


@pytest.mark.parametrize(
    "contents",
    [b"", b"\x00\xff\n", b"x" * (3 * 1024 * 1024 + 17)],
    ids=["empty", "binary", "streamed-multichunk"],
)
def test_file_roundtrip_after_move_preserves_sources(service, tmp_path, contents):
    source = tmp_path / "original.bin"
    source.write_bytes(contents)
    encrypted = tmp_path / "encrypted.svault"
    service.encrypt_file(source, encrypted)
    assert source.read_bytes() == contents
    assert encrypted.read_bytes().startswith(FILE_MAGIC)
    moved = tmp_path / "renamed-anywhere.bin"
    encrypted.rename(moved)
    before = moved.read_bytes()
    recovered = tmp_path / "recovered.bin"
    service.decrypt_file(moved, recovered)
    assert recovered.read_bytes() == contents
    assert moved.read_bytes() == before
    assert len(service.history()) == 1


def test_repeated_encryption_is_rejected_without_losing_keys(service, tmp_path):
    original = tmp_path / "original"
    original.write_bytes(b"keep me")
    encrypted = tmp_path / "encrypted.svault"
    service.encrypt_file(original, encrypted)
    with pytest.raises(VaultError, match="already encrypted"):
        service.encrypt_file(encrypted, tmp_path / "second.svault")
    assert len(service.history()) == 1
    recovered = tmp_path / "recovered"
    service.decrypt_file(encrypted, recovered)
    assert recovered.read_bytes() == b"keep me"


def test_existing_output_and_same_source_are_preserved(service, tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"original")
    destination = tmp_path / "exists"
    destination.write_bytes(b"existing data")
    with pytest.raises(VaultError):
        service.encrypt_file(source, destination)
    with pytest.raises(VaultError):
        service.encrypt_file(source, source)
    assert source.read_bytes() == b"original"
    assert destination.read_bytes() == b"existing data"


@pytest.mark.parametrize("offset", [-1, -17, 50])
def test_file_tampering_never_publishes_plaintext(service, tmp_path, offset):
    source = tmp_path / "source"
    source.write_bytes(b"private plaintext" * 100)
    encrypted = tmp_path / "encrypted.svault"
    service.encrypt_file(source, encrypted)
    contents = bytearray(encrypted.read_bytes())
    contents[offset] ^= 1
    encrypted.write_bytes(contents)
    destination = tmp_path / "never-published"
    with pytest.raises((AuthenticationError, FormatError)):
        service.decrypt_file(encrypted, destination)
    assert not destination.exists()
    assert not list(tmp_path.glob(".serein-*.tmp"))
    assert source.read_bytes() == b"private plaintext" * 100


def test_failed_key_save_never_publishes_encrypted_file(service, tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.write_bytes(b"unchanged original")
    destination = tmp_path / "encrypted.svault"

    def fail(_):
        raise OSError("simulated key-store failure")

    monkeypatch.setattr(service.vault, "add_record", fail)
    with pytest.raises(OSError):
        service.encrypt_file(source, destination)
    assert source.read_bytes() == b"unchanged original"
    assert not destination.exists()
    assert not list(tmp_path.glob(".serein-*.tmp"))


def test_wrong_vault_cannot_decrypt(service, tmp_path):
    token = service.encrypt_message("vault one")
    other = VaultService.signup(tmp_path / "other.svdb", USERNAME, PASSWORD)[0]
    try:
        with pytest.raises(AuthenticationError, match="different vault"):
            other.decrypt_message(token)
    finally:
        other.close()


def test_actual_message_input_is_used(service):
    first = service.encrypt_message("first")
    second = service.encrypt_message("second")
    assert service.decrypt_message(first) == "first"
    assert service.decrypt_message(second) == "second"
    raw = bytearray(decode64(first[len(MESSAGE_PREFIX) :]))
    raw[-1] ^= 1
    with pytest.raises(AuthenticationError):
        service.decrypt_message(MESSAGE_PREFIX + encode64(raw))


@pytest.mark.parametrize(
    "token",
    ["", "not a message", MESSAGE_PREFIX + "!@#", MESSAGE_PREFIX + "a" * 3000000],
    ids=["empty", "plaintext", "invalid-base64", "oversized"],
)
def test_malformed_messages_fail_cleanly(service, token):
    with pytest.raises(FormatError):
        service.decrypt_message(token)


def test_bounded_header_and_duplicate_fields(service):
    codec = EnvelopeCodec(service.vault.identity())
    with pytest.raises(FormatError):
        codec.parse(io.BytesIO(FILE_MAGIC + struct.pack(">I", 0xFFFFFFFF)), "file")
    metadata = b'{"version":1,"version":1}'
    with pytest.raises(FormatError):
        codec.parse(io.BytesIO(FILE_MAGIC + struct.pack(">I", len(metadata)) + metadata), "file")


def test_header_version_is_authenticated_and_strictly_typed(service):
    token = service.encrypt_message("header test")
    payload = decode64(token[len(MESSAGE_PREFIX) :])
    length = struct.unpack(">I", payload[8:12])[0]
    header = json.loads(payload[12 : 12 + length])
    header["version"] = True
    modified = json.dumps(header, separators=(",", ":")).encode()
    payload = payload[:8] + struct.pack(">I", len(modified)) + modified + payload[12 + length :]
    with pytest.raises(FormatError):
        service.decrypt_message(MESSAGE_PREFIX + encode64(payload))


def test_atomic_output_collision_does_not_clobber_competitor(service, tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.write_bytes(b"original")
    destination = tmp_path / "competing-output"
    link = os.link

    def race(temporary, target):
        destination.write_bytes(b"competitor")
        return link(temporary, target)

    monkeypatch.setattr("serein_vault.filesystem.os.link", race)
    with pytest.raises(VaultError, match="already exists"):
        service.encrypt_file(source, destination)
    assert destination.read_bytes() == b"competitor"
    assert source.read_bytes() == b"original"
    assert not list(tmp_path.glob(".serein-*.tmp"))


def test_active_vault_cannot_be_encrypted_or_used_as_output(service, tmp_path):
    path = service.vault.path
    with pytest.raises(VaultError, match="active vault"):
        service.encrypt_file(path, tmp_path / "bad.svault")
    source = tmp_path / "source"
    source.write_bytes(b"input")
    with pytest.raises(VaultError, match="active vault"):
        service.encrypt_file(source, path)
