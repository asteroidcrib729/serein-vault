import time
import tkinter as tk

import pytest

from serein_vault.gui import VaultApp
from serein_vault.service import VaultService

USERNAME = "test.user"
PASSWORD = "  Correct horse 🌿 battery  "


@pytest.fixture
def service(tmp_path):
    instance = VaultService.signup(tmp_path / "vault.svdb", USERNAME, PASSWORD)[0]
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture
def app():
    try:
        root = VaultApp()
    except tk.TclError as exc:
        if not any(
            message in str(exc).lower()
            for message in ("no display name", "connect to display", "cannot open display")
        ):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    try:
        yield root
    finally:
        if root.winfo_exists():
            root.close()
            deadline = time.monotonic() + 20
            while root._busy and time.monotonic() < deadline:
                root.update()
                time.sleep(0.01)
