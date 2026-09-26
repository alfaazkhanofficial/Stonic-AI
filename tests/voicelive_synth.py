"""Synthetic audio for voice tests: speech-like signals, rooms, and a playback/microphone simulator.

Not speech recognition material — just signals with time-varying spectral shape,
which is what the echo guard reasons about. Deterministic for a given seed.
"""
from __future__ import annotations

import numpy as np

SR_OUT = 24000
SR_IN = 16000
SR_SIM = 48000


def _resample(x: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    n_to = int(round(len(x) * sr_to / sr_from))
    spectrum = np.fft.rfft(x)
    out = np.zeros(n_to // 2 + 1, dtype=complex)
    m = min(len(out), len(spectrum))
    out[:m] = spectrum[:m]
    return np.fft.irfft(out, n=n_to) * (n_to / len(x))


def speech_like(seconds: float, seed: int, f0: float = 120.0, sr: int = SR_SIM, segment: float = 0.09) -> np.ndarray:
    """Harmonic source shaped by moving formants, with syllable-like energy dips."""
    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    t = np.arange(n) / sr
    out = np.zeros(n)
    seg = int(segment * sr)
    freqs = np.fft.rfftfreq(seg, 1.0 / sr)
    for start in range(0, n - seg, seg):
        centres = rng.uniform([250, 800, 1800], [800, 2200, 3600])
        widths = np.array([120.0, 220.0, 350.0]) * rng.uniform(0.8, 1.4)
        shape = sum(np.exp(-0.5 * ((freqs - c) / w) ** 2) * a for c, w, a in zip(centres, widths, (1.0, 0.7, 0.35)))
        shape = shape + 0.02 * np.exp(-freqs / 4000)
        noise = np.fft.rfft(rng.standard_normal(seg)) * shape
        out[start:start + seg] += np.fft.irfft(noise, n=seg) * np.hanning(seg)
    voicing = 0.6 + 0.4 * np.sin(2 * np.pi * f0 * t)
    env = 0.55 + 0.45 * np.sin(2 * np.pi * rng.uniform(2.5, 4.0) * t + rng.uniform(0, 6))
    sig = out * voicing * env
    return sig / (np.abs(sig).max() + 1e-9)


def apply_eq(x: np.ndarray, sr: int, gains_db: dict[float, float]) -> np.ndarray:
    """Static speaker/room colouring: piecewise-linear gain (dB) over frequency."""
    freqs = np.fft.rfftfreq(len(x), 1.0 / sr)
    pts = sorted(gains_db)
    curve = np.interp(freqs, pts, [gains_db[p] for p in pts])
    return np.fft.irfft(np.fft.rfft(x) * 10 ** (curve / 20), n=len(x))


def delay(x: np.ndarray, seconds: float, sr: int) -> np.ndarray:
    k = int(seconds * sr)
    return np.concatenate([np.zeros(k), x])[: len(x)]


ROOMS = {
    "desk":       dict(atten=0.35, delay=0.12, eq={100: -12, 300: -3, 1500: 3, 4000: -2, 8000: -9}, reverb=0.0, noise=0.004),
    "laptop":     dict(atten=0.25, delay=0.09, eq={100: -20, 400: -8, 1200: 4, 3000: 6, 8000: -6}, reverb=0.0, noise=0.006),
    "reverberant": dict(atten=0.40, delay=0.15, eq={100: -6, 500: 0, 2000: 2, 8000: -4}, reverb=0.55, noise=0.005),
    "noisy":      dict(atten=0.30, delay=0.11, eq={100: -10, 500: -2, 2000: 3, 8000: -6}, reverb=0.2, noise=0.02),
}


def room_echo(out48: np.ndarray, room: dict) -> np.ndarray:
    echo = delay(out48, room["delay"], SR_SIM)
    if room["reverb"]:
        tail = np.zeros_like(echo)
        for k, g in ((0.03, 0.6), (0.07, 0.4), (0.13, 0.25), (0.21, 0.12)):
            tail += g * delay(echo, k, SR_SIM)
        echo = echo + room["reverb"] * tail
    echo = apply_eq(echo, SR_SIM, room["eq"])
    return room["atten"] * echo


def simulate(guard, room_name: str, seconds: float = 6.0, user_from: float | None = None,
             user_level: float = 1.0, seed: int = 1, blocks_out=1024, blocks_in=1024):
    """Feed a guard with what playback and the microphone would have produced.

    Returns per-microphone-block records: (time, is_user_flag_from_guard, user_present).
    """
    out48 = speech_like(seconds, seed)
    echo48 = room_echo(out48, ROOMS[room_name])
    rng = np.random.default_rng(seed + 100)
    mic48 = echo48 + ROOMS[room_name]["noise"] * rng.standard_normal(len(echo48))
    if user_from is not None:
        user48 = speech_like(seconds, seed + 7, f0=190.0)
        gate = (np.arange(len(user48)) / SR_SIM >= user_from)
        # Same loudness as the echo, scaled by user_level.
        ref = np.sqrt(np.mean(echo48 ** 2) + 1e-12)
        user48 = user48 / (np.sqrt(np.mean(user48 ** 2)) + 1e-12) * ref * user_level
        mic48 = mic48 + user48 * gate
    out24 = (_resample(out48, SR_SIM, SR_OUT) * 12000).astype(np.int16)
    mic16 = (_resample(mic48, SR_SIM, SR_IN) * 12000).astype(np.int16)

    events = []
    for i in range(0, len(out24) - blocks_out, blocks_out):
        events.append((i / SR_OUT, "out", out24[i:i + blocks_out]))
    for i in range(0, len(mic16) - blocks_in, blocks_in):
        events.append(((i + blocks_in) / SR_IN, "mic", mic16[i:i + blocks_in]))
    events.sort(key=lambda e: (e[0], e[1] == "mic"))
    records = []
    for when, kind, block in events:
        if kind == "out":
            guard.note_output(block, SR_OUT, when=when + blocks_out / SR_OUT)
        else:
            flag = guard.is_user_speech(block, SR_IN, when=when)
            records.append((when, flag, user_from is not None and when - blocks_in / SR_IN >= user_from))
    return records
