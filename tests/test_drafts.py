"""Installer drafts require clean, source-matching evidence and remain unpublished."""

import hashlib
import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from .test_release_verification import verifier

SHA = "1" * 40


@pytest.fixture
def publisher_module(monkeypatch):
    folder = Path(__file__).parents[1] / "packaging"
    monkeypatch.syspath_prepend(str(folder))
    spec = importlib.util.spec_from_file_location("draft_publisher", folder / "create_draft.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def bundle(tmp_path):
    installer = "SereinVault-1.2.0-windows-x64-setup.exe"
    (tmp_path / installer).write_bytes(b"synthetic installer")
    for name in ("LICENSE", "AUTHORS.md", "Analysis-00.toc"):
        (tmp_path / name).write_text("Synthetic fixture", encoding="utf-8")
    for name in ("frozen-smoke.json", "installed-smoke.json", "installer-validation.json"):
        (tmp_path / name).write_text('{"ok": true}', encoding="utf-8")
    metadata = {
        "version": "1.2.0",
        "git_head": SHA,
        "dirty_worktree": False,
        "format": "exe",
        "artifact_sha256": {installer: hashlib.sha256(b"synthetic installer").hexdigest()},
    }
    (tmp_path / "provenance.json").write_text(json.dumps(metadata), encoding="utf-8")
    verifier.refresh(tmp_path)
    return tmp_path


def test_verified_bundle_is_accepted(publisher_module, bundle):
    version, files = publisher_module.validate_bundle(bundle, SHA, "exe")
    assert version == "1.2.0"
    assert len(files) == 9


@pytest.mark.parametrize(
    "field,value", [("git_head", "2" * 40), ("dirty_worktree", True), ("format", "msix")]
)
def test_wrong_source_dirty_or_wrong_format_is_rejected(publisher_module, bundle, field, value):
    path = bundle / "provenance.json"
    metadata = json.loads(path.read_text())
    metadata[field] = value
    path.write_text(json.dumps(metadata))
    verifier.refresh(bundle)
    with pytest.raises(ValueError, match="clean build"):
        publisher_module.validate_bundle(bundle, SHA, "exe")


def test_missing_installation_evidence_is_rejected(publisher_module, bundle):
    (bundle / "installed-smoke.json").unlink()
    verifier.refresh(bundle)
    with pytest.raises(ValueError, match="evidence is missing"):
        publisher_module.validate_bundle(bundle, SHA, "exe")


def test_changed_installer_is_rejected(publisher_module, bundle):
    (bundle / "SereinVault-1.2.0-windows-x64-setup.exe").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        publisher_module.validate_bundle(bundle, SHA, "exe")


def test_unlisted_asset_is_rejected(publisher_module, bundle):
    (bundle / "unexpected.txt").write_text("not covered")
    with pytest.raises(ValueError, match="every asset"):
        publisher_module.validate_bundle(bundle, SHA, "exe")


def test_failed_smoke_is_rejected(publisher_module, bundle):
    (bundle / "installed-smoke.json").write_text('{"ok": false}')
    verifier.refresh(bundle)
    with pytest.raises(ValueError, match="Smoke verification"):
        publisher_module.validate_bundle(bundle, SHA, "exe")


def test_publish_keeps_draft_and_verifies_uploaded_bytes(publisher_module, bundle, monkeypatch):
    publisher = publisher_module.DraftPublisher("example/project", "synthetic-token")
    assets, created = [], []

    def request(method, url, data=None, *, binary=False):
        if method == "POST" and not binary:
            created.append(data)
            return {"id": 17, "draft": True, "target_commitish": SHA}
        if binary:
            asset = {
                "name": parse_qs(urlparse(url).query)["name"][0],
                "size": len(data),
                "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
            }
            assets.append(asset)
            return asset
        return {
            "draft": True,
            "assets": assets,
            "html_url": "https://github.com/example/project/releases/17",
        }

    monkeypatch.setattr(publisher, "request", request)
    assert publisher.publish(bundle, SHA, "exe", "123", "1").endswith("/17")
    assert created[0]["draft"] is True
    assert created[0]["target_commitish"] == SHA
    assert created[0]["tag_name"] == f"preview-exe-{SHA[:12]}-123-1"
    assert {a["name"] for a in assets} == {p.name for p in bundle.iterdir()}


@pytest.mark.parametrize(
    "response",
    [
        {"id": 17, "draft": False, "target_commitish": SHA},
        {"id": 17, "draft": True, "target_commitish": "2" * 40},
    ],
)
def test_publish_rejects_published_or_wrong_target_response(
    publisher_module, bundle, monkeypatch, response
):
    publisher = publisher_module.DraftPublisher("example/project", "synthetic-token")
    monkeypatch.setattr(publisher, "request", lambda *args, **kwargs: response)
    with pytest.raises(ValueError, match="unpublished source-pinned draft"):
        publisher.publish(bundle, SHA, "exe", "123", "1")


def test_publish_rejects_wrong_uploaded_digest(publisher_module, bundle, monkeypatch):
    publisher = publisher_module.DraftPublisher("example/project", "synthetic-token")

    def request(method, url, data=None, *, binary=False):
        if not binary:
            return {"id": 17, "draft": True, "target_commitish": SHA}
        return {"digest": "sha256:" + "0" * 64, "size": len(data)}

    monkeypatch.setattr(publisher, "request", request)
    with pytest.raises(ValueError, match="Uploaded asset verification"):
        publisher.publish(bundle, SHA, "exe", "123", "1")
