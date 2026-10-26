import json
import os
import sqlite3
import struct

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from serein_vault.accounts import LEGACY_VAULT_MAGIC, VAULT_MAGIC, normalize_username
from serein_vault.crypto import EnvelopeCodec, KeyPair, derive_vault_key, password_hash
from serein_vault.errors import AuthenticationError, FormatError, VaultError
from serein_vault.service import VaultService

from .conftest import PASSWORD, USERNAME


def test_signup_username_is_encrypted_and_canonical(tmp_path):
    path = tmp_path / "account.svdb"
    service, recovery = VaultService.signup(path, "  My.Name  ", PASSWORD)
    try:
        assert service.username == "my.name"
        assert b"my.name" not in path.read_bytes()
        assert recovery.encode() not in path.read_bytes()
        token = service.encrypt_message("owner's message")
    finally:
        service.close()
    before = path.read_bytes()
    with pytest.raises(AuthenticationError):
        VaultService.login(path, "another.user", PASSWORD)
    assert path.read_bytes() == before
    logged_in = VaultService.login(path, "MY.NAME", PASSWORD)
    try:
        assert logged_in.decrypt_message(token) == "owner's message"
    finally:
        logged_in.close()


@pytest.mark.parametrize("username", ["ab", "a" * 33, "bad space", "../escape", "☘user", ".start"])
def test_invalid_usernames_are_rejected(username):
    with pytest.raises(VaultError):
        normalize_username(username)


def test_reset_preserves_identity_files_history_and_replaces_recovery(tmp_path):
    path = tmp_path / "account.svdb"
    service, recovery = VaultService.signup(path, USERNAME, PASSWORD)
    token = service.encrypt_message("message before reset")
    source = tmp_path / "source"
    source.write_bytes(b"private file data")
    encrypted = tmp_path / "encrypted.svault"
    service.encrypt_file(source, encrypted)
    identity = service.vault.identity().key_id
    service.close()
    new_password = "  new password with unicode 🌿  "
    new_recovery = VaultService.reset_password(path, USERNAME, recovery, new_password)
    assert new_recovery != recovery
    with pytest.raises(AuthenticationError):
        VaultService.login(path, USERNAME, PASSWORD)
    with pytest.raises(AuthenticationError):
        VaultService.reset_password(path, USERNAME, recovery, PASSWORD)
    restored = VaultService.login(path, USERNAME, new_password)
    try:
        assert restored.vault.identity().key_id == identity
        assert restored.decrypt_message(token) == "message before reset"
        restored.decrypt_file(encrypted, tmp_path / "recovered")
        assert (tmp_path / "recovered").read_bytes() == source.read_bytes()
        assert len(restored.history()) == 2
    finally:
        restored.close()
    # The replacement recovery key works independently of the current password.
    VaultService.reset_password(path, USERNAME, new_recovery, PASSWORD)


def test_wrong_recovery_or_username_cannot_change_vault(tmp_path):
    path = tmp_path / "account.svdb"
    service, recovery = VaultService.signup(path, USERNAME, PASSWORD)
    service.close()
    original = path.read_bytes()
    for username, key in (("wrong.user", recovery), (USERNAME, "invalid key")):
        with pytest.raises(AuthenticationError):
            VaultService.reset_password(path, username, key, "a replacement password")
        assert path.read_bytes() == original


def test_recovery_rotation_requires_password_and_revokes_old_key(tmp_path):
    path = tmp_path / "account.svdb"
    service, recovery = VaultService.signup(path, USERNAME, PASSWORD)
    try:
        before = path.read_bytes()
        with pytest.raises(AuthenticationError):
            service.rotate_recovery("an incorrect password")
        assert path.read_bytes() == before
        replacement = service.rotate_recovery(PASSWORD)
        assert replacement != recovery
        service.change_password(PASSWORD, "a changed normal password")
    finally:
        service.close()
    with pytest.raises(AuthenticationError):
        VaultService.reset_password(path, USERNAME, recovery, PASSWORD)
    VaultService.reset_password(path, USERNAME, replacement, PASSWORD)


def test_failed_reset_keeps_both_existing_login_and_recovery(tmp_path, monkeypatch):
    path = tmp_path / "account.svdb"
    service, recovery = VaultService.signup(path, USERNAME, PASSWORD)
    token = service.encrypt_message("saved record")
    service.close()
    original = path.read_bytes()
    with monkeypatch.context() as patcher:

        def fail(*_):
            raise OSError("injected disk failure")

        patcher.setattr("serein_vault.filesystem.os.replace", fail)
        with pytest.raises(OSError):
            VaultService.reset_password(path, USERNAME, recovery, "a replacement password")
    assert path.read_bytes() == original
    reopened = VaultService.login(path, USERNAME, PASSWORD)
    try:
        assert reopened.decrypt_message(token) == "saved record"
    finally:
        reopened.close()
    VaultService.reset_password(path, USERNAME, recovery, "a replacement password")


