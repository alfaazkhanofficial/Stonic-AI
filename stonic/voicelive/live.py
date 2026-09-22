"""The Gemini Live session: connect, stream, survive.

This module owns the network side of voice and nothing else. Audio devices,
STONIC's brain and the UI are reached through a ``host`` object, which is what
lets the whole thing be tested against a scripted fake session.

Behaviours worth knowing about (all covered by tests):

* Optional setup fields (VAD tuning, the explicit tool ``behavior``) are tried
  first and dropped one tier at a time if the server rejects the setup, so a
  model that does not accept a field still connects.
* A resumption handle keeps context across the ~10 minute connection limit and
  ``GoAway``. It lives in memory only. If a *resumed* session dies within
  seconds, the handle is dropped so one poisoned context cannot loop forever.
* Reconnect backoff doubles from 3 s to 60 s and resets after a healthy session.
  Authentication failures stop retrying; quota exhaustion waits longer.
* The ``receive()`` iterator of the SDK ends after every model turn, so it is
  looped, with a guard against a closed socket turning that loop into a spin.
* Tool calls run as tasks so audio keeps flowing while STONIC works, and are
  cancelled when the server says the user barged in.
"""
from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any, Callable

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com"
TOOL_NAME = "ask_stonic"
INITIAL_BACKOFF = 3.0
MAX_BACKOFF = 60.0
QUOTA_BACKOFF = 45.0
HEALTHY_AFTER_S = 20.0        # a session this old counts as having worked
POISON_WINDOW_S = 10.0        # a resumed session dying this fast drops the handle
GOAWAY_GRACE_S = 25.0
EMPTY_RECEIVES_BEFORE_DROP = 25
QUEUE_MAX = 64
_END = object()


class AuthError(Exception):
    """The key was refused. Retrying will not help."""


class QuotaError(Exception):
    pass


class SetupRejected(Exception):
    """The server refused the session configuration (close 1007 / invalid argument)."""


def classify(error: BaseException, established: bool) -> Exception:
    text = f"{type(error).__name__} {error}".lower()
    if any(k in text for k in ("api key not valid", "api_key_invalid", "unauthenticated", "permission_denied",
                                "permission denied", " 401", " 403", "invalid api key")):
        return AuthError(str(error))
    if any(k in text for k in ("resource_exhausted", "quota", " 429", "rate limit")):
        return QuotaError(str(error))
    if any(k in text for k in ("1007", "invalid argument", "invalid_argument", "unsupported")):
        return SetupRejected(str(error))
    return error if isinstance(error, Exception) else Exception(str(error))


def build_declarations(with_behavior: bool) -> list[dict]:
    fn: dict[str, Any] = {
        "name": TOOL_NAME,
        "description": (
            "Hand a request to STONIC's reasoning and action engine and get back its verified answer. "
            "Use it for anything beyond casual conversation: questions needing facts or current information, "
            "the user's PC, files, apps, windows, notes, tasks, reminders, memory, preferences, web research, "
            "screen capture, system or gaming status, and every action. Returns {ok, reply, approval_required}."),
        "parameters": {
            "type": "OBJECT",
            "properties": {"request": {
                "type": "STRING",
                "description": "What the user asked for, in their own words and language, keeping every detail (names, numbers, paths, times)."}},
            "required": ["request"],
        },
    }
    if with_behavior:
        fn["behavior"] = "BLOCKING"   # the model waits for the answer; explicit because newer models default to async
    return [{"function_declarations": [fn]}]


def build_config(settings, system_prompt: str, handle: str | None, tier: int) -> dict:
    """Setup message. ``tier`` 0 = everything, 1 = no VAD tuning, 2 = also no tool behavior."""
    config: dict[str, Any] = {
        "response_modalities": ["AUDIO"],
        "system_instruction": system_prompt,
        "input_audio_transcription": {},
        "output_audio_transcription": {},
        "tools": build_declarations(with_behavior=tier < 2),
        "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": settings.voice_name}}},
        "context_window_compression": {"sliding_window": {}},
        "session_resumption": {"handle": handle},
    }
    if tier < 1:
        config["realtime_input_config"] = {"automatic_activity_detection": {
            "silence_duration_ms": int(settings.voice_end_of_speech_ms), "prefix_padding_ms": 150}}
    return config


def default_connector(api_key: str):
    """Real connector. Imported lazily: nobody pays for the SDK until voice starts."""
    from google import genai
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
    return lambda model, config: client.aio.live.connect(model=model, config=config)


