"""Check that STONIC's live voice can actually reach Google from this PC.

    python scripts/voicelive-check.py                 # key from GEMINI_API_KEY, or the key saved in STONIC
    python scripts/voicelive-check.py --play          # also speak the reply through your speakers
    python scripts/voicelive-check.py --model gemini-3.1-flash-live-preview

It opens a real Gemini Live session using exactly the setup STONIC uses, asks the
model to say a short sentence (text in, audio out, so no microphone is needed),
and reports which setup tier the model accepted. The key is never printed.
"""
from __future__ import annotations

import argparse
import asyncio
import os
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


from stonic.config.settings import Settings
from stonic.voicelive.live import GEMINI_ENDPOINT, build_config, classify, default_connector
from stonic.voicelive.persona import system_prompt


def find_key(data_dir: Path) -> tuple[str, str]:
    """(key, where it came from). Environment first, then STONIC's encrypted store."""
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if os.environ.get(name):
            return os.environ[name], f"environment variable {name}"
    try:
        from stonic.security.secrets import SecretStore
        saved = SecretStore(data_dir)._load().get(GEMINI_ENDPOINT, "")
        if saved:
            return saved, f"key saved in STONIC ({data_dir})"
    except Exception as error:
        print(f"  (could not read STONIC's saved key: {type(error).__name__})")
    return "", ""


async def check(connector, model: str, play: bool = False, timeout: float = 25.0, out=print) -> bool:
    settings = Settings(voice_live_model=model)
    prompt = system_prompt("", "concise")
    for tier in (0, 1, 2):
        config = build_config(settings, prompt, None, tier)
        out(f"\nTrying setup tier {tier} " + ("(full: VAD tuning + explicit tool behavior)", "(no VAD tuning)", "(no tool behavior either)")[tier])
        try:
            async with connector(model, config) as session:
                out("  connected; asking the model to speak...")
                await session.send_realtime_input(text="Say exactly: STONIC voice check complete.")
                audio, transcript = bytearray(), []

                async def listen():
                    async for message in session.receive():
                        if getattr(message, "data", None):
                            audio.extend(message.data)
                        content = getattr(message, "server_content", None)
                        if content is not None and getattr(content, "output_transcription", None) and content.output_transcription.text:
                            transcript.append(content.output_transcription.text)
                try:
                    await asyncio.wait_for(listen(), timeout)     # a silent model must not hang this check
                except asyncio.TimeoutError:
                    pass
                seconds = len(audio) / 2 / 24000
                out(f"  received {seconds:.1f} s of speech audio" + (f': "{"".join(transcript).strip()}"' if transcript else ""))
                if seconds < 0.3:
                    out("  FAIL: the session opened but no speech came back.")
                    return False
                if play:
                    import sounddevice as sd
                    import numpy as np
                    sd.play(np.frombuffer(bytes(audio), dtype=np.int16), 24000)
                    sd.wait()
                out(f"\nOK: {model} works from this PC with setup tier {tier}.")
                if tier:
                    out("   (Tier > 0 means the model rejected an optional field; STONIC handles this automatically.)")
                return True
        except Exception as error:
            kind = type(classify(error, False)).__name__
            out(f"  failed: {kind}: {str(error)[:200]}")
            if kind == "AuthError":
                out("  Google rejected the key. Create a new one at aistudio.google.com/apikey.")
                return False
            if kind == "QuotaError":
                out("  Quota or rate limit reached. Wait a while, or check your Gemini plan.")
                return False
            if kind != "SetupRejected":
                out("  Network or service problem. Check your internet connection and any firewall or proxy.")
                return False
    out("\nFAIL: the model rejected every setup tier. Try --model with another Live model.")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=Settings().voice_live_model)
    parser.add_argument("--play", action="store_true", help="play the reply through the speakers")
    parser.add_argument("--data-dir", default=os.environ.get("STONIC_DATA_DIR", "data"))
    args = parser.parse_args()
    key, source = find_key(Path(args.data_dir))
    if not key:
        print("No Gemini key found. Set GEMINI_API_KEY, or save one in STONIC -> Settings -> Voice.")
        return 2
    print(f"Using the Gemini key from {source} (not shown).")
    return 0 if asyncio.run(check(default_connector(key), args.model, args.play)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