def test_authorization_checks_every_service_operation(service, tmp_path):
    service._username = "another.user"
    operations = [
        lambda: service.encrypt_message("text"),
        lambda: service.decrypt_message("invalid"),
        service.history,
        lambda: service.history_message("id"),
        lambda: service.encrypt_file(tmp_path / "in", tmp_path / "out"),
        lambda: service.decrypt_file(tmp_path / "in", tmp_path / "out"),
        lambda: service.backup(tmp_path / "backup"),
        lambda: service.import_legacy(tmp_path / "keys", "file"),
        lambda: service.change_password(PASSWORD, PASSWORD),
        lambda: service.rotate_recovery(PASSWORD),
        lambda: service.recover_legacy_file("id", tmp_path / "in", tmp_path / "out"),
    ]
    for operation in operations:
        with pytest.raises(AuthenticationError, match="not authorized"):
            operation()


def write_v1_fixture(path):
    """Historical v1 bytes, independently assembled from the documented old format."""
    database = sqlite3.connect(":memory:")
    database.executescript("""
        PRAGMA user_version=1;
        CREATE TABLE metadata(name TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE identity(key_id TEXT PRIMARY KEY,public_key BLOB NOT NULL,
                              private_key BLOB NOT NULL);
        CREATE TABLE items(record_id TEXT PRIMARY KEY,kind TEXT NOT NULL,label TEXT NOT NULL,
                           created_at TEXT NOT NULL,data_key BLOB NOT NULL,token TEXT);
    """)
    pair = KeyPair.generate()
    record = EnvelopeCodec(pair).encrypt_message("v1 history is retained")
    database.execute("INSERT INTO metadata VALUES ('password_hash',?)", (password_hash(PASSWORD),))
    database.execute(
        "INSERT INTO identity VALUES (?,?,?)", (pair.key_id, pair.public_der, pair.private_der)
    )
    database.execute(
        "INSERT INTO items VALUES (?,?,?,?,?,?)",
        (
            record.record_id,
            record.kind,
            record.label,
            "2026-10-26T00:00:00+00:00",
            record.data_key,
            record.token,
        ),
    )
    database.commit()
    salt, nonce = os.urandom(16), os.urandom(12)
    header = LEGACY_VAULT_MAGIC + salt
    payload = (
        header
        + nonce
        + AESGCM(derive_vault_key(PASSWORD, salt)).encrypt(nonce, database.serialize(), header)
    )
    database.close()
    path.write_bytes(payload)
    return payload, record.token, pair.key_id


def test_v1_upgrade_preserves_data_and_keeps_original_backup(tmp_path):
    path = tmp_path / "v1.svdb"
    original, token, identity = write_v1_fixture(path)
    with pytest.raises(FormatError, match="upgrade"):
        VaultService.login(path, USERNAME, PASSWORD)
    service, recovery = VaultService.upgrade(path, USERNAME, PASSWORD)
    try:
        assert service.decrypt_message(token) == "v1 history is retained"
        assert service.vault.identity().key_id == identity
        assert len(service.history()) == 1
    finally:
        service.close()
    assert path.read_bytes().startswith(VAULT_MAGIC)
    backups = list(tmp_path.glob("v1.before-account-*.svdb"))
    assert len(backups) == 1 and backups[0].read_bytes() == original
    VaultService.reset_password(path, USERNAME, recovery, "password after v1 upgrade")


def test_failed_v1_upgrade_preserves_original(tmp_path, monkeypatch):
    path = tmp_path / "v1.svdb"
    original, _, _ = write_v1_fixture(path)

    def fail(*_):
        raise OSError("injected save failure")

    monkeypatch.setattr("serein_vault.filesystem.os.replace", fail)
    with pytest.raises(OSError):
        VaultService.upgrade(path, USERNAME, PASSWORD)
    assert path.read_bytes() == original


def test_header_type_and_size_are_bounded(tmp_path):
    path = tmp_path / "bad.svdb"
    path.write_bytes(VAULT_MAGIC + struct.pack(">I", 0xFFFFFFFF) + b"x" * 100)
    with pytest.raises(FormatError):
        VaultService.login(path, USERNAME, PASSWORD)
    metadata = json.dumps({"salt": []}).encode()
    path.write_bytes(VAULT_MAGIC + struct.pack(">I", len(metadata)) + metadata + b"x" * 28)
    with pytest.raises(FormatError):
        VaultService.login(path, USERNAME, PASSWORD)
