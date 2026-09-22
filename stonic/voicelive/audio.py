"""Audio devices, microphone capture and callback-driven playback.

Design rules that matter here:

* The microphone and speaker callbacks run on PortAudio's real-time threads.
  They copy bytes and hand off to the event loop; they never block, never call
  the network and never run DSP.
* Playback is *callback driven* from a FIFO instead of blocking writes. That is
  what makes interruption immediate: clearing the FIFO silences the very next
  callback (about one buffer, ~40 ms), not "after the 200 ms write finishes".
* The output level shown by the UI is measured on the frames the device is
  actually being given, so the orb tracks the sound instead of a schedule.

``sounddevice`` and ``numpy`` are imported lazily so that a user who never turns
voice on pays nothing at startup.
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Callable

MIC_RATE = 16000          # what Gemini Live wants
SPEAKER_RATE = 24000      # what Gemini Live returns
BLOCK = 1024              # frames per callback, both directions
MAX_BUFFER_S = 120        # never queue more than this much reply audio
STALL_S = 3.0             # queued audio, no more arriving, no turn end: treat as finished


def now() -> float:
    """The clock the audio path stamps blocks with. A function so tests can drive it."""
    return time.monotonic()


def _sd():
    import sounddevice
    return sounddevice


def _np():
    import numpy
    return numpy


# ── devices ──────────────────────────────────────────────────────────────────

def _hostapi_names() -> dict[int, str]:
    sd = _sd()
    try:
        return {i: api["name"] for i, api in enumerate(sd.query_hostapis())}
    except Exception:
        return {}


def _default_api_name() -> str:
    sd = _sd()
    try:
        return str(sd.query_hostapis(sd.default.hostapi)["name"])
    except Exception:
        try:
            return str(sd.query_hostapis(0)["name"])
        except Exception:
            return ""


def list_devices(kind: str) -> list[str]:
    """Usable device names for ``kind`` in ('input', 'output'), one per name.

    Windows lists every device once per host API (MME, DirectSound, WASAPI,
    WDM-KS). Showing four copies of the same microphone is noise, so names are
    de-duplicated, preferring the system default host API.
    """
    sd = _sd()
    key = "max_input_channels" if kind == "input" else "max_output_channels"
    try:
        devices = sd.query_devices()
    except Exception:
        return []
    default_api = _default_api_name()
    apis = _hostapi_names()
    seen: dict[str, tuple[int, int]] = {}
    for index, device in enumerate(devices):
        if device.get(key, 0) < 1:
            continue
        name = str(device["name"]).strip()
        api_name = apis.get(device.get("hostapi", -1), "")
        rank = 0 if api_name == default_api else 1
        if name not in seen or rank < seen[name][1]:
            seen[name] = (index, rank)
    return sorted(seen)


def resolve_device(name: str, kind: str):
    """Device index for a saved name, or ``None`` for the system default.

    ``None`` is also the answer for a saved device that is no longer present, so
    a headset unplugged since last time falls back to the built-in microphone
    instead of stopping voice from starting.
    """
    if not name or not name.strip():
        return None
    sd = _sd()
    key = "max_input_channels" if kind == "input" else "max_output_channels"
    wanted = name.strip().casefold()
    best = None
    try:
        default_api = _default_api_name()
        apis = _hostapi_names()
        for index, device in enumerate(sd.query_devices()):
            if device.get(key, 0) < 1 or str(device["name"]).strip().casefold() != wanted:
                continue
            if apis.get(device.get("hostapi", -1), "") == default_api:
                return index
            best = index if best is None else best
    except Exception:
        return None
    return best


# ── microphone ───────────────────────────────────────────────────────────────

class Microphone:
    """16 kHz mono int16 capture. ``on_block(bytes, monotonic_time)`` is called on
    the event loop for every block the gate lets through."""

    def __init__(self, loop: asyncio.AbstractEventLoop, on_block: Callable[[bytes, float], None],
                 gate: Callable[[], bool], stream_factory=None) -> None:
        self._loop = loop
        self._on_block = on_block
        self._gate = gate
        self._factory = stream_factory
        self._stream = None
        self.device_used = "system default"
        self.fell_back = False

    @property
    def is_open(self) -> bool:
        return self._stream is not None

    def _callback(self, indata, frames, time_info, status) -> None:
        # Real-time thread: a boolean, a copy and a hand-off. Nothing else.
        try:
            if not self._gate():
                return
            data = bytes(indata)
            self._loop.call_soon_threadsafe(self._on_block, data, now())
        except Exception:
            pass

    def open(self, device_name: str = "") -> None:
        if self._stream is not None:
            return
        factory = self._factory or (lambda dev: _sd().RawInputStream(
            samplerate=MIC_RATE, channels=1, dtype="int16", blocksize=BLOCK, device=dev, callback=self._callback))
        index = resolve_device(device_name, "input")
        self.fell_back = False
        try:
            stream = factory(index)
            stream.start()
            self.device_used = device_name if index is not None else "system default"
        except Exception:
            if index is None:
                raise
            # The device the picker listed will not open right now (exclusive
            # mode, in use, driver asleep). Hearing nothing is worse than
            # hearing through the default microphone.
            stream = factory(None)
            stream.start()
            self.device_used = "system default"
            self.fell_back = True
        self._stream = stream

    def close(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass


# ── speaker ──────────────────────────────────────────────────────────────────

class Playback:
    """24 kHz mono int16 FIFO played from the device callback.

    ``on_frames(bytes, monotonic_time)`` (echo reference) and ``on_drained()``
    are delivered on the event loop.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, on_frames: Callable[[bytes, float], None],
                 on_drained: Callable[[], None], stream_factory=None) -> None:
        self._loop = loop
        self._on_frames = on_frames
        self._on_drained = on_drained
        self._factory = stream_factory
        self._stream = None
        self._lock = threading.Lock()
        self._buf = bytearray()
        self._active = False          # reply audio has been queued and not yet finished
        self._turn_ended = False      # the model said this reply is complete
        self._last_feed = 0.0
        self.ended_at = 0.0           # clock time the last reply stopped sounding (set on the audio thread itself)
        self.level = 0.0              # loudness of what the device is being given right now
        self.latency_s = 0.2
        self.device_used = "system default"
        self.fell_back = False
        self._numpy = None

    @property
    def is_open(self) -> bool:
        return self._stream is not None

    @property
    def active(self) -> bool:
        return self._active

    def _callback(self, outdata, frames, time_info, status) -> None:
        want = frames * 2
        drained = False
        with self._lock:
            take = min(len(self._buf), want)
            chunk = bytes(self._buf[:take])
            del self._buf[:take]
            if self._active and not self._buf:
                stalled = (now() - self._last_feed) > STALL_S
                if self._turn_ended or stalled:
                    self._active = False
                    self._turn_ended = False
                    self.ended_at = now()
                    drained = True
        outdata[:take] = chunk
        if take < want:
            outdata[take:want] = b"\x00" * (want - take)
        try:
            if take:
                np = self._numpy
                x = np.frombuffer(chunk, dtype=np.int16)
                rms = float(np.sqrt(np.mean(x.astype(np.float32) ** 2)))
                self.level = 0.0 if rms <= 60.0 else min(1.0, (rms - 60.0) / 2540.0)
                self._loop.call_soon_threadsafe(self._on_frames, chunk, now())
            else:
                self.level = 0.0
            if drained:
                self._loop.call_soon_threadsafe(self._on_drained)
        except Exception:
            pass

    def open(self, device_name: str = "") -> None:
        if self._stream is not None:
            return
        self._numpy = _np()      # resolved here so the real-time callback never imports anything
        factory = self._factory or (lambda dev: _sd().RawOutputStream(
            samplerate=SPEAKER_RATE, channels=1, dtype="int16", blocksize=BLOCK, device=dev, callback=self._callback))
        index = resolve_device(device_name, "output")
        self.fell_back = False
        try:
            stream = factory(index)
            stream.start()
            self.device_used = device_name if index is not None else "system default"
        except Exception:
            if index is None:
                raise
            stream = factory(None)
            stream.start()
            self.device_used = "system default"
            self.fell_back = True
        try:
            latency = float(getattr(stream, "latency", 0.0) or 0.0)
            if 0.0 < latency < 1.0:
                self.latency_s = latency   # measured, not guessed: sizes the echo tail
        except Exception:
            pass
        self._stream = stream

    def close(self) -> None:
        stream, self._stream = self._stream, None
        self.clear()
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    def feed(self, pcm: bytes) -> None:
        """Queue reply audio (event-loop thread)."""
        if not pcm:
            return
        with self._lock:
            if len(self._buf) + len(pcm) > MAX_BUFFER_S * SPEAKER_RATE * 2:
                return
            self._buf.extend(pcm)
            self._active = True
            self._turn_ended = False
            self._last_feed = now()

    def end_turn(self) -> None:
        """The model finished this reply; report ``drained`` once it has been heard."""
        with self._lock:
            self._turn_ended = True
            if self._active and not self._buf:
                # Nothing left to play (very short reply already consumed).
                self._active = False
                self._turn_ended = False
                self.ended_at = now()
                self._loop.call_soon(self._on_drained)

    def clear(self) -> bool:
        """Silence immediately. Returns True if anything was queued or playing."""
        with self._lock:
            was = self._active or bool(self._buf)
            if was:
                self.ended_at = now()
            self._buf.clear()
            self._active = False
            self._turn_ended = False
        self.level = 0.0
        return was
