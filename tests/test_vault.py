import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from serein_vault.errors import AuthenticationError, FormatError, VaultBusyError, VaultError
from serein_vault.service import VaultService
from serein_vault.storage import VAULT_MAGIC, EncryptedVault

from .conftest import PASSWORD, USERNAME


def test_database_and_every_secret_are_encrypted(service):
    token = service.encrypt_message("private message content")
    pair = service.vault.identity()
    payload = service.vault.path.read_bytes()
    assert payload.startswith(VAULT_MAGIC)
    for secret in (
        b"SQLite format 3",
        b"private message content",
        b"CREATE TABLE",
        b"$argon2id$",
        pair.private_der,
        pair.public_der,
        token.encode(),
        PASSWORD.encode(),
    ):
        assert secret not in payload
    row = service.vault.connection.execute(
        "SELECT value FROM metadata WHERE name='password_hash'"
    ).fetchone()
    assert row[0].startswith("$argon2id$")
    assert service.vault.connection.execute("PRAGMA database_list").fetchone()[2] == ""
    assert service.vault.connection.execute("PRAGMA temp_store").fetchone()[0] == 2
    with sqlite3.connect(service.vault.path) as database, pytest.raises(sqlite3.DatabaseError):
        database.execute("SELECT * FROM metadata")


def test_message_history_survives_reopen_and_retains_exact_text(service):
    texts = ["  first\n\t", "second", "مرحبا 🌿\n第三条"]
    tokens = [service.encrypt_message(text) for text in texts]
    path = service.vault.path
    service.close()
    reopened = VaultService.login(path, USERNAME, PASSWORD)
    try:
        assert len(reopened.history()) == 3
        assert [reopened.decrypt_message(token) for token in tokens] == texts
        for record in reopened.history():
            assert reopened.history_message(record["record_id"], decrypt=True) in texts
    finally:
        reopened.close()


def test_wrong_password_and_corrupt_vault_do_not_modify_data(service):
    path = service.vault.path
    service.close()
    original = path.read_bytes()
    with pytest.raises(AuthenticationError):
        EncryptedVault.open(path, USERNAME, "another wrong password")
    assert path.read_bytes() == original
    damaged = original[:-1] + bytes([original[-1] ^ 1])
    path.write_bytes(damaged)
    with pytest.raises(AuthenticationError):
        EncryptedVault.open(path, USERNAME, PASSWORD)
    assert path.read_bytes() == damaged


@pytest.mark.parametrize("payload", [b"", b"SQLite format 3\x00", b"SVDB\x00\xff\r\n" + b"x" * 100])
def test_malformed_vault_fails_cleanly(tmp_path, payload):
    path = tmp_path / "bad.svdb"
    path.write_bytes(payload)
    with pytest.raises(FormatError):
        EncryptedVault.open(path, USERNAME, PASSWORD)


def test_password_change_preserves_identity_and_all_records(service):
    token = service.encrypt_message("before change")
    identity = service.vault.identity().key_id
    path = service.vault.path
    new = "  新しい пароль 🌿 with spaces  "
    service.change_password(PASSWORD, new)
    assert service.vault.identity().key_id == identity
    assert service.decrypt_message(token) == "before change"
    service.close()
    with pytest.raises(AuthenticationError):
        VaultService.login(path, USERNAME, PASSWORD)
    reopened = VaultService.login(path, USERNAME, new)
    try:
        assert reopened.decrypt_message(token) == "before change"
        assert len(reopened.history()) == 1
    finally:
        reopened.close()


def test_password_change_rejects_wrong_current(service):
    before = service.vault.path.read_bytes()
    with pytest.raises(AuthenticationError):
        service.change_password("incorrect current password", "new password of sufficient length")
    assert service.vault.path.read_bytes() == before


@pytest.mark.parametrize(
    "password",
    ["short", " " * 20, "x" * 1025, "invalid\ud800password"],
    ids=["short", "whitespace", "oversized", "invalid-unicode"],
)
def test_consistent_password_policy(tmp_path, password):
    with pytest.raises(VaultError):
        EncryptedVault.create(tmp_path / "invalid.svdb", USERNAME, password)
    assert not (tmp_path / "invalid.svdb").exists()


