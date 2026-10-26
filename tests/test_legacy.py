import base64
import json

import pytest
from cryptography.fernet import Fernet

from serein_vault.errors import AuthenticationError, FormatError


def test_import_and_recover_legacy_messages_keeps_all_records(service, tmp_path):
    data = {}
    for text in ("  old message\n", "older message"):
        key = Fernet.generate_key()
        token = base64.b64encode(Fernet(key).encrypt(text.encode())).decode()
        data[token] = key.decode()
    source = tmp_path / "Message_Keys.json"
    source.write_text(json.dumps(data, indent=2))
    before = source.read_bytes()
    service.import_legacy(source, "message")
    service.encrypt_message("new message")
    recovered = [
        service.history_message(row["record_id"], decrypt=True)
        for row in service.history()
        if row["kind"] == "legacy_message"
    ]
    assert set(recovered) == {"  old message\n", "older message"}
    assert source.read_bytes() == before


def test_legacy_file_can_move_and_recovery_preserves_ciphertext(service, tmp_path):
    key = Fernet.generate_key()
    source = tmp_path / "File_Keys.json"
    source.write_text(json.dumps({"C:/old/location/file.txt": key.decode()}, indent=4))
    service.import_legacy(source, "file")
    record = service.history()[0]
    moved = tmp_path / "renamed-file.bin"
    ciphertext = Fernet(key).encrypt(b"old file data")
    moved.write_bytes(ciphertext)
    recovered = tmp_path / "recovered.txt"
    service.recover_legacy_file(record["record_id"], moved, recovered)
    assert recovered.read_bytes() == b"old file data"
    assert moved.read_bytes() == ciphertext


def test_invalid_legacy_batch_is_not_partially_imported(service, tmp_path):
    source = tmp_path / "File_Keys.json"
    source.write_text(json.dumps({"valid": Fernet.generate_key().decode(), "invalid": "bad-key"}))
    with pytest.raises(FormatError):
        service.import_legacy(source, "file")
    assert not service.history()


@pytest.mark.parametrize("raw", ["[]", "{}", '{"a":"x","a":"y"}', "not json"])
def test_malformed_legacy_json_is_rejected(service, tmp_path, raw):
    source = tmp_path / "bad.json"
    source.write_text(raw)
    with pytest.raises(FormatError):
        service.import_legacy(source, "message")


def test_legacy_hash_is_archived_only_inside_encrypted_database(service, tmp_path):
    path = tmp_path / "Pass.txt"
    legacy_hash = "1a" * 64
    path.write_text(legacy_hash)
    service.import_legacy(path, "password")
    row = service.vault.connection.execute(
        "SELECT value FROM metadata WHERE name='legacy_password_hash'"
    ).fetchone()
    assert row[0] == legacy_hash
    assert legacy_hash.encode() not in service.vault.path.read_bytes()
    assert path.read_text() == legacy_hash


def test_wrong_legacy_key_never_creates_recovered_file(service, tmp_path):
    source = tmp_path / "File_Keys.json"
    source.write_text(json.dumps({"original": Fernet.generate_key().decode()}))
    service.import_legacy(source, "file")
    encrypted = tmp_path / "encrypted"
    encrypted.write_bytes(Fernet(Fernet.generate_key()).encrypt(b"data"))
    output = tmp_path / "output"
    with pytest.raises(AuthenticationError):
        service.recover_legacy_file(service.history()[0]["record_id"], encrypted, output)
    assert not output.exists()
