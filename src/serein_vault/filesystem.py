"""Atomic publication and cross-process vault locking."""

import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import BinaryIO

from .errors import VaultBusyError, VaultError


class AtomicOutput:
    """Write beside the destination, fsync, then publish without clobbering files."""

    def __init__(self, destination: Path, *, replace: bool = False):
        self.destination = Path(destination).absolute()
        self.replace = replace
        self.temporary: Path | None = None
        self.stream: BinaryIO | None = None

    def __enter__(self):
        if not self.replace and self.destination.exists():
            raise VaultError("The output already exists. Choose a new filename.")
        fd, name = tempfile.mkstemp(prefix=".serein-", suffix=".tmp", dir=self.destination.parent)
        self.temporary = Path(name)
        self.stream = os.fdopen(fd, "w+b")
        return self

    def publish(self):
        assert self.stream is not None and self.temporary is not None
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.stream.close()
        if self.replace:
            os.replace(self.temporary, self.destination)
        else:
            # Atomic create-if-absent, including a competing writer after __enter__.
            # Both paths are on the same filesystem. Failure leaves the source intact.
            try:
                os.link(self.temporary, self.destination)
            except FileExistsError as exc:
                raise VaultError("The output already exists. Choose a new filename.") from exc
            except OSError as exc:
                raise VaultError(
                    "This location cannot publish a file safely. Choose a local NTFS, APFS, "
                    "or other filesystem supporting hard links."
                ) from exc
        self.temporary.unlink(missing_ok=True)
        self.temporary = None
        # Persist the directory entry on platforms supporting directory fsync.
        if os.name != "nt":
            # Publication has already committed. A filesystem refusing directory
            # fsync must not make callers roll back a successfully persisted image.
            with suppress(OSError):
                directory = os.open(self.destination.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)

    def __exit__(self, *_):
        if self.stream is not None:
            self.stream.close()
        if self.temporary is not None:
            self.temporary.unlink(missing_ok=True)


class VaultFileLock:
    """Hold a persistent sidecar lock for the complete unlocked session."""

    def __init__(self, path: Path):
        self.path = path.with_name(path.name + ".lock")
        self.handle = None

    def acquire(self):
        self.handle = self.path.open("a+b")
        try:
            self.handle.seek(0, os.SEEK_END)
            if self.handle.tell() == 0:
                self.handle.write(b"\0")
                self.handle.flush()
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            self.handle = None
            raise VaultBusyError("This vault is already open in another application.") from exc

    def release(self):
        if self.handle is not None:
            # Closing releases the OS lock. Keep the sidecar to avoid unlink/lock races.
            self.handle.close()
            self.handle = None