class LiveRunner:
    def __init__(self, host, connector: Callable[[str], Callable] | None = None,
                 sleep: Callable[[float], Any] = asyncio.sleep) -> None:
        self.host = host
        self._connector = connector or default_connector
        self._sleep = sleep
        self._handle: str | None = None
        self._tier = 0
        self._send_q: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX)
        self._session = None
        self._tools: dict[str, asyncio.Task] = {}
        self._cancelled: set[str] = set()
        self._answer_when_cancelled: set[str] = set()
        self._goaway_at: float | None = None
        self._user_text: list[str] = []
        self._model_text: list[str] = []
        self._used_tool = False
        self.connected = False

    # ── public ──────────────────────────────────────────────────────────────
    def offer_audio(self, pcm: bytes) -> None:
        """Queue a microphone block. When the network stalls, old audio is dropped, not new."""
        if self._send_q.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._send_q.get_nowait()
        self._send_q.put_nowait(pcm)

    def end_audio(self) -> None:
        """The microphone stopped (mute / push-to-talk released): flush the server's audio cache."""
        if self._send_q.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._send_q.get_nowait()
        self._send_q.put_nowait(_END)

    def cancel_tools(self, answer: bool = False) -> None:
        """Stop running requests. ``answer=True`` (the user pressed stop) still tells the model
        the request was cancelled, so it is not left waiting for a reply that will never come;
        otherwise (the server cancelled, or we are shutting down) no answer is sent."""
        for call_id, task in list(self._tools.items()):
            (self._answer_when_cancelled if answer else self._cancelled).add(call_id)
            task.cancel()

    @property
    def pending_tools(self) -> int:
        return len(self._tools)

    async def run(self) -> None:
        backoff = INITIAL_BACKOFF
        while True:
            started = time.monotonic()
            try:
                await self._run_once()
                backoff = INITIAL_BACKOFF
                self.host.on_disconnected("The connection was renewed.", retrying=True)
                continue
            except asyncio.CancelledError:
                raise
            except BaseException as raw:  # noqa: BLE001 - classified below
                error = classify(raw, self.connected)
                lived = time.monotonic() - started
                self.connected = False
                self._drop_session_state()
                if isinstance(error, AuthError):
                    self.host.on_fatal("Google rejected the API key. Check it in Settings → Voice.")
                    return
                if isinstance(error, SetupRejected):
                    if self._handle and lived < POISON_WINDOW_S:
                        self._handle = None
                        self.host.log("warning", "Resumed voice session was rejected; starting fresh.")
                        continue
                    if self._tier < 2:
                        self._tier += 1
                        self.host.log("warning", f"Voice setup option not accepted; retrying with a simpler setup (level {self._tier}).")
                        continue
                    self.host.on_disconnected(f"The voice service rejected the setup: {error}", retrying=True)
                    wait = backoff
                elif isinstance(error, QuotaError):
                    self.host.on_disconnected("Gemini quota or rate limit reached; waiting before retrying.", retrying=True)
                    wait = max(backoff, QUOTA_BACKOFF)
                else:
                    self.host.on_disconnected(f"Voice connection lost ({type(error).__name__}).", retrying=True)
                    wait = backoff
                if lived >= HEALTHY_AFTER_S:
                    wait, backoff = INITIAL_BACKOFF, INITIAL_BACKOFF
                else:
                    backoff = min(backoff * 2, MAX_BACKOFF)
                await self._sleep(wait)

    # ── one connection ──────────────────────────────────────────────────────
    async def _run_once(self) -> None:
        settings = self.host.live_settings()
        key = self.host.api_key()
        if not key:
            raise AuthError("no key")
        model = settings.voice_live_model
        config = build_config(settings, self.host.system_prompt(), self._handle, self._tier)
        connect = self._connector(key)
        self.host.on_connecting()
        async with connect(model, config) as session:
            self._session = session
            self.connected = True
            self._goaway_at = None
            self.host.on_connected(resumed=bool(self._handle))
            tasks = [asyncio.create_task(self._recv_loop(session), name="voicelive-recv"),
                     asyncio.create_task(self._send_loop(session), name="voicelive-send")]
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for finished in done:
                    finished.result()   # re-raise the failure that ended the session
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                self.cancel_tools()
                self.connected = False
                self._session = None

    def _drop_session_state(self) -> None:
        self.cancel_tools()
        self._tools.clear()

    async def _send_loop(self, session) -> None:
        while True:
            item = await self._send_q.get()
            if item is _END:
                await session.send_realtime_input(audio_stream_end=True)
            else:
                await session.send_realtime_input(audio={"data": item, "mime_type": "audio/pcm;rate=16000"})

    async def _recv_loop(self, session) -> None:
        empty = 0
        while True:
            seen = False
            async for message in session.receive():
                seen = True
                empty = 0
                if await self._handle_message(session, message):
                    return   # renew the connection (GoAway)
            if not seen:
                empty += 1
                if empty >= EMPTY_RECEIVES_BEFORE_DROP:
                    raise ConnectionError("The voice socket closed.")
                await asyncio.sleep(0.05)

    # ── messages ────────────────────────────────────────────────────────────
    async def _handle_message(self, session, message) -> bool:
        update = getattr(message, "session_resumption_update", None)
        if update is not None and getattr(update, "resumable", False) and getattr(update, "new_handle", None):
            self._handle = update.new_handle

        if getattr(message, "go_away", None) is not None and self._goaway_at is None:
            self._goaway_at = time.monotonic()
            self.host.log("info", "The voice service will renew this connection shortly.")

        data = getattr(message, "data", None)
        if data:
            self.host.on_audio(data)

        content = getattr(message, "server_content", None)
        if content is not None:
            if getattr(content, "interrupted", False):
                self.host.on_server_interrupted()
            it = getattr(content, "input_transcription", None)
            if it is not None and getattr(it, "text", None):
                self._add(self._user_text, it.text)
            ot = getattr(content, "output_transcription", None)
            if ot is not None and getattr(ot, "text", None):
                self._add(self._model_text, ot.text)
            if getattr(content, "turn_complete", False):
                self.host.on_turn_complete()
                if not self._tools:
                    self._finish_exchange()
                    if self._goaway_at is not None:
                        return True

        if self._goaway_at is not None and time.monotonic() - self._goaway_at > GOAWAY_GRACE_S and not self._tools:
            return True

        call = getattr(message, "tool_call", None)
        if call is not None:
            for fc in getattr(call, "function_calls", None) or []:
                self._start_tool(session, fc)

        cancel = getattr(message, "tool_call_cancellation", None)
        if cancel is not None and getattr(cancel, "ids", None):
            for call_id in cancel.ids:
                self._cancelled.add(call_id)
                task = self._tools.get(call_id)
                if task:
                    task.cancel()
            self.host.cancel_running_request()
        return False

    @staticmethod
    def _add(parts: list[str], text: str) -> None:
        # The service re-sends the tail of a transcript around tool calls.
        if parts and parts[-1] == text and len(text) > 3:
            return
        parts.append(text)

    def _finish_exchange(self) -> None:
        user = " ".join("".join(self._user_text).split())
        model = " ".join("".join(self._model_text).split())
        used = self._used_tool
        self._user_text, self._model_text, self._used_tool = [], [], False
        if user or model:
            self.host.on_exchange(user, model, used_tool=used)

    # ── tools ───────────────────────────────────────────────────────────────
    def _start_tool(self, session, fc) -> None:
        call_id = getattr(fc, "id", None) or f"call-{len(self._tools)}"
        self._used_tool = True
        task = asyncio.create_task(self._run_tool(session, call_id, getattr(fc, "name", ""), dict(getattr(fc, "args", None) or {})),
                                   name=f"voicelive-tool-{call_id}")
        self._tools[call_id] = task
        self.host.on_tools_changed(len(self._tools))

    async def _run_tool(self, session, call_id: str, name: str, args: dict) -> None:
        try:
            if name != TOOL_NAME:
                result = {"ok": False, "error": f"Unknown tool {name}."}
            else:
                result = await self.host.run_request(str(args.get("request", "")))
        except asyncio.CancelledError:
            result = None
        except Exception as error:  # a broken tool must not break the conversation
            self.host.log("error", f"Voice request failed ({type(error).__name__}).")
            result = {"ok": False, "error": "The request failed unexpectedly."}
        finally:
            self._tools.pop(call_id, None)
            self.host.on_tools_changed(len(self._tools))
        answer = call_id in self._answer_when_cancelled
        self._answer_when_cancelled.discard(call_id)
        if result is None and answer and self._session is session:
            result = {"ok": False, "error": "The user cancelled this request."}
        if result is None or call_id in self._cancelled or self._session is not session:
            self._cancelled.discard(call_id)
            return
        if self._tier >= 2:
            result = {**result, "scheduling": "WHEN_IDLE"}   # model defaulted to async: say when to speak
        try:
            await session.send_tool_response(function_responses=[{"id": call_id, "name": name, "response": result}])
        except Exception as error:
            self.host.log("warning", f"Could not deliver the answer to the voice service ({type(error).__name__}).")
