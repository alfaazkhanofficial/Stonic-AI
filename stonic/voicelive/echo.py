"""Telling the user's voice apart from STONIC's own voice coming back through the speakers.

Why this exists
---------------
A voice assistant that keeps the microphone open hears itself. Streaming that
to the model is how an assistant answers its own last sentence. The blunt fix
is to deafen the microphone while it talks, which also makes interrupting it
impossible. This module lets the microphone stay open and drops only the
blocks that are explained by what was just played.

How it decides (no per-machine tuning constant)
-----------------------------------------------
Every played slice and every microphone block is reduced to a handful of
speech-band powers. Echo is not just loud, it is *the same spectral pattern we
just played*, so:

1. Recent output is aggregated over a small set of plausible delays (device
   buffers plus the room), and the best-matching delay is chosen.
2. Playback is not heard flat: speakers and rooms colour it. A per-band gain
   vector is therefore learned online, so the colouring stops looking like a
   mismatch.
3. What the microphone heard that this scaled, coloured copy cannot explain is
   the *residual*. Echo leaves almost none. A second voice leaves a lot.
4. The residual bar is not a constant. It is placed just above the residuals
   this room has actually produced for echo, and it is only ever learned from
   blocks judged to be echo, so a talking user cannot raise the bar over
   themselves.

Everything here runs on the event-loop thread only; callers hand blocks over
from the audio threads. One small FFT per block.

This is signal processing, validated against synthetic rooms in the test-suite.
Real rooms differ: ``scripts/voicelive-calibrate.py`` reports what this module
measures on the actual microphone and speakers.
"""
from __future__ import annotations

import time
from collections import deque

import numpy as np

# Log-spaced edges across the band that carries speech. Coarse on purpose: fine
# bins would track pitch, and pitch is exactly what differs between two people
# saying the same word. Timbre is what echo preserves.
BAND_EDGES = (200, 400, 700, 1100, 1700, 2600, 3800, 5200, 7000)
BANDS = len(BAND_EDGES) - 1

HISTORY_S = 2.0            # how far back an echo could have been played
LAGS = tuple(i * 0.025 for i in range(21))  # 0 .. 0.5 s candidate device+room delays (coarse)
REFINE_STEP = 0.006        # then refined around the best coarse delay
MIN_LEVEL = 0.06           # below this the microphone hears (almost) nothing back
SMOOTH = 4                 # blocks averaged for a decision (~256 ms): one block of noise is not a voice
MIN_USER = 0.12            # never call a smoothed residual below this a voice
HEAD_Q = 97                # percentile of observed echo residual the bar must clear
HEAD_MULT = 1.25           # ...with this much headroom above it
UNRELIABLE_BAR = 0.30      # if the room forces the bar this high, content separates voice from echo poorly
BLOCKS_NORMAL = 6          # consecutive judged-voice blocks before a barge-in is believed (on top of SMOOTH)
BLOCKS_NOISY = 10          # same, in a room where echo and voice look alike
WINDOW = 60                # echo residuals kept to characterise the room
WARMUP = 16                # blocks of learning before anyone is judged
RELEARN_WINDOW = 100       # blocks (~6 s) considered when deciding the room has changed
RELEARN_DENSITY = 85       # ...if this many of them looked like a voice while we play, it is the room, not a talker
AMBIENT_WINDOW = 100       # microphone levels remembered to find the room's noise floor (~6 s)
AMBIENT_MULT = 1.6         # a voice must clear the room's noise floor by this factor
QUIET_HOLD = 3             # quiet blocks tolerated inside a run of voice (a pause between words is not the end)
QUIET_ROOM = 0.04          # ...but only where the room is quiet enough that a quiet block really is a pause
ISOLATED = 0.05            # ...and the microphone barely hears the speakers (headphones): with audible echo a quiet block proves nothing
LEARN_BELOW = 0.7          # ...but only blocks this far under the bar teach the room model
GAIN_RATE = 0.12           # how fast the per-band colouring is learned
LEVEL_FLOOR = 60.0         # int16 RMS at/below which a block is room silence
LEVEL_FULL = 2600.0        # int16 RMS at/above which the level reads as full


