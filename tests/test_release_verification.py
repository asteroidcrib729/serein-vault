"""Corrupt package fixtures exercise the actual artifact verifier."""

import base64
import hashlib
import importlib.util
import zipfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "release_verifier", Path(__file__).parents[1] / "packaging" / "verify_release.py"
)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


@pytest.mark.parametrize("corrupt", [False, True])
def test_msix_blocks_detect_changed_payload(tmp_path, corrupt):
    content = b"original data" * 7000
    blocks = "".join(
        '<Block Hash="'
        + base64.b64encode(hashlib.sha256(content[i : i + 65536]).digest()).decode()
        + '"/>'
        for i in range(0, len(content), 65536)
    )
    manifest = (
        '<BlockMap xmlns="http://schemas.microsoft.com/appx/2010/blockmap" '
        'HashMethod="http://www.w3.org/2001/04/xmlenc#sha256">'
        f'<File Name="payload.bin" Size="{len(content)}">{blocks}</File></BlockMap>'
    )
    package = tmp_path / "test.msix"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("AppxBlockMap.xml", manifest)
        archive.writestr("payload.bin", b"X" + content[1:] if corrupt else content)
    if corrupt:
        with pytest.raises(ValueError, match="block hash mismatch"):
            verifier.verify_msix(package)
    else:
        verifier.verify_msix(package)


def test_release_checksum_detects_artifact_changes(tmp_path):
    artifact = tmp_path / "installer.exe"
    artifact.write_bytes(b"synthetic installer")
    verifier.refresh(tmp_path)
    verifier.verify(tmp_path)
    artifact.write_bytes(b"changed installer")
    with pytest.raises(ValueError, match="checksum mismatch"):
        verifier.verify(tmp_path)
