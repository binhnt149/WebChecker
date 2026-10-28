from __future__ import annotations

import gc
from typing import Any


class TkGarbageCollector:
    """Collect cycles on Tk's thread while the standalone desktop app is open.

    Destroyed CTk widgets can leave cycles containing tkinter fonts/variables.
    Automatic GC in a database/network worker can run their Tcl finalizers while
    holding a database lock, deadlocking the UI that needs the same lock.
    Reference counting still works normally; periodic collection reclaims cycles.
    """

    def __init__(self, root: Any) -> None:
        self.root = root
        self._was_enabled = gc.isenabled()
        self._closed = False
        gc.disable()
        self._job = root.after(2000, self._collect)

    def _collect(self) -> None:
        if not self._closed:
            gc.collect()
            self._job = self.root.after(2000, self._collect)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.root.after_cancel(self._job)
        gc.collect()
        if self._was_enabled:
            gc.enable()
