"""Windows display setup and Tk 9 precision scrolling, without runtime dependencies."""

import sys
import tkinter as tk


def enable_windows_dpi():
    """Call before creating Tk. Packaged builds also declare PerMonitorV2 in their manifest."""
    if sys.platform != "win32":
        return
    import ctypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    try:
        set_process = user32.SetProcessDpiAwarenessContext
        set_process.argtypes = [ctypes.c_void_p]
        set_process.restype = ctypes.c_bool
        if not set_process(ctypes.c_void_p(-4)):
            # A host executable may already have fixed process awareness. Set this
            # GUI thread's context before any windows exist, leaving other threads alone.
            set_thread = user32.SetThreadDpiAwarenessContext
            set_thread.argtypes = [ctypes.c_void_p]
            set_thread.restype = ctypes.c_void_p
            set_thread(ctypes.c_void_p(-4))
    except AttributeError:
        user32.SetProcessDPIAware()


def dark_titlebar(root):
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    root.update_idletasks()
    user32 = ctypes.WinDLL("user32")
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    hwnd = user32.GetAncestor(root.winfo_id(), 2)
    enabled = ctypes.c_int(1)
    # Windows may ignore this on older builds; it never changes system settings.
    ctypes.WinDLL("dwmapi").DwmSetWindowAttribute(
        wintypes.HWND(hwnd), 20, ctypes.byref(enabled), ctypes.sizeof(enabled)
    )


class FormScrolling:
    """Intercept precision events before Entry class bindings can consume them."""

    TAG = "SereinFormScroll"

    def __init__(self, root, activity):
        self.root = root
        self.activity = activity
        self.remainders = {}
        self.precise = False
        root.bind_all("<Map>", self._mapped, add=True)
        for pattern in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            root.bind_class(self.TAG, pattern, self.wheel)
        try:
            root.bind_class(self.TAG, "<TouchpadScroll>", self.touchpad)
            self.precise = True
        except tk.TclError:
            pass  # Tk 8.6 still receives MouseWheel events.

    def _mapped(self, event):
        widget = event.widget
        if hasattr(widget, "bindtags") and self.TAG not in widget.bindtags():
            widget.bindtags((self.TAG, *widget.bindtags()))

    def target(self, event):
        widget = event.widget
        if widget.winfo_class() in {"Text", "Treeview", "Listbox"}:
            return None  # Preserve the widget's native precise scrolling.
        while widget is not None:
            if isinstance(widget, tk.Canvas):
                return widget
            target = getattr(widget, "_serein_scroll_target", None)
            if target is not None and target.winfo_exists():
                return target
            widget = getattr(widget, "master", None)
        return None

    def scroll(self, event, pixels):
        target = self.target(event)
        if target is None or pixels == 0:
            return None
        bounds = target.bbox("all")
        if not bounds or bounds[3] <= target.winfo_height():
            return None
        total = self.remainders.get(str(target), 0) + pixels
        whole = int(total)
        self.remainders[str(target)] = total - whole
        if whole:
            target.yview_scroll(whole, "units")
        self.activity()
        return "break"

    def wheel(self, event):
        number = getattr(event, "num", None)
        if number in (4, 5):
            pixels = -48 if number == 4 else 48
        else:
            delta = getattr(event, "delta", 0)
            pixels = (
                -delta if self.root.tk.call("tk", "windowingsystem") == "aqua" else -delta * 0.4
            )
        return self.scroll(event, pixels)

    def touchpad(self, event):
        _, vertical = self.root.tk.call("tk::PreciseScrollDeltas", event.delta)
        return self.scroll(event, -int(vertical))