def test_existing_vault_cannot_be_replaced(service):
    with pytest.raises((VaultBusyError, VaultError)):
        EncryptedVault.create(service.vault.path, USERNAME, PASSWORD)
    assert service.vault.is_open


def test_competing_process_cannot_open_vault(service):
    code = (
        "import sys; from pathlib import Path; "
        "from serein_vault.storage import EncryptedVault; "
        "from serein_vault.errors import VaultBusyError\n"
        "try: EncryptedVault.open(Path(sys.argv[1]), 'test.user', 'a long test password')\n"
        "except VaultBusyError: sys.exit(0)\n"
        "sys.exit(1)\n"
    )
    process = subprocess.run(
        [sys.executable, "-c", code, str(service.vault.path)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert process.returncode == 0, process.stderr


def test_failed_save_rolls_back_memory_and_disk(service, monkeypatch):
    service.encrypt_message("retained")
    original = service.vault.path.read_bytes()
    original_count = len(service.history())
    with monkeypatch.context() as patcher:
        patcher.setattr(
            "serein_vault.filesystem.os.replace",
            lambda *_: (_ for _ in ()).throw(OSError("disk failure")),
        )
        with pytest.raises(OSError):
            service.encrypt_message("must not be committed")
    assert service.vault.path.read_bytes() == original
    assert len(service.history()) == original_count
    assert not list(service.vault.path.parent.glob(".serein-*.tmp"))
    assert service.decrypt_message(service.encrypt_message("after failure")) == "after failure"


def test_failed_password_save_retains_old_password(service, monkeypatch):
    path = service.vault.path
    original = path.read_bytes()
    with monkeypatch.context() as patcher:
        patcher.setattr(
            "serein_vault.filesystem.os.replace",
            lambda *_: (_ for _ in ()).throw(OSError("disk failure")),
        )
        with pytest.raises(OSError):
            service.change_password(PASSWORD, "replacement password value")
    assert path.read_bytes() == original
    token = service.encrypt_message("still usable")
    service.close()
    reopened = VaultService.login(path, USERNAME, PASSWORD)
    try:
        assert reopened.decrypt_message(token) == "still usable"
    finally:
        reopened.close()


def test_external_modification_is_not_overwritten(service):
    path = service.vault.path
    payload = path.read_bytes()
    altered = payload[:-1] + bytes([payload[-1] ^ 1])
    path.write_bytes(altered)
    with pytest.raises(VaultError, match="changed outside"):
        service.encrypt_message("not saved")
    assert path.read_bytes() == altered
    assert not service.history()


def test_backup_can_recover_messages_and_old_backups_keep_old_password(service, tmp_path):
    token = service.encrypt_message("backup recovery")
    backup = tmp_path / "backup.svdb"
    service.backup(backup)
    with pytest.raises(VaultError):
        service.backup(backup)
    service.change_password(PASSWORD, "a replacement password")
    restored = VaultService.login(backup, USERNAME, PASSWORD)
    try:
        assert restored.decrypt_message(token) == "backup recovery"
    finally:
        restored.close()


def test_locked_service_rejects_operations(service):
    service.close()
    with pytest.raises(VaultError, match="locked"):
        service.encrypt_message("no access")


def test_database_size_limit_rolls_back_new_record(service, monkeypatch):
    before = service.vault.path.read_bytes()
    monkeypatch.setattr("serein_vault.storage.MAX_DATABASE_BYTES", 1)
    with pytest.raises(VaultError, match="64 MiB"):
        service.encrypt_message("record beyond the limit")
    assert not service.history()
    assert service.vault.path.read_bytes() == before


def test_vault_path_is_independent_of_working_directory(service, tmp_path, monkeypatch):
    path = service.vault.path
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    service.encrypt_message("same vault")
    assert service.vault.path == path
    assert not list(Path.cwd().glob("*.svdb"))
