"""Measure how STONIC's echo guard behaves on THIS microphone and THESE speakers.

Run on the PC that will use voice (nothing is sent to the internet):

    python scripts/voicelive-calibrate.py                 # uses your Windows defaults
    python scripts/voicelive-calibrate.py --input "USB Mic" --output "Speakers"
    python scripts/voicelive-calibrate.py --list          # show device names
    python scripts/voicelive-calibrate.py --simulate desk # no hardware: prove the script itself runs

It plays a speech-like test signal through the speakers, listens through the
microphone, and reports whether STONIC can tell its own voice from yours here.
Phase 3 asks you to talk over the playback, which is the honest test of
"interrupt by voice".
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sys as _sys
if _sys.stdout.encoding and _sys.stdout.encoding.lower() != "utf-8":
    # Windows consoles often default to a legacy codepage (cp1252/cp437) that cannot encode
    # arbitrary Unicode; a plain print() of anything outside it would crash this script.
    _sys.stdout.reconfigure(errors="replace")
    _sys.stderr.reconfigure(errors="replace")


import numpy as np

from stonic.voicelive import audio
from stonic.voicelive.echo import EchoGuard, pcm_level

OUT_RATE, IN_RATE = audio.SPEAKER_RATE, audio.MIC_RATE
BLOCK = audio.BLOCK


def speech_like(seconds: float, seed: int, rate: int, f0: float = 120.0) -> np.ndarray:
    """A voice-shaped test signal: moving formants on a pulsing source. Not intelligible, and not meant to be."""
    rng = np.random.default_rng(seed)
    n, seg = int(seconds * rate), int(0.09 * rate)
    freqs = np.fft.rfftfreq(seg, 1 / rate)
    out = np.zeros(n)
    for start in range(0, n - seg, seg):
        centres = rng.uniform([250, 800, 1800], [800, 2200, 3600])
        shape = sum(np.exp(-0.5 * ((freqs - c) / w) ** 2) * a for c, w, a in zip(centres, (120, 220, 350), (1.0, 0.7, 0.35)))
        out[start:start + seg] += np.fft.irfft(np.fft.rfft(rng.standard_normal(seg)) * (shape + 0.02), n=seg) * np.hanning(seg)
    t = np.arange(n) / rate
    out *= (0.6 + 0.4 * np.sin(2 * np.pi * f0 * t)) * (0.55 + 0.45 * np.sin(2 * np.pi * 3.2 * t))
    return out / (np.abs(out).max() + 1e-9)


def to_int16(x: np.ndarray, peak: float) -> np.ndarray:
    return (np.clip(x, -1, 1) * peak * 32767).astype(np.int16)


class Recorder:
    """Real device I/O: plays a buffer and records the microphone, block by block, with timestamps."""

    def __init__(self, input_name: str, output_name: str) -> None:
        import sounddevice as sd
        self.sd = sd
        self.mic_blocks: list[tuple[float, bytes]] = []
        self.out_blocks: list[tuple[float, bytes]] = []
        self.play = np.zeros(0, dtype=np.int16)
        self.pos = 0
        self.mic = sd.RawInputStream(samplerate=IN_RATE, channels=1, dtype="int16", blocksize=BLOCK,
                                     device=audio.resolve_device(input_name, "input"), callback=self._in)
        self.spk = sd.RawOutputStream(samplerate=OUT_RATE, channels=1, dtype="int16", blocksize=BLOCK,
                                      device=audio.resolve_device(output_name, "output"), callback=self._out)
        self.latency = float(getattr(self.spk, "latency", 0.0) or 0.0)

    def _in(self, indata, frames, info, status):
        self.mic_blocks.append((time.monotonic(), bytes(indata)))

    def _out(self, outdata, frames, info, status):
        chunk = self.play[self.pos:self.pos + frames]
        self.pos += frames
        raw = chunk.tobytes()
        outdata[:len(raw)] = raw
        outdata[len(raw):frames * 2] = b"\x00" * (frames * 2 - len(raw))
        if len(raw):
            self.out_blocks.append((time.monotonic(), raw))

    def run(self, seconds: float, play: np.ndarray | None = None):
        self.mic_blocks.clear(); self.out_blocks.clear()
        self.play = play if play is not None else np.zeros(0, dtype=np.int16)
        self.pos = 0
        self.mic.start(); self.spk.start()
        try:
            end = time.monotonic() + seconds
            while time.monotonic() < end:          # visible progress: a silent 8 s wait looks like a hang
                print(f"  {max(0, int(end - time.monotonic()) + 1)}...", end=" ", flush=True)
                time.sleep(min(1.0, max(0.0, end - time.monotonic())))
            print()
        finally:
            self.mic.stop(); self.spk.stop()
        return list(self.out_blocks), list(self.mic_blocks)

    def close(self):
        self.mic.close(); self.spk.close()


class Simulated:
    """No hardware: a room that delays, colours and adds noise to what is played, and an optional talker."""

    def __init__(self, room: str) -> None:
        self.room = {"desk": (0.35, 0.12, 0.004), "noisy": (0.30, 0.11, 0.02), "phones": (0.004, 0.05, 0.0005)}[room]
        self.latency = 0.05
        self.talk: np.ndarray | None = None

    def run(self, seconds: float, play: np.ndarray | None = None):
        atten, delay, noise = self.room
        n_out, n_in = int(seconds * OUT_RATE), int(seconds * IN_RATE)
        played = np.zeros(n_out, dtype=np.int16) if play is None else np.pad(play, (0, max(0, n_out - len(play))))[:n_out]
        rng = np.random.default_rng(4)
        heard = np.interp(np.arange(n_in) / IN_RATE, np.arange(n_out) / OUT_RATE, played.astype(np.float64)) * atten
        heard = np.concatenate([np.zeros(int(delay * IN_RATE)), heard])[:n_in] + noise * 32767 * rng.standard_normal(n_in)
        if self.talk is not None:
            heard = heard + np.pad(self.talk, (0, max(0, n_in - len(self.talk))))[:n_in]
        heard = np.clip(heard, -32768, 32767).astype(np.int16)
        t0 = 1000.0
        outs = [(t0 + (i + BLOCK) / OUT_RATE, played[i:i + BLOCK].tobytes()) for i in range(0, n_out - BLOCK, BLOCK)]
        mics = [(t0 + (i + BLOCK) / IN_RATE, heard[i:i + BLOCK].tobytes()) for i in range(0, n_in - BLOCK, BLOCK)]
        return outs, mics

    def close(self):
        pass


def judge(outs, mics, guard: EchoGuard, count_after: float):
    """Feed one run through the guard in time order.

    Returns (rows, triggers): rows are per-microphone-block (time, flagged, level); triggers are the times at
    which STONIC would have decided "that is a voice, stop talking", i.e. the guard's sustained evidence bar.
    """
    events = [(t, 0, b) for t, b in outs] + [(t, 1, b) for t, b in mics]
    events.sort(key=lambda e: (e[0], e[1]))
    start = events[0][0]
    rows, triggers, run = [], [], 0
    for t, kind, raw in events:
        pcm = np.frombuffer(raw, dtype=np.int16)
        if kind == 0:
            guard.note_output(pcm, OUT_RATE, t)
            continue
        flagged = guard.is_user_speech(pcm, IN_RATE, t)
        run = run + 1 if flagged else 0
        if t - start >= count_after:
            rows.append((t - start, flagged, pcm_level(pcm)))
            if run == guard.required_blocks:
                triggers.append(t - start)
    return rows, triggers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default="", help="microphone name (default: system default)")
    parser.add_argument("--output", default="", help="speaker name (default: system default)")
    parser.add_argument("--list", action="store_true", help="list devices and exit")
    parser.add_argument("--simulate", choices=["desk", "noisy", "phones"], help="use a simulated room instead of hardware")
    parser.add_argument("--volume", type=float, default=0.5, help="test signal loudness 0-1 (use your normal listening volume)")
    parser.add_argument("--no-talk", action="store_true", help="skip phase 3 (talking over the playback)")
    args = parser.parse_args()

    if args.list:
        print("Microphones:"); [print("  ", n) for n in audio.list_devices("input")]
        print("Speakers:"); [print("  ", n) for n in audio.list_devices("output")]
        return 0

    rig = Simulated(args.simulate) if args.simulate else Recorder(args.input, args.output)
    guard = EchoGuard()
    volume = max(0.05, min(1.0, args.volume))
    print(f"Speaker latency reported by the device: {rig.latency * 1000:.0f} ms")

    print("\nPhase 1/3: staying quiet for 3 s to hear the room (be silent)...")
    outs, mics = rig.run(3.0)
    ambient = np.mean([pcm_level(np.frombuffer(b, dtype=np.int16)) for _, b in mics]) if mics else 0.0
    print(f"  room noise level: {ambient:.2f} (0 = silent, 1 = loud)")

    print("\nPhase 2/3: playing a test voice for 8 s (you should HEAR it; if not, pick your speakers with --output). Stay quiet...")
    tone = to_int16(speech_like(8.0, 5, OUT_RATE), volume)
    outs, mics = rig.run(8.5, tone)
    rows, false_triggers = judge(outs, mics, guard, count_after=2.0)
    coupling = np.mean([r[2] for r in rows]) if rows else 0.0
    print(f"  how loudly the microphone hears the speakers: {coupling:.2f}")
    print(f"  times its own echo would have interrupted it: {len(false_triggers)} (must be 0)")

    detected = None
    if not args.no_talk:
        print("\nPhase 3/3: the test voice plays again for 8 s. After 3 s, TALK NORMALLY over it for about 4 s...")
        if isinstance(rig, Simulated):
            rig.talk = np.concatenate([np.zeros(int(3.5 * IN_RATE)), to_int16(speech_like(4.0, 11, IN_RATE, f0=190), 0.25)])
        outs, mics = rig.run(8.5, tone)
        _rows3, triggers3 = judge(outs, mics, guard, count_after=0.0)
        after = [t for t in triggers3 if t >= 3.0]
        detected = (after[0] - 3.0) if after else None
        print("  your voice was NOT recognised over the playback" if detected is None
              else f"  your voice was recognised {detected:.1f} s after you started talking")
    rig.close()

    snap = guard.snapshot()
    print("\n-- Result -----------------------------------------")
    print(f"learned: floor {snap['floor']}, bar {snap['threshold']}, reliable {snap['reliable']}, calibrated {snap['calibrated']}")
    verdict = []
    if coupling < 0.03:
        verdict.append("Your microphone barely hears the speakers (headphones, or far apart). Echo is not a problem here.")
    elif false_triggers or not snap["reliable"]:
        verdict.append("Echo and voices look too alike in this room. Keep 'Interrupt by speaking' OFF; the after-speech echo guard still protects you.")
    elif not args.no_talk and (detected is None or detected > 2.0):
        verdict.append("Your voice was missed or slow to register over the playback. Speak up or move closer, or keep 'Interrupt by speaking' OFF.")
    else:
        verdict.append("This room looks good. You can set 'Interrupt by speaking' to Guarded in Settings -> Voice.")
    if ambient > 0.10:
        verdict.append("The room is noisy; expect the guard to be less certain. A headset microphone helps most.")
    print("\n".join(verdict))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nStopped. Nothing was changed. Run it again and let it finish (about 25 seconds, no key presses needed).")
        raise SystemExit(130)