def pcm_level(pcm) -> float:
    """Map int16 samples to a 0..1 loudness. Never raises."""
    try:
        x = np.asarray(pcm, dtype=np.float32)
        if x.size == 0:
            return 0.0
        rms = float(np.sqrt(np.mean(x * x)))
    except Exception:
        return 0.0
    if rms <= LEVEL_FLOOR:
        return 0.0
    return min(1.0, (rms - LEVEL_FLOOR) / (LEVEL_FULL - LEVEL_FLOOR))


_freq_cache: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}


def _tables(n: int, sr: int):
    key = (n, sr)
    hit = _freq_cache.get(key)
    if hit is None:
        freqs = np.fft.rfftfreq(n, 1.0 / sr)
        masks = np.stack([(freqs >= BAND_EDGES[i]) & (freqs < BAND_EDGES[i + 1]) for i in range(BANDS)])
        hit = (np.hanning(n).astype(np.float32), masks)
        if len(_freq_cache) > 8:
            _freq_cache.clear()
        _freq_cache[key] = hit
    return hit


def band_power(pcm, sr: int) -> np.ndarray:
    """Mean power per speech band. Time-normalised, so slices of different
    lengths can be averaged, and sample-rate agnostic."""
    x = np.asarray(pcm, dtype=np.float32)
    n = int(x.size)
    if n < 64:
        return np.zeros(BANDS, dtype=np.float64)
    win, masks = _tables(n, sr)
    spectrum = np.fft.rfft((x - x.mean()) * win)
    power = (spectrum.real ** 2 + spectrum.imag ** 2) / (n * n)
    return np.array([power[m].sum() for m in masks], dtype=np.float64)


