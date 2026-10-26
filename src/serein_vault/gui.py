"""Tkinter/ttk desktop UI. Workers never access Tk objects."""

import contextlib
import os
import sys
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Empty, Full, Queue
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import __version__
from .desktop import FormScrolling, dark_titlebar, enable_windows_dpi
from .errors import VaultError
from .operations import OperationControl
from .service import VaultService

AUTO_LOCK_SECONDS = 600
CLIPBOARD_SECONDS = 45
COLORS = {
    "page": "#09111f",
    "surface": "#121c2c",
    "text": "#e7eef8",
    "muted": "#b5c4d8",
    "accent": "#5eead4",
    "accent_active": "#99f6e4",
    "accent_text": "#042f2e",
    "input": "#0e1726",
    "focus": "#93c5fd",
    "border": "#647c9a",
    "selection": "#244d58",
    "selection_text": "#e6fffb",
    "error": "#ffb4b4",
}


def default_vault_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "SereinVault" / "vault.svdb"


class VaultApp(tk.Tk):
    def __init__(self, *, display_scale=None):
        enable_windows_dpi()
        super().__init__()
        if display_scale is not None:
            self.tk.call("tk", "scaling", display_scale * 96 / 72)
        self.display_scale = float(self.tk.call("tk", "scaling")) / (96 / 72)
        self.title("Serein Vault")
        width = min(round(1040 * self.display_scale), self.winfo_screenwidth() - 96)
        height = min(round(780 * self.display_scale), self.winfo_screenheight() - 120)
        self.geometry(f"{max(840, width)}x{max(660, height)}")
        self.minsize(840, 660)
        self.configure(background=COLORS["page"])
        self.service: VaultService | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="serein-vault")
        self._future = None
        self._success = None
        self._busy = False
        self._closing = False
        self._activity = time.monotonic()
        self._clipboard_value = None
        self._clipboard_expires = 0
        self._controls = []
        self._texts = []
        self._password_fields = []
        self.vault_path = tk.StringVar(master=self, value=str(default_vault_path()))
        self.mode = tk.StringVar(
            master=self, value="login" if default_vault_path().exists() else "signup"
        )
        self.username_text = tk.StringVar(master=self)
        self.status = tk.StringVar(
            master=self, value="Welcome. Create an account or log in to your vault."
        )
        self._pending_recovery = None
        self._operation_control = None
        self._progress_updates = Queue(maxsize=1)
        self._scrolling = FormScrolling(self, self._touch)
        self._style()
        assets = Path(__file__).parent / "assets"
        self._icon = None
        if sys.platform == "win32" and (assets / "SereinVault.ico").exists():
            # Use Windows' native multi-resolution loader. Repeated Tk PNG decoder
            # initialization can fail with an empty TclError on hosted Windows.
            self.iconbitmap(default=str(assets / "SereinVault.ico"))
        elif (assets / "icon.png").exists():
            self._icon = tk.PhotoImage(master=self, file=assets / "icon.png")
            self.iconphoto(True, self._icon)
        self._container = ttk.Frame(self, padding=28)
        self._container.pack(fill="both", expand=True, padx=12, pady=12)
        self.bind_all("<KeyPress>", self._touch, add=True)
        self.bind_all("<ButtonPress>", self._touch, add=True)
        self.bind_all("<FocusIn>", self._focus_visible, add=True)
        self.bind("<Return>", self._submit_auth)
        self.bind("<Control-Return>", lambda _: self._shortcut_message(False))
        self.bind("<Control-Shift-Return>", lambda _: self._shortcut_message(True))
        self.bind("<Control-Shift-L>", lambda _: self._lock_vault())
        for number in range(1, 5):
            self.bind(
                f"<Control-Key-{number}>", lambda _, index=number - 1: self._select_tab(index)
            )
        self.bind("<F1>", self._help)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self._show_login()
        dark_titlebar(self)
        self._poll_id = self.after(100, self._poll)

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            ".",
            font=("Segoe UI", 11),
            background=COLORS["surface"],
            foreground=COLORS["text"],
            bordercolor="#334155",
            lightcolor="#334155",
            darkcolor="#334155",
        )
        style.configure("TFrame", background=COLORS["surface"])
        style.configure("TLabel", background=COLORS["surface"], foreground=COLORS["text"])
        style.configure("Title.TLabel", font=("Segoe UI", 25, "bold"), foreground=COLORS["text"])
        style.configure("Subtitle.TLabel", foreground=COLORS["muted"])
        style.configure("Error.TLabel", foreground=COLORS["error"])
        style.configure("Badge.TLabel", foreground=COLORS["accent"], font=("Segoe UI", 11, "bold"))
        style.configure(
            "TButton",
            padding=(15, 10),
            borderwidth=1,
            background=COLORS["surface"],
            foreground=COLORS["text"],
            bordercolor=COLORS["border"],
            focuscolor=COLORS["focus"],
        )
        style.map(
            "TButton",
            background=[("disabled", "#253247"), ("active", "#233449")],
            foreground=[("disabled", "#95a8c0")],
            bordercolor=[("focus", COLORS["focus"])],
        )
        style.configure(
            "Accent.TButton", background=COLORS["accent"], foreground=COLORS["accent_text"]
        )
        style.map(
            "Accent.TButton",
            background=[("disabled", "#253247"), ("active", COLORS["accent_active"])],
            foreground=[("disabled", "#95a8c0"), ("!disabled", COLORS["accent_text"])],
        )
        style.configure(
            "TEntry",
            fieldbackground=COLORS["input"],
            foreground=COLORS["text"],
            padding=9,
            borderwidth=2,
            bordercolor=COLORS["border"],
            insertcolor=COLORS["text"],
        )
        style.map(
            "TEntry", bordercolor=[("focus", COLORS["focus"])], foreground=[("disabled", "#95a8c0")]
        )
        style.configure("TNotebook", background=COLORS["surface"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 12), background=COLORS["page"], borderwidth=0)
        style.map(
            "TNotebook.Tab",
            background=[("selected", COLORS["selection"])],
            foreground=[("selected", COLORS["selection_text"])],
        )
        style.configure(
            "Treeview",
            background=COLORS["surface"],
            fieldbackground=COLORS["surface"],
            foreground=COLORS["text"],
            rowheight=35,
        )
        style.map(
            "Treeview",
            background=[("selected", COLORS["selection"])],
            foreground=[("selected", COLORS["selection_text"])],
        )
        style.configure(
            "Treeview.Heading", background=COLORS["page"], foreground=COLORS["text"], padding=9
        )
        style.configure(
            "Horizontal.TProgressbar", background=COLORS["accent"], troughcolor=COLORS["page"]
        )
        for name in ("TCheckbutton", "TRadiobutton"):
            style.configure(
                name,
                background=COLORS["surface"],
                indicatorbackground=COLORS["input"],
                indicatorforeground=COLORS["accent"],
                focuscolor=COLORS["focus"],
            )
            style.map(
                name,
                background=[("active", COLORS["surface"])],
                indicatorbackground=[("selected", COLORS["accent"])],
            )
        style.configure(
            "Vertical.TScrollbar",
            background=COLORS["border"],
            troughcolor=COLORS["input"],
            arrowcolor=COLORS["text"],
            borderwidth=0,
        )
        style.map(
            "Vertical.TScrollbar",
            background=[("disabled", "#253247"), ("active", "#8ba2be")],
            troughcolor=[("disabled", COLORS["input"])],
            arrowcolor=[("disabled", COLORS["muted"])],
            lightcolor=[("!disabled", COLORS["border"])],
            darkcolor=[("!disabled", COLORS["border"])],
        )
        style.map("Treeview.Heading", background=[("active", "#233449")])
        style.layout(
            "Vertical.TScrollbar",
            [
                (
                    "Vertical.Scrollbar.trough",
                    {
                        "sticky": "ns",
                        "children": [
                            ("Vertical.Scrollbar.thumb", {"sticky": "nswe", "expand": True})
                        ],
                    },
                )
            ],
        )

    def _feedback(self, value, *, error=False):
        self.status.set(("Error: " if error else "") + value)
        label = getattr(self, "_status_label", None)
        if label is not None and label.winfo_exists():
            label.configure(style="Error.TLabel" if error else "Subtitle.TLabel")

    def _status_panel(self):
        panel = ttk.Frame(self._container)
        expanding = [w for w in self._container.pack_slaves() if w.pack_info().get("expand")]
        options = {"before": expanding[0]} if expanding else {}
        panel.pack(side="bottom", fill="x", pady=(18, 0), **options)
        self._status_label = self._wrapped_label(
            panel, textvariable=self.status, style="Subtitle.TLabel"
        )
        self._status_label.pack(side="left", fill="x", expand=True)
        self._progress = ttk.Progressbar(panel, mode="indeterminate", length=100)
        self._cancel_button = ttk.Button(panel, text="Cancel", command=self._cancel_operation)

    def _help(self, _event=None):
        messagebox.showinfo(
            "Keyboard shortcuts",
            "Tab / Shift+Tab: move between controls\n"
            "Ctrl+1–4: switch workspace tabs\nCtrl+Enter: encrypt message\n"
            "Ctrl+Shift+Enter: decrypt message\nCtrl+Shift+L: sign out\n"
            "Ctrl+A: select message text\nCtrl+Tab: insert a tab in message input\n"
            "F1: this help",
            parent=self,
        )

    def _select_tab(self, index):
        notebook = getattr(self, "notebook", None)
        if notebook is not None and notebook.winfo_exists() and not self._busy:
            notebook.select(index)

    def _shortcut_message(self, decrypt):
        if self.service is not None and not self._busy and self._pending_recovery is None:
            self._select_tab(0)
            self._message(decrypt)
        return "break"

    def _submit_auth(self, _event=None):
        if self.service is None and self._pending_recovery is None and not self._busy:
            self._unlock()

    def _focus_visible(self, event):
        widget = event.widget
        while widget is not None and not isinstance(widget, tk.Canvas):
            widget = getattr(widget, "master", None)
        if widget is not None and widget.winfo_exists():
            canvas = widget
            self.update_idletasks()
            top = event.widget.winfo_rooty() - canvas.winfo_rooty()
            bottom = top + event.widget.winfo_height()
            bounds = canvas.bbox("all")
            if bounds and (top < 0 or bottom > canvas.winfo_height()):
                offset = top if top < 0 else bottom - canvas.winfo_height()
                canvas.yview_moveto(max(0, (canvas.canvasy(0) + offset) / max(1, bounds[3])))

    def _touch(self, _event=None):
        self._activity = time.monotonic()

    def _reset(self):
        for widget in self._container.winfo_children():
            widget.destroy()
        self._controls = []
        self._texts = []
        self._password_fields = []

    def _button(self, parent, text, command, *, accent=False):
        button = ttk.Button(
            parent, text=text, command=command, style="Accent.TButton" if accent else "TButton"
        )
        self._controls.append(button)
        return button

    def _entry(self, parent, *, secret=False, **kwargs):
        entry = ttk.Entry(parent, show="•" if secret else "", **kwargs)
        self._controls.append(entry)
        if secret:
            self._password_fields.append(entry)
        return entry

    def _heading(self, parent, text, detail):
        ttk.Label(parent, text=text, style="Title.TLabel").pack(anchor="w")
        self._wrapped_label(parent, text=detail, style="Subtitle.TLabel").pack(
            fill="x", anchor="w", pady=(6, 20)
        )

    @staticmethod
    def _wrapped_label(parent, **kwargs):
        label = ttk.Label(parent, wraplength=700, **kwargs)
        label.bind("<Configure>", lambda event: label.configure(wraplength=max(120, event.width)))
        return label

    def _show_login(self):
        self._reset()
        self._heading(
            self._container,
            "Serein Vault",
            "Private files. Personal messages. One simple local account.",
        )
        options = ttk.Frame(self._container)
        options.pack(fill="x", padx=24, pady=(0, 14))
        outer = ttk.Frame(self._container)
        outer.pack(fill="both", expand=True)
        card, _ = self._scrollable(outer)
        card.configure(padding=(24, 0, 24, 12))
        for title, value in (
            ("Log in", "login"),
            ("Sign up", "signup"),
            ("Reset password", "reset"),
        ):
            self._button(
                options,
                title,
                lambda mode=value: self._switch_mode(mode),
                accent=self.mode.get() == value,
            ).pack(side="left", padx=(0, 8))
        mode = self.mode.get()
        titles = {
            "login": "Welcome back",
            "signup": "Create your account",
            "reset": "Recover your account",
            "upgrade": "Upgrade a password-only vault",
        }
        ttk.Label(card, text=titles[mode], font=("Segoe UI", 16, "bold")).pack(
            anchor="w", pady=(0, 10)
        )
        form = ttk.Frame(card)
        form.pack(fill="x")
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="Username").grid(row=0, column=0, sticky="w")
        self.login_username = self._entry(form, textvariable=self.username_text)
        self.login_username.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 10))
        ttk.Label(form, text="New password" if mode == "reset" else "Password").grid(
            row=2, column=0, sticky="w"
        )
        self.login_password = self._entry(form, secret=True)
        self.login_password.grid(
            row=3,
            column=0,
            columnspan=1 if mode in {"signup", "reset"} else 2,
            sticky="ew",
            padx=(0, 8) if mode in {"signup", "reset"} else 0,
            pady=(4, 10),
        )
        self.login_confirm = self._entry(form, secret=True)
        if mode in {"signup", "reset"}:
            ttk.Label(form, text="Confirm password").grid(row=2, column=1, sticky="w", padx=(8, 0))
            self.login_confirm.grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=(4, 10))
        self.recovery_entry = None
        if mode == "reset":
            ttk.Label(form, text="Saved recovery key").grid(row=4, column=0, sticky="w")
            self.recovery_entry = self._entry(form, secret=True)
            self.recovery_entry.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 8))
        self._show_secrets = tk.BooleanVar(master=self, value=False)
        show = ttk.Checkbutton(
            card,
            text="Show password and recovery key" if mode == "reset" else "Show password",
            variable=self._show_secrets,
            command=self._toggle_passwords,
        )
        show.pack(anchor="w", pady=(0, 10))
        self._controls.append(show)
        details = {
            "signup": "Username: 3–32 letters, numbers, dots, dashes or underscores. "
            "Password: 12+ characters. Save the recovery key shown after signup.",
            "login": "Use the username and password for this vault. Usernames ignore case; "
            "passwords preserve every character.",
            "reset": "Your recovery key preserves your encrypted data. A successful reset "
            "replaces that key. No email or server is required.",
            "upgrade": "Choose a username and enter your existing vault password. "
            "An encrypted backup is saved before upgrading.",
        }
        self._wrapped_label(card, text=details[mode], style="Subtitle.TLabel").pack(
            fill="x", pady=(0, 12)
        )
        buttons = {
            "login": "Log in",
            "signup": "Create account",
            "reset": "Reset password",
            "upgrade": "Upgrade and create account",
        }
        self._button(card, buttons[mode], self._unlock, accent=True).pack(anchor="w", pady=(0, 14))
        location = ttk.Frame(card)
        location.pack(fill="x")
        ttk.Label(location, text="Account vault file", style="Subtitle.TLabel").pack(anchor="w")
        row = ttk.Frame(location)
        row.pack(fill="x", pady=(4, 8))
        self._entry(row, textvariable=self.vault_path).pack(side="left", fill="x", expand=True)
        self._button(row, "Browse…", self._browse_vault).pack(side="left", padx=(10, 0))
        if mode != "upgrade":
            self._button(
                location,
                "Upgrade an older password-only vault…",
                lambda: self._switch_mode("upgrade"),
            ).pack(anchor="w")
        self._status_panel()
        self.login_username.focus_set()

    def _toggle_passwords(self):
        for entry in self._password_fields:
            entry.configure(show="" if self._show_secrets.get() else "•")

    def _switch_mode(self, mode):
        if self._busy:
            return
        self._clear_passwords()
        self.mode.set(mode)
        self._show_login()
        self._feedback(
            "One owner account per vault. Choose another file to use a different account."
        )

    def _browse_vault(self):
        options = {"parent": self, "filetypes": [("Serein vault", "*.svdb"), ("All files", "*")]}
        if self.mode.get() == "signup":
            chosen = filedialog.asksaveasfilename(
                title="Create account vault",
                defaultextension=".svdb",
                confirmoverwrite=False,
                **options,
            )
        else:
            chosen = filedialog.askopenfilename(title="Choose account vault", **options)
        if chosen:
            self.vault_path.set(chosen)

    def _unlock(self):
        mode = self.mode.get()
        password = self.login_password.get()
        username = self.username_text.get()
        if mode in {"signup", "reset"} and password != self.login_confirm.get():
            self._feedback("Enter the same password in both fields.", error=True)
            self.login_confirm.focus_set()
            return
        path = Path(self.vault_path.get()).expanduser()
        recovery = self.recovery_entry.get() if self.recovery_entry is not None else None
        self._clear_passwords()
        if mode == "reset":
            self._run(
                lambda: VaultService.reset_password(path, username, recovery, password),
                self._reset_done,
                "Resetting your password safely…",
            )
        elif mode in {"signup", "upgrade"}:
            operation = VaultService.signup if mode == "signup" else VaultService.upgrade
            self._run(
                lambda: operation(path, username, password),
                self._account_created,
                "Creating your account…"
                if mode == "signup"
                else "Backing up and upgrading your vault…",
            )
        else:
            self._run(
                lambda: VaultService.login(path, username, password), self._unlocked, "Logging in…"
            )

    def _unlocked(self, service):
        self.service = service
        self.username_text.set(service.username)
        self.vault_path.set(str(service.vault.path))
        self._show_workspace()
        self._feedback("Logged in. Your original files are preserved.")

    def _account_created(self, result):
        self.service, recovery = result
        self.username_text.set(self.service.username)
        self.vault_path.set(str(self.service.vault.path))
        self._show_recovery(recovery, self._show_workspace)

    def _reset_done(self, recovery):
        self._show_recovery(recovery, self._return_to_login)

    def _return_to_login(self):
        self.mode.set("login")
        self._show_login()
        self._feedback("Password reset. Log in with your username and new password.")

    def _show_recovery(self, code, after):
        self._reset()
        self._pending_recovery = code
        self._recovery_after = after
        self._heading(
            self._container,
            "Save your recovery key",
            "This key can reset your password and unlock your vault. Keep it private.",
        )
        self._wrapped_label(
            self._container,
            text="Save this in a password manager or keep an offline copy, separately from "
            "your vault. It is shown only now. If you lose it while you still know your "
            "password, you can replace it from Account settings.",
            style="Subtitle.TLabel",
        ).pack(fill="x", pady=(0, 20))
        self.recovery_display = self._text(self._container, 3)
        self._write_text(self.recovery_display, code, readonly=True)
        self._button(self._container, "Copy recovery key", lambda: self._copy_value(code)).pack(
            anchor="w", pady=12
        )
        self.recovery_saved = tk.BooleanVar(master=self, value=False)
        self.recovery_continue = self._button(
            self._container, "Continue", self._finish_recovery, accent=True
        )
        saved = ttk.Checkbutton(
            self._container,
            text="I have saved my recovery key somewhere safe",
            variable=self.recovery_saved,
            command=self._recovery_acknowledged,
        )
        saved.pack(anchor="w", pady=14)
        self._controls.append(saved)
        self.recovery_continue.pack(anchor="w")
        self.recovery_continue.state(["disabled"])
        self._status_panel()
        self._feedback(
            "A password reset replaces the previous recovery key. Back up your updated vault too."
        )
        saved.focus_set()

    def _recovery_acknowledged(self):
        self.recovery_continue.state(["!disabled"] if self.recovery_saved.get() else ["disabled"])

    def _finish_recovery(self):
        if not self.recovery_saved.get():
            return
        self._pending_recovery = None
        self._clear_clipboard()
        after, self._recovery_after = self._recovery_after, None
        after()
        if self.service is not None:
            self._feedback("Logged in. Recovery key saved; keep an encrypted vault backup too.")

    def _show_workspace(self):
        self._reset()
        top = ttk.Frame(self._container)
        top.pack(fill="x")
        ttk.Label(top, text="Serein Vault", style="Title.TLabel").pack(side="left")
        self._button(top, "Sign out", self._lock_vault).pack(side="right")
        ttk.Label(top, text=f"Signed in as {self.service.username}", style="Badge.TLabel").pack(
            side="right", padx=18
        )
        self._wrapped_label(
            self._container, text=self.vault_path.get(), style="Subtitle.TLabel"
        ).pack(anchor="w", fill="x", pady=(4, 18))
        notebook = ttk.Notebook(self._container)
        self.notebook = notebook
        notebook.enable_traversal()
        notebook.pack(fill="both", expand=True)
        self._message_tab(notebook)
        self._file_tab(notebook)
        self._history_tab(notebook)
        self._vault_tab(notebook)
        self._status_panel()
        self._refresh_history()

    def _tab(self, notebook, title):
        frame = ttk.Frame(notebook, padding=18)
        notebook.add(frame, text=title)
        if title in {"Messages", "History & recovery"} and self.display_scale > 1.1:
            inner, _ = self._scrollable(frame, fill_height=True)
            return inner
        return frame

    def _text(self, parent, height, *, pack=True):
        frame = ttk.Frame(parent)
        if pack:
            frame.pack(fill="both", expand=True, pady=(6, 12))
        text = tk.Text(
            frame,
            height=height,
            wrap="word",
            undo=False,
            background=COLORS["input"],
            foreground=COLORS["text"],
            insertbackground=COLORS["text"],
            selectbackground=COLORS["selection"],
            selectforeground=COLORS["selection_text"],
            highlightthickness=2,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["focus"],
            relief="flat",
            padx=12,
            pady=10,
            font=("Consolas", 11),
        )
        scrollbar = ttk.Scrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        self._texts.append(text)
        text.bind("<Tab>", lambda _: self._focus_next(text))
        text.bind("<Shift-Tab>", lambda _: self._focus_next(text, reverse=True))
        text.bind("<Control-Tab>", lambda _: self._insert_tab(text))
        text.bind("<Control-a>", lambda _: self._select_all(text))
        return text

    @staticmethod
    def _focus_next(widget, *, reverse=False):
        (widget.tk_focusPrev() if reverse else widget.tk_focusNext()).focus_set()
        return "break"

    @staticmethod
    def _insert_tab(widget):
        widget.insert("insert", "\t")
        return "break"

    @staticmethod
    def _select_all(widget):
        widget.tag_add("sel", "1.0", "end-1c")
        return "break"

    def _message_tab(self, notebook):
        frame = self._tab(notebook, "Messages")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1, minsize=55)
        frame.rowconfigure(4, weight=1, minsize=55)
        header = ttk.Frame(frame)
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="Your message").pack(side="left")
        self.message_label = tk.StringVar(master=self)
        self._entry(header, textvariable=self.message_label, width=22).pack(side="right")
        ttk.Label(header, text="Label (optional)", style="Subtitle.TLabel").pack(
            side="right", padx=8
        )
        self.message_input = self._text(frame, 3, pack=False)
        self.message_input.master.grid(row=1, column=0, sticky="nsew", pady=(6, 10))
        row = ttk.Frame(frame)
        row.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self._button(row, "Encrypt message", lambda: self._message(False), accent=True).pack(
            side="left"
        )
        self._button(row, "Decrypt message", lambda: self._message(True)).pack(side="left", padx=8)
        self._button(row, "Clear", self._clear_messages).pack(side="right")
        ttk.Label(frame, text="Output · copy only when you need it").grid(
            row=3, column=0, sticky="w"
        )
        self.message_output = self._text(frame, 3, pack=False)
        self.message_output.master.grid(row=4, column=0, sticky="nsew", pady=(6, 10))
        self.message_output.configure(state="disabled")
        self.copy_output_button = self._button(
            frame, "Copy output (clears after 45 seconds)", self._copy_output
        )
        self.copy_output_button.grid(row=5, column=0, sticky="w")

    def _message(self, decrypt):
        value = self.message_input.get("1.0", "end-1c")
        label = self.message_label.get()
        self._run(
            lambda: (
                self.service.decrypt_message(value.strip())
                if decrypt
                else self.service.encrypt_message(value, label)
            ),
            self._message_result,
            "Decrypting message…" if decrypt else "Encrypting and saving message…",
        )

    def _message_result(self, value):
        self._write_text(self.message_output, value, readonly=True)
        self._refresh_history()
        self._feedback("Message ready. You can find earlier messages in History & recovery.")

    @staticmethod
    def _write_text(widget, value, *, readonly=False):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        if readonly:
            widget.configure(state="disabled")

    def _clear_messages(self):
        if hasattr(self, "message_label"):
            self.message_label.set("")
        for name in ("message_input", "message_output"):
            widget = getattr(self, name, None)
            if widget is not None and widget.winfo_exists():
                self._write_text(widget, "", readonly=name == "message_output")

    def _copy_output(self):
        value = self.message_output.get("1.0", "end-1c")
        self._copy_value(value)

    def _copy_value(self, value):
        if not value:
            return
        self.clipboard_clear()
        self.clipboard_append(value)
        self._clipboard_value = value
        self._clipboard_expires = time.monotonic() + CLIPBOARD_SECONDS
        self._feedback("Copied. This clipboard value clears after 45 seconds or when you sign out.")

    def _clear_clipboard(self):
        if self._clipboard_value is not None:
            try:
                if self.clipboard_get() == self._clipboard_value:
                    self.clipboard_clear()
            except tk.TclError:
                pass
            self._clipboard_value = None

    def _file_tab(self, notebook):
        outer = self._tab(notebook, "Files")
        frame, _ = self._scrollable(outer)
        self._heading(
            frame,
            "Protect a file",
            "Choose an input and a separate output. "
            "Your original and existing files stay untouched.",
        )
        self.file_mode = tk.StringVar(master=self, value="encrypt")
        self.file_source = tk.StringVar(master=self)
        self.file_destination = tk.StringVar(master=self)
        modes = ttk.Frame(frame)
        modes.pack(fill="x", pady=(0, 18))
        for title, value in (("Encrypt a file", "encrypt"), ("Decrypt a file", "decrypt")):
            radio = ttk.Radiobutton(
                modes,
                text=title,
                variable=self.file_mode,
                value=value,
                command=self._file_mode_changed,
            )
            radio.pack(side="left", padx=(0, 24))
            self._controls.append(radio)
        for label, variable, command in (
            ("Input file", self.file_source, self._browse_input),
            ("Output file", self.file_destination, self._browse_output),
        ):
            ttk.Label(frame, text=label).pack(anchor="w")
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=(6, 16))
            self._entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
            self._button(row, "Browse…", command).pack(side="left", padx=(10, 0))
        self.file_action = self._button(frame, "Encrypt file", self._start_file, accent=True)
        self.file_action.pack(anchor="w", pady=(6, 18))
        self._wrapped_label(
            frame,
            text="Encrypted files can be moved or renamed. "
            "Keep an encrypted vault backup so you retain access to them.",
            style="Subtitle.TLabel",
        ).pack(fill="x")

    def _file_mode_changed(self):
        self.file_action.configure(
            text="Decrypt file" if self.file_mode.get() == "decrypt" else "Encrypt file"
        )
        if self.file_source.get():
            source = Path(self.file_source.get())
            name = (
                source.name.removesuffix(".svault") + ".recovered"
                if self.file_mode.get() == "decrypt"
                else source.name + ".svault"
            )
            self.file_destination.set(str(source.with_name(name)))

    def _browse_input(self):
        chosen = filedialog.askopenfilename(parent=self, title="Choose input file")
        if chosen:
            self.file_source.set(chosen)
            self._file_mode_changed()

    def _browse_output(self):
        value = self.file_destination.get()
        chosen = filedialog.asksaveasfilename(
            parent=self,
            title="Choose a new output file",
            initialfile=Path(value).name if value else "",
            confirmoverwrite=False,
        )
        if chosen:
            self.file_destination.set(chosen)

    def _start_file(self):
        if self._busy:
            return
        if not self.file_source.get() or not self.file_destination.get():
            self._feedback("Choose both an input file and a new output file.", error=True)
            return
        source, destination = Path(self.file_source.get()), Path(self.file_destination.get())
        operation = (
            self.service.decrypt_file
            if self.file_mode.get() == "decrypt"
            else self.service.encrypt_file
        )
        control = OperationControl(self._report_progress)
        self._operation_control = control
        self._run(
            lambda: operation(source, destination, control),
            self._file_result,
            "Processing your file safely…",
        )

    def _choose_file_paths(self, decrypt=False):
        source = filedialog.askopenfilename(
            parent=self, title="Select encrypted file" if decrypt else "Select file"
        )
        if not source:
            return None
        path = Path(source)
        name = (
            (path.name.removesuffix(".svault") + ".recovered") if decrypt else path.name + ".svault"
        )
        destination = filedialog.asksaveasfilename(
            parent=self,
            title="Save recovered file" if decrypt else "Save encrypted file",
            initialdir=path.parent,
            initialfile=name,
            confirmoverwrite=False,
        )
        return (path, Path(destination)) if destination else None

    def _file_result(self, destination):
        self._refresh_history()
        self.status.set(f"Saved: {destination}. The input file was preserved.")

    def _history_tab(self, notebook):
        frame = self._tab(notebook, "History & recovery")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        search = ttk.Frame(frame)
        search.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(search, text="Search history").pack(side="left", padx=(0, 10))
        self.history_query = tk.StringVar(master=self)
        self._entry(search, textvariable=self.history_query).pack(fill="x", expand=True)
        table = ttk.Frame(frame)
        table.grid(row=1, column=0, sticky="nsew")
        self.history_tree = ttk.Treeview(
            table, columns=("kind", "label", "date"), show="headings", selectmode="browse"
        )
        for column, title, width in (
            ("kind", "Type", 120),
            ("label", "Item", 420),
            ("date", "Created (UTC)", 190),
        ):
            self.history_tree.heading(column, text=title)
            self.history_tree.column(column, width=width, minwidth=80)
        scroll = ttk.Scrollbar(table, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.history_tree.pack(fill="both", expand=True)
        row = ttk.Frame(frame)
        row.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        for index, (title, command) in enumerate(
            (
                ("Load encrypted message", lambda: self._history_message(False)),
                ("Recover message", lambda: self._history_message(True)),
                ("Edit message label", self._edit_label),
                ("Recover legacy file…", self._recover_legacy_file),
            )
        ):
            self._button(row, title, command).grid(
                row=index // 2, column=index % 2, sticky="ew", padx=(0, 8), pady=3
            )
        row.columnconfigure((0, 1), weight=1)
        self.history_query.trace_add("write", self._filter_history)

    def _refresh_history(self):
        selection = self.history_tree.selection()
        records = self.service.history(self.history_query.get())
        for record_id in self.history_tree.get_children():
            self.history_tree.delete(record_id)
        for item in records:
            self.history_tree.insert(
                "",
                "end",
                iid=item["record_id"],
                values=(item["kind"], item["label"], item["created_at"]),
            )
        if selection and self.history_tree.exists(selection[0]):
            self.history_tree.selection_set(selection)

    def _filter_history(self, *_):
        if self._busy:
            return
        try:
            self._refresh_history()
        except VaultError as exc:
            self._feedback(str(exc), error=True)

    def _edit_label(self):
        record_id = self._selected_record()
        if record_id:
            label = simpledialog.askstring(
                "Message label",
                "New label (80 characters maximum)",
                parent=self,
                initialvalue=self.history_tree.item(record_id, "values")[1],
            )
            if label is not None:
                self._run(
                    lambda: self.service.label_message(record_id, label),
                    lambda _: self._refresh_history(),
                    "Saving label…",
                )

    def _selected_record(self):
        selection = self.history_tree.selection()
        if not selection:
            messagebox.showinfo(
                "Select an item", "Select a message or legacy file key first.", parent=self
            )
            return None
        return selection[0]

    def _history_message(self, decrypt):
        record_id = self._selected_record()
        if record_id:

            def loaded(value):
                self._write_text(
                    self.message_output if decrypt else self.message_input, value, readonly=decrypt
                )
                self._select_tab(0)
                self.status.set("Message loaded in the Messages tab.")

            self._run(
                lambda: self.service.history_message(record_id, decrypt=decrypt),
                loaded,
                "Loading message…",
            )

    def _recover_legacy_file(self):
        record_id = self._selected_record()
        if record_id is None:
            return
        paths = self._choose_file_paths(True)
        if paths:
            self._run(
                lambda: self.service.recover_legacy_file(record_id, *paths),
                self._file_result,
                "Recovering legacy file…",
            )

    def _vault_tab(self, notebook):
        outer = self._tab(notebook, "Account & backups")
        frame, _ = self._scrollable(outer)
        self.health_text = tk.StringVar(
            master=self, value="Check database integrity without changing your vault."
        )
        self._button(frame, "Check vault health", self._check_health).pack(anchor="w", pady=(0, 8))
        self._wrapped_label(frame, textvariable=self.health_text, style="Subtitle.TLabel").pack(
            fill="x", pady=(0, 18)
        )
        ttk.Label(frame, text="Change the vault password", font=("Segoe UI", 14, "bold")).pack(
            anchor="w"
        )
        self.change_entries = []
        for label in ("Current password", "New password (12+ characters)", "Confirm new password"):
            ttk.Label(frame, text=label).pack(anchor="w", pady=(7, 2))
            entry = self._entry(frame, secret=True, width=65)
            entry.pack(anchor="w", fill="x")
            self.change_entries.append(entry)
        self._button(frame, "Update password", self._change_password).pack(
            anchor="w", pady=(12, 14)
        )
        self._button(frame, "Replace recovery key", self._replace_recovery).pack(
            anchor="w", pady=(0, 12)
        )
        self._wrapped_label(
            frame,
            text="To replace a lost recovery key, enter your current password above. "
            "The old recovery key will stop working.",
            style="Subtitle.TLabel",
        ).pack(fill="x", pady=(0, 16))
        self._button(frame, "Save encrypted vault backup…", self._backup).pack(
            anchor="w", pady=(0, 12)
        )
        self._wrapped_label(
            frame,
            text="Import from the deprecated EncryptZone prototype",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", pady=(6, 8))
        row = ttk.Frame(frame)
        row.pack(fill="x")
        for title, kind in (
            ("File keys…", "file"),
            ("Message keys…", "message"),
            ("Password hash…", "password"),
        ):
            self._button(row, title, lambda k=kind: self._import(k)).pack(side="left", padx=(0, 8))
        self._wrapped_label(
            frame,
            text=f"Serein Vault {__version__} · Faraz Hussain & contributors · MIT License\n"
            "Signs out after 10 minutes of inactivity. "
            "Imported source files remain untouched. Verify recovery and back up the vault "
            "before removing them.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", fill="x", pady=(18, 0))

    def _scrollable(self, parent, *, fill_height=False):
        canvas = tk.Canvas(
            parent,
            background=COLORS["surface"],
            highlightthickness=0,
            takefocus=False,
            yscrollincrement=1,
        )
        self._scroll_canvas = canvas
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollbar._serein_scroll_target = canvas
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        frame = ttk.Frame(canvas, padding=(0, 0, 12, 8))
        window_id = canvas.create_window(0, 0, anchor="nw", window=frame)
        frame.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))

        def resize(event):
            options = {"width": event.width}
            if fill_height:
                options["height"] = max(frame.winfo_reqheight(), event.height)
            canvas.itemconfigure(window_id, **options)

        canvas.bind("<Configure>", resize)
        return frame, canvas

    def _check_health(self):
        def checked(result):
            self.health_text.set(
                f"Integrity: {result['integrity']} · {result['records']} records · "
                f"{result['encrypted_bytes']:,} encrypted bytes"
            )
            self._feedback("Vault health check passed. No data was changed.")

        self._run(self.service.health, checked, "Checking vault health…")

    def _report_progress(self, completed, total):
        # Workers publish numbers only. Keep a single latest update, not a growing queue.
        with contextlib.suppress(Empty):
            self._progress_updates.get_nowait()
        with contextlib.suppress(Full):
            self._progress_updates.put_nowait((completed, total))

    def _cancel_operation(self):
        if self._operation_control is not None:
            self._operation_control.cancel()
            self._cancel_button.state(["disabled"])
            self._feedback("Cancellation requested; waiting for safe cleanup…")

    def _change_password(self):
        current, new, confirm = (entry.get() for entry in self.change_entries)
        if new != confirm:
            self._feedback("Enter the same new password twice.", error=True)
            return
        self._clear_passwords()
        self._run(
            lambda: self.service.change_password(current, new),
            lambda _: self.status.set(
                "Password changed. Existing files and messages remain recoverable. "
                "Create a fresh backup; older backups retain their previous password."
            ),
            "Re-encrypting the database with the new password…",
        )

    def _replace_recovery(self):
        current = self.change_entries[0].get()
        self._clear_passwords()
        self._run(
            lambda: self.service.rotate_recovery(current),
            lambda key: self._show_recovery(key, self._show_workspace),
            "Replacing your recovery key…",
        )

    def _backup(self):
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save encrypted vault backup",
            initialfile="serein-backup.svdb",
            defaultextension=".svdb",
            confirmoverwrite=False,
        )
        if path:
            self._run(
                lambda: self.service.backup(Path(path)),
                lambda result: self.status.set(f"Encrypted backup saved: {result}"),
                "Saving encrypted backup…",
            )

    def _import(self, kind):
        path = filedialog.askopenfilename(parent=self, title=f"Import legacy {kind} file")
        if path:

            def imported(result):
                self._refresh_history()
                self.status.set(result)

            self._run(
                lambda: self.service.import_legacy(Path(path), kind),
                imported,
                "Validating legacy records…",
            )

    def _clear_passwords(self):
        for entry in self._password_fields:
            entry.delete(0, "end")

    def _set_busy(self, busy):
        self._busy = busy
        for widget in self._controls:
            widget.state(["disabled"] if busy else ["!disabled"])
        for widget in self._texts:
            widget.configure(
                state="disabled"
                if busy
                or widget
                in (getattr(self, "message_output", None), getattr(self, "recovery_display", None))
                else "normal"
            )
        if busy:
            self._progress.pack(side="right", padx=(12, 0))
            if self._operation_control is None:
                self._progress.configure(mode="indeterminate")
                self._progress.start(15)
            else:
                self._progress.configure(mode="determinate", value=0, maximum=100)
                self._cancel_button.state(["!disabled"])
                self._cancel_button.pack(side="right", padx=(12, 0))
        else:
            self._progress.stop()
            self._progress.pack_forget()
            self._cancel_button.pack_forget()
            self._operation_control = None

    def _run(self, operation, success, status):
        if self._busy:
            return
        self._set_busy(True)
        self._feedback(status)
        self._success = success
        self._future = self._executor.submit(operation)

    def _poll(self):
        try:
            completed, total = self._progress_updates.get_nowait()
            if self._busy and self._operation_control is not None:
                percent = completed * 100 / total if total else 100
                self._progress.configure(value=percent)
                if not self._operation_control.cancelled.is_set():
                    self._feedback(
                        f"Processing file: {percent:.0f}% · {completed:,} / {total:,} bytes"
                    )
        except Empty:
            pass
        if self._future is not None and self._future.done():
            future, success = self._future, self._success
            self._future = self._success = None
            self._set_busy(False)
            try:
                result = future.result()
                success(result)
            except (VaultError, OSError) as exc:
                self._feedback(str(exc), error=True)
                if self.service is None and self._pending_recovery is None:
                    self.login_password.focus_set()
            except Exception:
                self.status.set(
                    "Unexpected application error. Sign out and log in before continuing."
                )
                if not self._closing:
                    messagebox.showerror("Application error", self.status.get(), parent=self)
            self._touch()
        if self._closing and not self._busy:
            self._shutdown()
            return
        now = time.monotonic()
        if self._clipboard_value is not None and now >= self._clipboard_expires:
            self._clear_clipboard()
        if (
            self.service is not None
            and not self._busy
            and now - self._activity >= AUTO_LOCK_SECONDS
        ):
            self._lock_vault()
        self._poll_id = self.after(100, self._poll)

    def _lock_vault(self):
        if self._busy or self.service is None:
            return
        self._clear_clipboard()
        self._clear_passwords()
        self._clear_messages()
        service = self.service

        def locked(_):
            self.service = None
            self._pending_recovery = None
            self.mode.set("login")
            self._show_login()
            self._feedback("Signed out. Enter your username and password to continue.")

        self._run(service.close, locked, "Locking vault…")

    def close(self):
        self._closing = True
        if self._busy:
            if self._operation_control is not None:
                self._operation_control.cancel()
            self.status.set("Finishing the current operation safely before closing…")
        else:
            self._shutdown()

    def _shutdown(self):
        self._clear_clipboard()
        if self.service is not None:
            self.service.close()
            self.service = None
        self._executor.shutdown(wait=True)
        self.after_cancel(self._poll_id)
        self.destroy()


def main():
    if "--smoke-test" in sys.argv:
        import argparse

        from .smoke import run_smoke

        parser = argparse.ArgumentParser(description="Serein Vault installer validation")
        parser.add_argument("--smoke-test", type=Path, required=True)
        args = parser.parse_args()
        run_smoke(args.smoke_test)
        return
    app = VaultApp()
    try:
        app.mainloop()
    finally:
        app._executor.shutdown(wait=True)
        if app.service is not None:
            app.service.close()


if __name__ == "__main__":
    main()
