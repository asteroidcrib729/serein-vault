"""Explicit installer probe using only disposable synthetic data."""

import json
import platform
import tempfile
from pathlib import Path

from . import __version__
from .gui import COLORS, VaultApp
from .service import VaultService


def run_smoke(report: Path):
    with tempfile.TemporaryDirectory(prefix="serein-smoke-") as directory:
        root = Path(directory)
        password = "Synthetic installer test only"
        service, _ = VaultService.signup(root / "test.svdb", "installer.test", password)
        app = None
        try:
            token = service.encrypt_message("Installer roundtrip ✓", "Smoke label")
            assert service.decrypt_message(token) == "Installer roundtrip ✓"
            source = root / "original.txt"
            source.write_bytes(b"synthetic file\n" * 100)
            service.encrypt_file(source, root / "encrypted.svault")
            service.decrypt_file(root / "encrypted.svault", root / "recovered.txt")
            assert source.read_bytes() == (root / "recovered.txt").read_bytes()
            assert service.health()["integrity"] == "ok"
            service.backup(root / "backup.svdb")
            app = VaultApp()
            app.service = service
            app.vault_path.set(str(service.vault.path))
            app._show_workspace()
            app.update()
            assert app.copy_output_button.winfo_ismapped()
            assert app._scrolling.precise or not str(app.tk.call("info", "patchlevel")).startswith(
                "9"
            )
            result = {
                "ok": True,
                "version": __version__,
                "python": platform.python_version(),
                "tk": str(app.tk.call("info", "patchlevel")),
                "theme": "dark",
                "surface": COLORS["surface"],
                "message_roundtrip": True,
                "file_roundtrip": True,
                "health": True,
                "backup": True,
                "real_tk_workspace": True,
                "synthetic_data_only": True,
            }
        finally:
            if app is not None:
                app.close()
            else:
                service.close()
        restored = VaultService.login(root / "backup.svdb", "installer.test", password)
        try:
            assert restored.decrypt_message(token) == "Installer roundtrip ✓"
            result["backup_restore"] = True
        finally:
            restored.close()
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
