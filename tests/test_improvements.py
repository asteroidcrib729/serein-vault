import hashlib

import pytest

from serein_vault.crypto import CHUNK_SIZE, MESSAGE_PREFIX, encode64
from serein_vault.errors import OperationCancelled, VaultError
from serein_vault.operations import OperationControl
from serein_vault.service import VaultService

from .conftest import PASSWORD, USERNAME


def test_label_search_rename_backup_and_health(service, tmp_path):
    token = service.encrypt_message("Keep exact plaintext\n", "Straße 🌿")
    item = service.history("STRASSE")[0]
    assert service.history("%")[0:] == []  # Search is literal, not SQL LIKE.
    before = service.vault.path.read_bytes()
    assert service.health()["records"] == 1
    assert service.vault.path.read_bytes() == before
    assert "Straße".encode() not in before
    service.label_message(item["record_id"], "Changed label")
    assert not service.history("strasse")
    assert service.history("changed")[0]["record_id"] == item["record_id"]
    service.backup(tmp_path / "backup.svdb")
    restored = VaultService.login(tmp_path / "backup.svdb", USERNAME, PASSWORD)
    try:
        assert restored.history("changed")[0]["label"] == "Changed label"
        assert restored.decrypt_message(token) == "Keep exact plaintext\n"
    finally:
        restored.close()


@pytest.mark.parametrize("label", ["x" * 81, "two\nlines", "null\0label", "\ud800", None])
def test_bad_label_does_not_mutate_vault(service, label):
    before = service.vault.path.read_bytes()
    with pytest.raises(VaultError):
        service.encrypt_message("secret", label)
    assert service.vault.path.read_bytes() == before
    assert service.history() == []


def test_file_records_cannot_be_relabelled(service, tmp_path):
    source = tmp_path / "file"
    source.write_bytes(b"abc")
    service.encrypt_file(source, tmp_path / "file.svault")
    record = service.history()[0]
    before = service.vault.path.read_bytes()
    with pytest.raises(VaultError, match="Select a message"):
        service.label_message(record["record_id"], "new")
    assert service.vault.path.read_bytes() == before


def test_new_operations_require_open_authorized_session(service):
    service.close()
    for operation in (
        service.health,
        lambda: service.history("query"),
        lambda: service.label_message("id", "label"),
    ):
        with pytest.raises(VaultError, match="locked"):
            operation()


@pytest.mark.parametrize("decrypt", [False, True])
@pytest.mark.parametrize("when", ["before", "middle", "last"])
def test_cancellation_never_publishes_output(service, tmp_path, decrypt, when):
    original = tmp_path / "original"
    original.write_bytes(b"z" * (CHUNK_SIZE * 3 + 17))
    source = original
    if decrypt:
        source = tmp_path / "ciphertext"
        service.encrypt_file(original, source)
    digest = hashlib.sha256(source.read_bytes()).digest()
    output = tmp_path / "cancelled-output"
    control = OperationControl()

    def progress(done, total):
        if (when == "middle" and done >= CHUNK_SIZE) or (when == "last" and done == total):
            control.cancel()

    control.progress = progress
    if when == "before":
        control.cancel()
    operation = service.decrypt_file if decrypt else service.encrypt_file
    with pytest.raises(OperationCancelled):
        operation(source, output, control)
    assert not output.exists()
    assert hashlib.sha256(source.read_bytes()).digest() == digest
    assert not list(tmp_path.glob("*.tmp"))
    assert service.health()["integrity"] == "ok"


def test_progress_roundtrip_is_monotonic_and_complete(service, tmp_path):
    source = tmp_path / "input"
    source.write_bytes(b"a" * (CHUNK_SIZE * 2 + 37))
    for operation, input_path, output_path in (
        (service.encrypt_file, source, tmp_path / "encrypted"),
        (service.decrypt_file, tmp_path / "encrypted", tmp_path / "recovered"),
    ):
        updates = []
        operation(
            input_path,
            output_path,
            OperationControl(lambda n, total, updates=updates: updates.append((n, total))),
        )
        assert updates[0] == (0, source.stat().st_size)
        assert updates[-1] == (source.stat().st_size, source.stat().st_size)
        assert updates == sorted(updates)
    assert (tmp_path / "recovered").read_bytes() == source.read_bytes()


def test_cancel_after_record_saved_keeps_vault_usable(service, tmp_path, monkeypatch):
    source = tmp_path / "original"
    source.write_bytes(b"retained input")
    control = OperationControl()
    add = service.vault.add_record

    def save_then_cancel(record):
        add(record)
        control.cancel()

    monkeypatch.setattr(service.vault, "add_record", save_then_cancel)
    with pytest.raises(OperationCancelled):
        service.encrypt_file(source, tmp_path / "output", control)
    assert not (tmp_path / "output").exists()
    assert len(service.history()) == 1  # Harmless saved recovery key, no published file.
    assert service.health()["integrity"] == "ok"


def test_failed_label_save_rolls_back_metadata(service, monkeypatch):
    service.encrypt_message("secret", "Original label")
    record_id = service.history()[0]["record_id"]
    before = service.vault.path.read_bytes()
    with monkeypatch.context() as patcher:
        patcher.setattr(
            "serein_vault.filesystem.os.replace",
            lambda *_: (_ for _ in ()).throw(OSError("disk failure")),
        )
        with pytest.raises(OSError):
            service.label_message(record_id, "Unsaved label")
    assert service.history()[0]["label"] == "Original label"
    assert service.vault.path.read_bytes() == before


def test_deterministic_malformed_envelopes_are_bounded_and_do_not_mutate(service):
    import random

    generator = random.Random(1742)
    before = service.vault.path.read_bytes()
    for length in range(128):
        token = MESSAGE_PREFIX + encode64(generator.randbytes(length))
        with pytest.raises(VaultError):
            service.decrypt_message(token)
    assert service.vault.path.read_bytes() == before
    assert service.history() == []
