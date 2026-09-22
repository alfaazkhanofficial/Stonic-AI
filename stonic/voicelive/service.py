"""STONIC's voice: microphone → Gemini Live → speakers, with STONIC as the brain.

``VoiceService`` is the only thing the rest of the application touches. It owns
the audio devices, the Live session, the echo guard and the state shown in the
UI, and it hands every real request to ``CoreService.chat`` so voice goes
through exactly the same planner, permission gate and verification as typing.

Threading model: PortAudio callbacks (microphone, speaker) and the push-to-talk
poller run on their own threads and only hand bytes to the event loop. Every
other line in this file runs on the event loop.

Heavy imports (numpy, sounddevice, google-genai) happen on ``start()``, so
nobody pays for voice until they use it.
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import time
from collections import deque
from enum import StrEnum

from stonic.core.models import ChatInput, HealthCheck
from stonic.voicelive import persona
from stonic.voicelive.controls import CHORDS, PushToTalk, supported as ptt_supported
from stonic.voicelive.live import GEMINI_ENDPOINT, LiveRunner

REQUEST_TIMEOUT_S = 170
DISCARD_WINDOW_S = 5.0
PREROLL_BLOCKS = 8            # ~0.5 s of microphone kept while speaking, so a barge-in loses no onset
TAIL_MARGIN_S = 0.25
LEVEL_TICK_S = 0.08


class VoiceState(StrEnum):
    OFF = "off"
    CONNECTING = "connecting"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    MUTED = "muted"
    STANDBY = "standby"          # push-to-talk mode, key not held
    RECONNECTING = "reconnecting"
    ERROR = "error"


class VoiceUnavailable(Exception):
    """Voice cannot start; the message says why in words a user can act on."""


class VoiceService:
    def __init__(self, core, credentials, *, connector=None, mic_stream_factory=None,
                 speaker_stream_factory=None, key_state=None) -> None:
        self.core = core
        self.credentials = credentials
        self._connector = connector
        self._mic_factory = mic_stream_factory
        self._speaker_factory = speaker_stream_factory
        self._key_state = key_state
        self._now = time.monotonic       # injectable clock (tests)
        self.running = False
        self.muted = False
        self.session_id = "main"
        self.detail = ""
        self.fatal = ""
        self._had_connection = False
        self._ptt_held = False
        self._ptt_active_mode = "off"
        self._last_state = VoiceState.OFF
        self._subscribers: set[asyncio.Queue] = set()
        self._tasks: list[asyncio.Task] = []
        self._runner: LiveRunner | None = None
        self._mic = None
        self._playback = None
        self._guard = None
        self._ptt: PushToTalk | None = None
        self._mic_q: asyncio.Queue | None = None
        self._preroll: deque[bytes] = deque(maxlen=PREROLL_BLOCKS)
        self._tail_until = 0.0
        self._speech_ended_at = 0.0    # when the last reply stopped sounding; blocks captured before it heard it
        self._discard_until = 0.0
        self._last_activity = self._now()
        self._mic_level = 0.0
        self._request_task: asyncio.Task | None = None
        self._start_lock = asyncio.Lock()
        self._np = None

    # ── settings / keys ─────────────────────────────────────────────────────
    @property
    def settings(self):
        return self.core.config.values

    def live_settings(self):
        return self.core.config.values

    def api_key(self) -> str:
        """Saved key first, then environment. Deliberately NOT ``SecretStore.key``:
        that falls back to the LLM provider's environment key for unknown endpoints,
        and an xKiro key must never be sent to Google."""
        try:
            saved = self.credentials._load().get(GEMINI_ENDPOINT, "")
        except (OSError, ValueError, UnicodeError, AttributeError):
            saved = ""
        return saved or os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")

    def credential_configured(self) -> bool:
        return bool(self.api_key())

    def save_key(self, key: str) -> None:
        self.credentials.save(key, GEMINI_ENDPOINT)
        self.core.events.publish("security", "Voice (Gemini) credential saved using Windows user-bound encryption.")

    def delete_key(self) -> None:
        self.credentials.delete(GEMINI_ENDPOINT)
        self.core.events.publish("security", "Voice (Gemini) credential removed.")

    # ── host interface used by LiveRunner ───────────────────────────────────
    def system_prompt(self) -> str:
        s = self.settings
        return persona.system_prompt(s.display_name, s.response_style, s.gaming_mode)

    def log(self, level: str, message: str) -> None:
        self.core.events.publish("voice", message, level if level in {"info", "warning", "error"} else "info")

    def on_connecting(self) -> None:
        self.detail = "Connecting to Gemini Live…" if not self._had_connection else "Reconnecting to Gemini Live…"
        self._publish_state()

    def on_connected(self, resumed: bool) -> None:
        first = not self._had_connection
        self._had_connection = True
        self.fatal = ""
        self.detail = "Listening."
        if first or not resumed:
            self.log("info", "Voice session connected.")
        self._publish_state()

    def on_disconnected(self, reason: str, retrying: bool) -> None:
        self.detail = reason
        if self._playback:
            self._playback.clear()
        self.log("warning", reason)
        self._publish_state()

    def on_fatal(self, reason: str) -> None:
        self.fatal = reason
        self.detail = reason
        self.log("error", reason)
        self._publish_state()
        asyncio.get_running_loop().call_soon(lambda: asyncio.ensure_future(self.stop(keep_error=True)))

    def on_audio(self, pcm: bytes) -> None:
        if self._now() < self._discard_until:
            return   # tail of a reply the user already cut off
        if self._playback:
            self._playback.feed(pcm)
            self._touch()
            self._publish_state()

    def _speech_ended(self, tail: bool = True) -> None:
        now = self._now()
        self._speech_ended_at = now
        self._tail_until = now + self._tail_length() if tail else 0.0

    def on_server_interrupted(self) -> None:
        self._discard_until = 0.0
        if self._playback and self._playback.clear():
            self._speech_ended()
        self._publish_state()

    def on_turn_complete(self) -> None:
        self._discard_until = 0.0
        if self._playback:
            self._playback.end_turn()

    def on_tools_changed(self, pending: int) -> None:
        self._publish_state()

    def cancel_running_request(self) -> None:
        self.core.cancel()

    def on_exchange(self, user: str, assistant: str, used_tool: bool) -> None:
        """Casual turns are stored like typed ones. Requests that went through the
        engine were already stored by ``chat`` and must not be duplicated."""
        if used_tool:
            return
        sid = self.session_id
        if user:
            self.core.append(sid, "user", user)
            self._emit({"type": "transcript", "role": "user", "text": user})
        if assistant:
            self.core.append(sid, "assistant", assistant)
            self._emit({"type": "transcript", "role": "assistant", "text": assistant})
        if user or assistant:
            self.core.events.emit("conversation", {"session_id": sid})

    async def run_request(self, request: str) -> dict:
        """The ``ask_stonic`` tool: run the request through the real pipeline."""
        text = (request or "").strip()[:12000]
        if not text:
            return {"ok": False, "error": "The request was empty."}
        core = self.core
        if core.lock.locked():
            return {"ok": False, "error": "STONIC is busy with another request. Try again in a moment."}
        self._touch()
        task = asyncio.ensure_future(core.chat(ChatInput(content=text, session_id=self.session_id)))
        self._request_task = task
        try:
            done, _ = await asyncio.wait({task}, timeout=REQUEST_TIMEOUT_S)
            if not done:
                core.cancel()
                await asyncio.wait({task}, timeout=5)
                return {"ok": False, "error": "That took too long and was stopped."}
            message = task.result()
        except asyncio.CancelledError:
            core.cancel()
            raise
        finally:
            self._request_task = None
        core.events.emit("conversation", {"session_id": self.session_id})
        waiting = core.db.query("SELECT COUNT(*) AS n FROM jobs WHERE session_id=? AND status='waiting_approval'",
                                (self.session_id,))[0]["n"]
        return {"ok": True, "reply": str(message.get("content", "")), "approval_required": bool(waiting)}

    # ── lifecycle ───────────────────────────────────────────────────────────
    async def start(self, session_id: str | None = None) -> dict:
        async with self._start_lock:
            if self.running:
                if session_id:
                    self.set_session(session_id)
                return self.status()
            self.fatal = ""
            s = self.settings
            if not s.voice_cloud_consent:
                raise VoiceUnavailable("Voice streams your microphone to Google's Gemini Live while it is on. "
                                       "Allow that in Settings → Privacy first.")
            if not self.credential_configured():
                raise VoiceUnavailable("Add a Gemini API key in Settings → Voice to use voice.")
            try:
                import numpy as np
                from stonic.voicelive import audio
                from stonic.voicelive.echo import EchoGuard, pcm_level
                audio._sd()
            except (ImportError, OSError) as error:
                raise VoiceUnavailable(f"Audio libraries are unavailable ({type(error).__name__}). "
                                       "Run Setup-Stonic.cmd to install them.") from error
            self._np, self._pcm_level, self._mic_rate = np, pcm_level, audio.MIC_RATE
            self.set_session(session_id)
            loop = asyncio.get_running_loop()
            self._guard = EchoGuard()
            self._mic_q = asyncio.Queue(maxsize=200)
            self._playback = audio.Playback(loop, self._on_playback_frames, self._on_drained, self._speaker_factory)
            self._mic = audio.Microphone(loop, self._offer_mic, self._gate, self._mic_factory)
            try:
                self._playback.open(s.voice_output_device)
                if not self.muted:
                    self._mic.open(s.voice_input_device)
            except Exception as error:
                self._release_devices()
                raise VoiceUnavailable(f"The audio device could not be opened ({type(error).__name__}). "
                                       "Check Settings → Voice → devices and Windows sound privacy settings.") from error
            for note, dev in (("speaker", self._playback), ("microphone", self._mic)):
                if getattr(dev, "fell_back", False):
                    self.log("warning", f"The chosen {note} could not be opened; using the system default.")
            self.running = True
            self._had_connection = False
            self._last_activity = self._now()
            self._runner = LiveRunner(self, self._connector)
            self._ptt = PushToTalk(loop, self._on_ptt, self._key_state)
            self._tasks = [asyncio.create_task(self._runner.run(), name="voicelive-runner"),
                           asyncio.create_task(self._mic_loop(), name="voicelive-mic"),
                           asyncio.create_task(self._housekeeping(), name="voicelive-housekeeping"),
                           asyncio.create_task(self._levels(), name="voicelive-levels")]
            self.detail = "Connecting to Gemini Live…"
            self.log("info", "Voice started.")
            self._sync_ptt()
            self._publish_state()
            return self.status()

    async def stop(self, keep_error: bool = False) -> dict:
        async with self._start_lock:
            if not self.running and not self._tasks:
                return self.status()
            self.running = False
            if self._request_task and not self._request_task.done():
                self.core.cancel()
            
            self._release_devices()
            
            tasks, self._tasks = self._tasks, []
            for task in tasks:
                if task is not asyncio.current_task():
                    task.cancel()
            await asyncio.gather(*[t for t in tasks if t is not asyncio.current_task()], return_exceptions=True)
            if self._ptt:
                self._ptt.stop()
                self._ptt = None
            self._runner = None
            self._ptt_held = False
            self._ptt_active_mode = "off"
            self._preroll.clear()
            if not keep_error:
                self.fatal = ""
                self.detail = "Voice is off."
            self.log("info", "Voice stopped.")
            self._publish_state()
            return self.status()

    async def shutdown(self) -> None:
        with contextlib.suppress(Exception):
            await self.stop()

    def autostart_soon(self) -> None:
        async def go():
            try:
                await self.start()
            except VoiceUnavailable as error:
                self.detail = str(error)
                self.log("warning", f"Voice did not start automatically: {error}")
        asyncio.get_running_loop().create_task(go(), name="voicelive-autostart")

    def _release_devices(self) -> None:
        for dev in (self._mic, self._playback):
            if dev is not None:
                with contextlib.suppress(Exception):
                    dev.close()
        self._mic = None
        self._playback = None

    def set_session(self, session_id: str | None) -> None:
        if session_id:
            ChatInput(content="x", session_id=session_id)   # reuse the API's own validation
            self.session_id = session_id

    # ── controls ────────────────────────────────────────────────────────────
    def set_muted(self, muted: bool) -> dict:
        if muted == self.muted:
            return self.status()
        self.muted = muted
        if self.running and self._mic is not None:
            if muted:
                self._mic.close()
                self._preroll.clear()
                if self._runner:
                    self._runner.end_audio()
            else:
                try:
                    self._mic.open(self.settings.voice_input_device)
                except Exception as error:
                    self.muted = True
                    raise VoiceUnavailable(f"The microphone could not be opened ({type(error).__name__}).") from error
        self._publish_state()
        return self.status()

    def interrupt(self) -> dict:
        """Stop talking now (and stop working on a spoken request)."""
        if self._playback and self._playback.clear():
            self._discard_until = self._now() + DISCARD_WINDOW_S
            self._speech_ended()
        if self._runner and self._runner.pending_tools:
            self._runner.cancel_tools(answer=True)
            self.core.cancel()
        self._publish_state()
        return self.status()

    def set_ptt_held(self, held: bool) -> dict:
        """Hold-to-talk from the UI button (the global key uses the same path)."""
        self._on_ptt(held)
        return self.status()

    def _on_ptt(self, held: bool) -> None:
        if held == self._ptt_held:
            return
        self._ptt_held = held
        if not held and self._runner:
            self._runner.end_audio()
        self._publish_state()

    def _sync_ptt(self) -> None:
        mode = self.settings.voice_push_to_talk
        if mode == self._ptt_active_mode or self._ptt is None:
            return
        self._ptt_active_mode = mode
        if mode in CHORDS:
            if not self._ptt.start(mode):
                self.log("warning", "Push-to-talk keys work only on Windows; use the on-screen button.")
        else:
            self._ptt.stop()
            self._ptt_held = False
        self._publish_state()

    def _gate(self) -> bool:
        """Should the microphone callback deliver this block? Read on the audio thread: keep it trivial."""
        if not self.running or self.muted:
            return False
        return self.settings.voice_push_to_talk == "off" or self._ptt_held

    def _touch(self) -> None:
        self._last_activity = self._now()

    def _tail_length(self) -> float:
        return (self._playback.latency_s if self._playback else 0.2) + TAIL_MARGIN_S

    # ── audio routing ───────────────────────────────────────────────────────
    def _on_playback_frames(self, chunk: bytes, when: float) -> None:
        if self._guard is not None and self._np is not None:
            self._guard.note_output(self._np.frombuffer(chunk, dtype=self._np.int16), 24000, when)

    def _on_drained(self) -> None:
        self._speech_ended()
        self._publish_state()

    def _offer_mic(self, data: bytes, when: float) -> None:
        q = self._mic_q
        if q is None:
            return
        if q.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                q.get_nowait()
        q.put_nowait((data, when))

    async def _mic_loop(self) -> None:
        assert self._mic_q is not None
        failures = 0
        while True:
            data, when = await self._mic_q.get()
            try:
                self._route(data, when)
            except Exception as error:
                failures += 1
                if failures in (1, 50):
                    self.log("error", f"Microphone routing error ({type(error).__name__}).")

    def _route(self, data: bytes, when: float) -> None:
        if not self._gate() or self._runner is None or self._playback is None:
            return
        np = self._np
        pcm = np.frombuffer(data, dtype=np.int16)
        self._mic_level = self._pcm_level(pcm)
        # Judge by when the block was CAPTURED, not when it is processed: a block
        # heard while STONIC was talking is still echo if the reply ended a moment
        # before this line ran.
        speaking = self._playback.active or when <= max(self._speech_ended_at, self._playback.ended_at)
        in_tail = (not speaking) and when < self._tail_until
        guard = self._guard

        if speaking:
            # Nothing is streamed while STONIC talks, but the guard listens anyway:
            # that is how it learns this room, so it is already calibrated for the
            # tail after the reply and for voice barge-in if it is switched on.
            guard.is_user_speech(pcm, self._mic_rate, when)
            if self.settings.voice_barge_in != "guarded":
                return
            self._preroll.append(data)
            if guard.calibrated and guard.reliable and guard.sustained:
                self._barge_in()
            return
        if in_tail:
            # Mic stays open; only what the guard explains as our own echo is dropped.
            if not guard.is_user_speech(pcm, self._mic_rate, when):
                return
            self._tail_until = 0.0
        elif guard is not None and guard.has_output and when >= self._tail_until:
            guard.reset()   # tail over: forget the output history, keep what was learned

        if self._mic_level > 0.15:
            self._touch()
        self._runner.offer_audio(data)

    def _barge_in(self) -> None:
        """The user spoke over STONIC: stop talking, and give the server the words it missed."""
        self._playback.clear()
        self._discard_until = self._now() + DISCARD_WINDOW_S
        self._speech_ended(tail=False)
        self._guard.reset()
        for block in self._preroll:
            self._runner.offer_audio(block)
        self._preroll.clear()
        self._touch()
        self.log("info", "Interrupted by voice.")
        self._publish_state()

    # ── state, events, SSE ──────────────────────────────────────────────────
    def state(self) -> VoiceState:
        if self.fatal and not self.running:
            return VoiceState.ERROR
        if not self.running:
            return VoiceState.OFF
        if self.muted:
            return VoiceState.MUTED
        runner = self._runner
        if runner is None or not runner.connected:
            return VoiceState.RECONNECTING if self._had_connection else VoiceState.CONNECTING
        if self._playback is not None and self._playback.active:
            return VoiceState.SPEAKING
        if runner.pending_tools:
            return VoiceState.THINKING
        if self.settings.voice_push_to_talk != "off" and not self._ptt_held:
            return VoiceState.STANDBY
        return VoiceState.LISTENING

    def _publish_state(self) -> None:
        state = self.state()
        self._last_state = state
        self._emit({"type": "state", **self.status()})

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subscribers.add(q)
        q.put_nowait({"type": "state", **self.status()})
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def _emit(self, event: dict) -> None:
        for q in tuple(self._subscribers):
            while q.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()
            q.put_nowait(event)

    async def _levels(self) -> None:
        quiet = False
        while True:
            await asyncio.sleep(LEVEL_TICK_S)
            if not self._subscribers:
                continue
            level_in = self._mic_level if not self.muted else 0.0
            level_out = self._playback.level if self._playback else 0.0
            self._mic_level *= 0.6     # decay: the microphone path only writes while audio arrives
            if level_in < 0.02 and level_out < 0.02:
                if quiet:
                    continue
                quiet = True
                level_in = level_out = 0.0
            else:
                quiet = False
            self._emit({"type": "level", "in": round(level_in, 3), "out": round(level_out, 3)})

    async def _housekeeping(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            self._sync_ptt()
            minutes = self.settings.voice_idle_sleep_minutes
            busy = (self._playback is not None and self._playback.active) or (self._runner and self._runner.pending_tools)
            if minutes and not busy and self._now() - self._last_activity > minutes * 60:
                self.log("info", f"Voice stopped after {minutes} idle minutes.")
                self.detail = f"Stopped after {minutes} idle minutes. Press the microphone to resume."
                asyncio.ensure_future(self.stop(keep_error=True))
                return

    # ── reporting ───────────────────────────────────────────────────────────
    def status(self) -> dict:
        s = self.settings
        guard = self._guard
        barge_ok = bool(guard and guard.calibrated and guard.reliable)
        return {
            "state": self.state().value, "detail": self.detail,
            "running": self.running, "muted": self.muted, "session_id": self.session_id,
            "push_to_talk": s.voice_push_to_talk, "push_to_talk_held": self._ptt_held, "push_to_talk_global": ptt_supported(),
            "barge_in": s.voice_barge_in, "barge_in_active": s.voice_barge_in == "guarded" and barge_ok,
            "consent": s.voice_cloud_consent, "credential_configured": self.credential_configured(),
            "model": s.voice_live_model,
            "input_device": getattr(self._mic, "device_used", None), "output_device": getattr(self._playback, "device_used", None),
            "echo": guard.snapshot() if guard else None,
        }

    async def devices(self) -> dict:
        try:
            from stonic.voicelive import audio
            inputs = await asyncio.to_thread(audio.list_devices, "input")
            outputs = await asyncio.to_thread(audio.list_devices, "output")
            return {"available": True, "input": inputs, "output": outputs}
        except (ImportError, OSError) as error:
            return {"available": False, "input": [], "output": [], "reason": f"Audio libraries unavailable ({type(error).__name__})."}

    def health(self) -> HealthCheck | None:
        """Shown in diagnostics once the user has engaged with voice; absent before,
        so a text-only install reports exactly what it always did."""
        s = self.settings
        engaged = s.voice_cloud_consent or self.credential_configured() or self.running or bool(self.fatal)
        if not engaged:
            return None
        base = dict(id="voice", name="Voice (Gemini Live)")
        if self.fatal:
            return HealthCheck(**base, status="failed", detail=self.fatal)
        if self.running:
            state = self.state()
            if state in {VoiceState.CONNECTING, VoiceState.RECONNECTING}:
                return HealthCheck(**base, status="recovering", detail=self.detail or "Connecting to Gemini Live…")
            return HealthCheck(**base, status="ready",
                               detail=f"Voice is on ({state.value}). Requests run through STONIC's normal planner and approvals.")
        if not s.voice_cloud_consent:
            return HealthCheck(**base, status="unconfigured", detail="Allow cloud voice in Settings → Privacy to use voice.")
        if not self.credential_configured():
            return HealthCheck(**base, status="unconfigured", detail="Add a Gemini API key in Settings → Voice.")
        return HealthCheck(**base, status="ready", detail=self.detail or "Voice is off. Press the microphone to start.")