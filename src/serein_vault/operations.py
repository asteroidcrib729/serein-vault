"""Cooperative file cancellation and progress callbacks, independent of Tk."""

import threading

from .errors import OperationCancelled


class OperationControl:
    def __init__(self, progress=None):
        self.cancelled = threading.Event()
        self.progress = progress

    def cancel(self):
        self.cancelled.set()

    def check(self):
        if self.cancelled.is_set():
            raise OperationCancelled(
                "Cancelled. The input was preserved and no new output was published."
            )

    def report(self, completed: int, total: int):
        self.check()
        if self.progress is not None:
            self.progress(completed, total)
