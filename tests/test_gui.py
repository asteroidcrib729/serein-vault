import time
from pathlib import Path

from serein_vault.gui import default_vault_path

from .conftest import PASSWORD, USERNAME


def pump(app):
    deadline = time.monotonic() + 20
    while app._future is not None and time.monotonic() < deadline:
        app.update()
        time.sleep(0.01)
    assert app._future is None, "Worker did not finish"
    app.update_idletasks()


def test_tkinter_create_encrypt_decrypt_and_lock(app, tmp_path, monkeypatch):
    errors = []
    monkeypatch.setattr(
        "serein_vault.gui.messagebox.showerror", lambda *args, **kwargs: errors.append(args)
    )
    app.vault_path.set(str(tmp_path / "gui.svdb"))
    app.mode.set("signup")
    app._show_login()
    app.username_text.set(USERNAME)
    app.login_password.insert(0, PASSWORD)
    app.login_confirm.insert(0, PASSWORD)
    app._unlock()
    assert app._busy
    pump(app)
    assert app.service is not None, errors
    assert app._pending_recovery.startswith("SRK-")
    assert "disabled" in app.recovery_continue.state()
    app._finish_recovery()
    assert app._pending_recovery is not None
    app.recovery_saved.set(True)
    app._finish_recovery()
    assert app.title() == "Serein Vault"
    assert not any(entry.get() for entry in app._password_fields)
    text = "  hello from Tkinter 🌿\n"
    app.message_input.insert("1.0", text)
    app._message(False)
    pump(app)
    token = app.message_output.get("1.0", "end-1c")
    assert token.startswith("SEREIN1:")
    app._write_text(app.message_input, token)
    app._message(True)
    pump(app)
    assert app.message_output.get("1.0", "end-1c") == text
    assert len(app.history_tree.get_children()) == 1
    # Settings remain accessible at the minimum supported window size.
    app.geometry("840x660")
    notebook = next(w for w in app._container.winfo_children() if w.winfo_class() == "TNotebook")
    notebook.select(notebook.tabs()[-1])
    app.deiconify()
    app.update()
    canvas = app._scroll_canvas
    canvas.yview_moveto(1)
    app.update()
    assert canvas.yview()[1] >= 0.99
    app._lock_vault()
    pump(app)
    assert app.service is None
    assert not app.login_password.get()
    assert not errors


def test_gui_login_error_is_inline_and_does_not_open_workspace(app, tmp_path):
    from serein_vault.service import VaultService

    service, _ = VaultService.signup(tmp_path / "account.svdb", USERNAME, PASSWORD)
    service.close()
    app.vault_path.set(str(tmp_path / "account.svdb"))
    app.mode.set("login")
    app._show_login()
    app.username_text.set("somebody.else")
    app.login_password.insert(0, PASSWORD)
    app._unlock()
    pump(app)
    assert app.service is None
    assert app.status.get().startswith("Error:")
    assert not app.login_password.get()


def test_gui_password_reset_rotates_key_and_returns_to_login(app, tmp_path):
    from serein_vault.service import VaultService

    path = tmp_path / "reset.svdb"
    service, recovery = VaultService.signup(path, USERNAME, PASSWORD)
    token = service.encrypt_message("saved before GUI reset")
    service.close()
    app.vault_path.set(str(path))
    app.mode.set("reset")
    app._show_login()
    app.username_text.set(USERNAME)
    app.login_password.insert(0, "replacement GUI password")
    app.login_confirm.insert(0, "replacement GUI password")
    app.recovery_entry.insert(0, recovery)
    app._unlock()
    pump(app)
    assert app.service is None
    assert app._pending_recovery and app._pending_recovery != recovery
    app.recovery_saved.set(True)
    app._finish_recovery()
    assert app.mode.get() == "login"
    app.login_password.insert(0, "replacement GUI password")
    app._unlock()
    pump(app)
    assert app.service.decrypt_message(token) == "saved before GUI reset"


def test_text_tab_navigation_does_not_insert_characters(app, tmp_path):
    from serein_vault.service import VaultService

    app.service = VaultService.signup(tmp_path / "keyboard.svdb", USERNAME, PASSWORD)[0]
    app._show_workspace()
    app.message_input.insert("1.0", "private text")
    assert app._focus_next(app.message_input) == "break"
    assert app.message_input.get("1.0", "end-1c") == "private text"
    app._select_tab(1)
    assert app.notebook.index("current") == 1


def test_copy_and_lock_preserve_unrelated_clipboard_values(app, monkeypatch):
    clipboard = {"text": "unrelated text"}
    monkeypatch.setattr(app, "clipboard_get", lambda: clipboard["text"])
    monkeypatch.setattr(app, "clipboard_clear", lambda: clipboard.update(text=""))
    monkeypatch.setattr(app, "clipboard_append", lambda value: clipboard.update(text=value))
    app._clipboard_value = "previous application value"
    app._clear_clipboard()
    assert clipboard["text"] == "unrelated text"
    app._clipboard_value = "unrelated text"
    app._clear_clipboard()
    assert clipboard["text"] == ""


def test_inactivity_locks_vault_and_clears_displayed_secrets(app, tmp_path):
    from serein_vault.gui import AUTO_LOCK_SECONDS
    from serein_vault.service import VaultService

    app.service = VaultService.signup(tmp_path / "idle.svdb", USERNAME, PASSWORD)[0]
    app._show_workspace()
    old_input = app.message_input
    app.message_input.insert("1.0", "sensitive displayed message")
    app._activity = time.monotonic() - AUTO_LOCK_SECONDS - 1
    deadline = time.monotonic() + 10
    while app.service is not None and time.monotonic() < deadline:
        app.update()
        time.sleep(0.01)
    assert app.service is None
    assert not old_input.winfo_exists()
    assert not app.login_password.get()


def test_default_location_is_not_working_directory(tmp_path, monkeypatch):
    original = default_vault_path()
    monkeypatch.chdir(tmp_path)
    assert default_vault_path() == original
    assert default_vault_path().is_absolute()
    assert default_vault_path().parent != Path.cwd()


def test_multiple_tk_instances_own_their_images_and_form_state(app):
    from serein_vault.gui import VaultApp

    second = VaultApp()
    try:
        second.withdraw()
        assert second._icon.tk is second.tk
        for variable in (second.vault_path, second.mode, second.username_text, second.status):
            assert variable._tk is second.tk
        second.username_text.set("second.user")
        assert second.login_username.get() == "second.user"
        assert app.username_text.get() == ""
    finally:
        second.close()