class EchoGuard:
    """Classifies microphone blocks while STONIC is (or was just) speaking.

    ``note_output`` from the playback path, ``is_user_speech`` from the
    microphone path. Both are cheap and neither blocks.
    """

    def __init__(self) -> None:
        self._hist: deque[tuple[float, float, np.ndarray, float]] = deque()  # (t_end, dur, samples, level)
        self._out_sr = 0
        self._log_gain = np.zeros(BANDS)      # learned colouring, log domain, zero-mean
        self._residuals: list[float] = []     # recent ECHO residuals only
        self._floor = 0.10                    # typical echo residual here; learned
        self._head = 0.13                     # near-worst echo residual here; learned
        self._seen = 0
        self._run = 0                         # consecutive blocks judged to be a voice
        self._last_similarity = 0.0
        self._recent: deque[float] = deque(maxlen=SMOOTH)   # raw per-block residuals
        self._levels: deque[float] = deque(maxlen=AMBIENT_WINDOW)
        self._quiet = 0                       # consecutive quiet blocks
        self._coupling = 1.0                  # slow average of how loudly the microphone hears the speakers; assume the worst until measured
        self._voice_window: deque[int] = deque(maxlen=RELEARN_WINDOW)

    # ── diagnostics ─────────────────────────────────────────────────────────
    @property
    def calibrated(self) -> bool:
        return self._seen >= 8

    @property
    def floor(self) -> float:
        return self._floor

    @property
    def reliable(self) -> bool:
        """False when the acoustics are too poor to judge on content alone."""
        return self.threshold < UNRELIABLE_BAR

    @property
    def threshold(self) -> float:
        return max(MIN_USER, self._head * HEAD_MULT)

    @property
    def required_blocks(self) -> int:
        return BLOCKS_NORMAL if self.reliable else BLOCKS_NOISY

    @property
    def run(self) -> int:
        return self._run

    @property
    def sustained(self) -> bool:
        """True once a voice has held long enough to be believed."""
        return self._run >= self.required_blocks

    @property
    def last_similarity(self) -> float:
        return self._last_similarity

    @property
    def has_output(self) -> bool:
        return bool(self._hist)

    def snapshot(self) -> dict:
        return {"calibrated": self.calibrated, "floor": round(self._floor, 3),
                "threshold": round(self.threshold, 3), "reliable": self.reliable,
                "required_blocks": self.required_blocks}

    def reset(self) -> None:
        """Playback ended: drop the output history, keep what was learned."""
        self._hist.clear()
        self._run = 0
        self._last_similarity = 0.0
        self._recent.clear()

    # ── output side ─────────────────────────────────────────────────────────
    def note_output(self, pcm, sr: int, when: float | None = None) -> None:
        """Record a slice of what is being played. ``when`` is the time the slice
        was handed to the device."""
        try:
            x = np.asarray(pcm)
            if x.size < 64:
                return
            t = time.monotonic() if when is None else when
            if sr != self._out_sr:
                self._hist.clear()
                self._out_sr = sr
            self._hist.append((t, x.size / sr, x.astype(np.float32), pcm_level(x)))
            cutoff = t - HISTORY_S
            while self._hist and self._hist[0][0] < cutoff:
                self._hist.popleft()
        except Exception:
            pass  # bookkeeping must never disturb playback

    # ── microphone side ─────────────────────────────────────────────────────
    def is_user_speech(self, pcm, sr: int, when: float | None = None) -> bool:
        """True if this microphone block is a voice that is not our own echo."""
        try:
            return self._judge(pcm, sr, time.monotonic() if when is None else when)
        except Exception:
            return False  # if anything goes wrong, do not feed our own voice back

    def _learn(self, residual: float) -> None:
        self._residuals.append(residual)
        if len(self._residuals) > WINDOW:
            del self._residuals[:-WINDOW]
        if len(self._residuals) >= WARMUP:
            self._floor = float(np.percentile(self._residuals, 35))
            self._head = float(np.percentile(self._residuals, HEAD_Q))

    def _window(self, lo: float, hi: float):
        """The output samples that were sounding between two times, cut to the
        same span as the microphone block so both are measured through the same
        window. Returns (samples, coverage 0..1)."""
        sr = self._out_sr
        n = int(round((hi - lo) * sr))
        if n < 64:
            return None, 0.0
        out = np.zeros(n, dtype=np.float32)
        covered = 0
        for ts, d, samples, _lvl in self._hist:
            start = ts - d
            a, b = max(lo, start), min(hi, ts)
            if b <= a:
                continue
            src0 = int(round((a - start) * sr))
            dst0 = int(round((a - lo) * sr))
            count = min(int(round((b - a) * sr)), len(samples) - src0, n - dst0)
            if count <= 0:
                continue
            out[dst0:dst0 + count] = samples[src0:src0 + count]
            covered += count
        return out, covered / n

    def _reference(self, t_end: float, dur: float, lag: float):
        """Output power over the window that could be sounding in this block."""
        window, coverage = self._window(t_end - dur - lag, t_end - lag)
        if window is None or coverage < 0.8:
            return None, 0.0
        return band_power(window, self._out_sr), pcm_level(window)

    @staticmethod
    def _fit(power: np.ndarray, shaped: np.ndarray) -> float:
        """How much of the (coloured) reference the microphone block contains."""
        denom = float(shaped @ shaped)
        return max(0.0, float(power @ shaped) / denom) if denom > 0 else 0.0

    def _judge(self, pcm, sr: int, t: float) -> bool:
        x = np.asarray(pcm)
        if x.size < 64:
            return False
        level = pcm_level(x)
        dur = x.size / sr
        self._levels.append(level)
        if self._run == 0 and self._hist and max(h[3] for h in list(self._hist)[-6:]) > 0.3:
            # Measured only while no voice run is in progress, and clipped so the first blocks of a
            # person starting to talk cannot make headphones look like speakers.
            self._coupling += 0.08 * (min(level, 0.15) - self._coupling)
        # A fan, a hum, a breath between words: sound that is always there is not a
        # voice. The quietest tenth of what this microphone has recently heard is
        # the room's noise floor; something must stand clearly above it.
        ambient = float(np.percentile(self._levels, 10)) if len(self._levels) >= 20 else 0.0
        if level < max(MIN_LEVEL, AMBIENT_MULT * ambient):
            level = 0.0
        if level < MIN_LEVEL:
            # We play and the microphone hears nothing back: headphones, or a
            # microphone far from the speaker. That is a real measurement.
            # Only count it when the speakers are loud *right now*; a quiet mic
            # in a pause between words says nothing about how well echo is explained.
            if self._hist and max(h[3] for h in list(self._hist)[-6:]) > 0.3:
                self._learn(0.0)
                self._seen += 1     # a silent microphone under loud playback IS calibration (headphones, driver echo-cancelling)
            self._quiet += 1
            if self._run > 0 and self._quiet <= QUIET_HOLD and ambient < QUIET_ROOM and self._coupling < ISOLATED:
                return False       # a breath inside a run of speech: hold the run, do not restart it
            self._recent.append(0.0)
            self._run = 0
            return False
        self._quiet = 0
        if not self._hist:
            self._run += 1
            self._recent.clear()
            return True  # nothing playing that we know of: anything audible is theirs

        power = band_power(x, sr)
        total = float(power.sum())
        if total <= 1e-12:
            return False

        gain = np.exp(self._log_gain)

        def score(lag: float):
            ref, ref_level = self._reference(t, dur, lag)
            if ref is None or ref_level <= 0.0:
                return None
            shaped = gain * ref
            denom = float(shaped @ shaped)
            if denom < 1e-24:
                return None
            alpha = self._fit(power, shaped)
            residual = float(np.maximum(power - alpha * shaped, 0.0).sum()) / total
            return residual, alpha, ref, ref_level

        best = None  # (residual, alpha, reference, lag_level)
        best_lag = 0.0
        for lag in LAGS:
            cand = score(lag)
            if cand and (best is None or cand[0] < best[0]):
                best, best_lag = cand, lag
        if best is not None:
            for k in range(-4, 5):
                lag = best_lag + k * REFINE_STEP
                if lag < 0 or k == 0:
                    continue
                cand = score(lag)
                if cand and cand[0] < best[0]:
                    best = cand
        if best is None:
            self._last_similarity = 0.0
            self._recent.append(1.0)
            self._run += 1
            return True  # nothing in the window explains it: not our sound
        raw, _alpha, ref, _lvl = best
        self._last_similarity = 1.0 - raw
        # Decide on a few blocks together. A single block of speech-like noise
        # can match its reference badly by chance; several together cannot.
        self._recent.append(raw)
        residual = float(np.mean(self._recent))

        # Two stages, and the order matters both times. While warming up learn
        # from EVERY block: in a poor room the very first echo block already
        # sits above any sensible starting bar, so judging first would call it
        # a voice, never learn from it, and mischaracterise the room forever.
        # Once warm, learn only from blocks BELOW the bar: feeding a talking
        # user back in would lift the bar over themselves.
        warming = len(self._residuals) < WARMUP
        speech = (not warming) and residual >= self.threshold
        self._voice_window.append(1 if speech else 0)
        if len(self._voice_window) == RELEARN_WINDOW and sum(self._voice_window) >= RELEARN_DENSITY:
            # Nearly every block for ~6 s looks like a voice while we are the only thing
            # playing: the room changed (speakers moved, new EQ). A talker leaves gaps.
            self._residuals.clear()
            self._log_gain[:] = 0.0
            self._floor, self._head = 0.10, 0.13
            self._voice_window.clear()
            self._run = 0
            return False
        if not speech:
            # Learn only from blocks that are clearly echo. A block just under the
            # bar might be a quiet voice, and learning from it would raise the bar
            # over the next one.
            if warming or residual < LEARN_BELOW * self.threshold:
                self._learn(residual)
                self._seen += 1
                self._update_gain(power, ref)
            self._run = 0
            return False
        self._run += 1
        return True

    def _update_gain(self, power: np.ndarray, ref: np.ndarray) -> None:
        """Nudge the learned per-band colouring towards what this echo block showed."""
        ok = (ref > 1e-9 * max(float(ref.sum()), 1e-12)) & (power > 1e-9 * max(float(power.sum()), 1e-12))
        if int(ok.sum()) < 4:
            return
        target = np.zeros(BANDS)
        target[ok] = np.log(np.clip(power[ok] / ref[ok], 1e-3, 1e3))
        target[ok] -= target[ok].mean()
        step = GAIN_RATE * np.where(ok, target - self._log_gain, 0.0)
        self._log_gain = np.clip(self._log_gain + step, -3.0, 3.0)
        self._log_gain -= self._log_gain.mean()
