"""Push-to-talk. Global on Windows; not available elsewhere.

Polls the key state on a small daemon thread (``GetAsyncKeyState``) instead of
installing a keyboard hook, so it needs no privileges, cannot swallow keys and
cannot leave a stuck hook behind if STONIC dies.
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
from typing import Callable

_VK = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10, "space": 0x20, "f8": 0x77, "f9": 0x78}
CHORDS = {"ctrl+space": ("ctrl", "space"), "ctrl+alt+space": ("ctrl", "alt", "space"), "f8": ("f8",), "f9": ("f9",)}
POLL_S = 0.03


def supported() -> bool:
    return os.name == "nt"


class PushToTalk:
    """Calls ``on_change(held: bool)`` on the event loop when the chord goes down or up."""

    def __init__(self, loop: asyncio.AbstractEventLoop, on_change: Callable[[bool], None], key_state=None) -> None:
        self._loop = loop
        self._on_change = on_change
        self._key_state = key_state
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._chord: tuple[str, ...] = ()
        self._held = False

    def _down(self, name: str) -> bool:
        if self._key_state is not None:
            return bool(self._key_state(name))
        import ctypes
        return bool(ctypes.windll.user32.GetAsyncKeyState(_VK[name]) & 0x8000)

    def start(self, chord_name: str) -> bool:
        """Start watching. False if the platform cannot do a global hotkey."""
        self.stop()
        chord = CHORDS.get(chord_name)
        if not chord or (self._key_state is None and not supported()):
            return False
        self._chord = chord
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="voicelive-ptt", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread and thread.is_alive():
            thread.join(timeout=1.0)
        if self._held:
            self._held = False
            self._loop.call_soon_threadsafe(self._on_change, False)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                held = all(self._down(k) for k in self._chord)
            except Exception:
                held = False
            if held != self._held:
                self._held = held
                try:
                    self._loop.call_soon_threadsafe(self._on_change, held)
                except RuntimeError:
                    return   # loop closed
            time.sleep(POLL_S)
