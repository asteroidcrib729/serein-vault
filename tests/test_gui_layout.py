from serein_vault.service import VaultService

from .conftest import PASSWORD, USERNAME


def test_minimum_window_preserves_actions_and_status(app, tmp_path):
    app.service = VaultService.signup(tmp_path / "layout.svdb", USERNAME, PASSWORD)[0]
    app._show_workspace()
    app.geometry("840x660")
    app.deiconify()
    app.update()
    button = app.copy_output_button
    assert button.winfo_ismapped()
    assert button.winfo_y() + button.winfo_height() <= button.master.winfo_height()
    assert app._status_label.winfo_ismapped()
    app.notebook.select(2)
    app.update()
    history = app.nametowidget(app.notebook.select())

    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    buttons = [widget for widget in descendants(history) if widget.winfo_class() == "TButton"]
    assert len(buttons) == 4
    assert all(widget.winfo_ismapped() for widget in buttons)
    assert app._status_label.winfo_ismapped()
