import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import pytest

from serein_vault.gui import COLORS, VaultApp
from serein_vault.service import VaultService

from .conftest import PASSWORD, USERNAME
from .test_gui import pump


def test_native_touchpad_and_small_wheel_deltas_scroll_forms(app):
    app.geometry("840x660")
    app.deiconify()
    app.update()
    canvas = app._scroll_canvas
    # Force real overflow independently of platform font metrics and display DPI.
    form = canvas.nametowidget(canvas.itemcget(canvas.find_all()[0], "window"))
    ttk.Label(form, text="Scroll fixture\n" * 40).pack(anchor="w")
    app.update()
    canvas.yview_moveto(0)
    app.update()
    assert canvas.bbox("all")[3] > canvas.winfo_height()
    entry = app.login_username
    assert app._scrolling.TAG in entry.bindtags()
    if not app._scrolling.precise:
        pytest.skip("TouchpadScroll is a Tk 9 event; Tk 8.6 uses MouseWheel")
    start = canvas.yview()[0]
    entry.event_generate("<TouchpadScroll>", delta=65506)  # Packed (x=0, y=-30).
    app.update()
    assert canvas.yview()[0] > start
    canvas.yview_moveto(0)
    entry.event_generate("<MouseWheel>", delta=-1)
    entry.event_generate("<MouseWheel>", delta=-1)
    entry.event_generate("<MouseWheel>", delta=-1)
    app.update()
    assert canvas.yview()[0] > 0
    before = canvas.yview()
    entry.event_generate("<MouseWheel>", delta=0)
    app.update()
    assert canvas.yview() == before


def test_dark_theme_and_native_text_scrolling(app, tmp_path):
    app.service = VaultService.signup(tmp_path / "native.svdb", USERNAME, PASSWORD)[0]
    app._show_workspace()
    app.deiconify()
    app.update()
    assert app.message_input.cget("background") == COLORS["input"]
    assert app._scrolling.target(SimpleNamespace(widget=app.message_input)) is None
    app.message_input.insert("1.0", "line\n" * 100)
    app.message_input.yview_moveto(0)
    app.message_input.event_generate("<MouseWheel>", delta=-120)
    app.update()
    assert app.message_input.yview()[0] > 0


def test_gui_labels_filter_and_health(app, tmp_path):
    app.service = VaultService.signup(tmp_path / "labels.svdb", USERNAME, PASSWORD)[0]
    app._show_workspace()
    app.message_input.insert("1.0", "remember me")
    app.message_label.set("First note")
    app._message(False)
    pump(app)
    app.history_query.set("missing")
    assert not app.history_tree.get_children()
    app.history_query.set("FIRST")
    assert len(app.history_tree.get_children()) == 1
    app._check_health()
    pump(app)
    assert "Integrity: ok" in app.health_text.get()


def test_worker_progress_and_cancel_are_responsive(app, tmp_path, monkeypatch):
    app.service = VaultService.signup(tmp_path / "progress.svdb", USERNAME, PASSWORD)[0]
    app._show_workspace()
    app.file_source.set(str(tmp_path / "input"))
    app.file_destination.set(str(tmp_path / "output"))

    def operation(source, destination, control):
        for number in range(100):
            control.report(number, 100)
            time.sleep(0.01)
        return destination

    monkeypatch.setattr(app.service, "encrypt_file", operation)
    app._start_file()
    deadline = time.monotonic() + 2
    while float(app._progress["value"]) == 0 and time.monotonic() < deadline:
        app.update()
        time.sleep(0.01)
    assert float(app._progress["value"]) > 0
    assert app._progress_updates.qsize() <= 1
    app._cancel_operation()
    pump(app)
    assert "Cancelled" in app.status.get()
    assert not app._busy
    assert app._operation_control is None


@pytest.mark.parametrize("scale", [1.25, 1.5, 2.0])
def test_scaled_window_keeps_actions_reachable(scale, tmp_path):
    try:
        root = VaultApp(display_scale=scale)
    except tk.TclError as exc:
        if not any(
            message in str(exc).lower()
            for message in ("no display name", "connect to display", "cannot open display")
        ):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    try:
        root.geometry("840x660")
        root.service = VaultService.signup(tmp_path / f"dpi-{scale}.svdb", USERNAME, PASSWORD)[0]
        root._show_workspace()
        root.update()
        button = root.copy_output_button
        button.focus_force()
        root.update()
        assert root._status_label.winfo_ismapped()
        assert button.winfo_rooty() >= root.winfo_rooty()
        assert (
            button.winfo_rooty() + button.winfo_height() <= root.winfo_rooty() + root.winfo_height()
        )
        root.notebook.select(3)
        root.change_entries[-1].focus_force()
        root.update()
        entry = root.change_entries[-1]
        assert entry.winfo_rooty() + entry.winfo_height() < root._status_label.winfo_rooty()
    finally:
        root.close()


def test_real_file_workflow_and_authentication_failure(app, tmp_path):
    app.service = VaultService.signup(tmp_path / "files.svdb", USERNAME, PASSWORD)[0]
    app._show_workspace()
    source = tmp_path / "original.txt"
    source.write_bytes(b"GUI file workflow\n" * 10000)
    encrypted = tmp_path / "encrypted.svault"
    app.file_source.set(str(source))
    app.file_destination.set(str(encrypted))
    app._start_file()
    pump(app)
    assert encrypted.exists()
    app.file_mode.set("decrypt")
    app.file_source.set(str(encrypted))
    recovered = tmp_path / "recovered.txt"
    app.file_destination.set(str(recovered))
    app._start_file()
    pump(app)
    assert recovered.read_bytes() == source.read_bytes()
    damaged = bytearray(encrypted.read_bytes())
    damaged[-1] ^= 1
    encrypted.write_bytes(damaged)
    rejected = tmp_path / "rejected.txt"
    app.file_destination.set(str(rejected))
    app._start_file()
    pump(app)
    assert app.status.get().startswith("Error:")
    assert not rejected.exists()
    assert source.read_bytes() == recovered.read_bytes()


def test_real_tab_event_moves_focus_without_inserting_text(app, tmp_path):
    app.service = VaultService.signup(tmp_path / "tab.svdb", USERNAME, PASSWORD)[0]
    app._show_workspace()
    app.deiconify()
    app.message_input.insert("1.0", "sensitive message")
    app.message_input.focus_force()
    app.update()
    app.message_input.event_generate("<Tab>")
    app.update()
    assert app.focus_get() != app.message_input
    assert app.message_input.get("1.0", "end-1c") == "sensitive message"
