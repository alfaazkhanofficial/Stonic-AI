"""Scripted stand-ins for the parts of voice that need a network or a sound card.

The Live messages are the SDK's real pydantic types, so the code under test
reads exactly the attributes it reads from Google.
"""
from __future__ import annotations

import asyncio

from google.genai import types

_CLOSED = object()


def m_audio(data: bytes):
    return types.LiveServerMessage(server_content=types.LiveServerContent(
        model_turn=types.Content(parts=[types.Part(inline_data=types.Blob(data=data, mime_type="audio/pcm;rate=24000"))])))


def m_turn_complete():
    return types.LiveServerMessage(server_content=types.LiveServerContent(turn_complete=True))


def m_interrupted():
    return types.LiveServerMessage(server_content=types.LiveServerContent(interrupted=True))


def m_user_text(text: str):
    return types.LiveServerMessage(server_content=types.LiveServerContent(input_transcription=types.Transcription(text=text)))


def m_model_text(text: str):
    return types.LiveServerMessage(server_content=types.LiveServerContent(output_transcription=types.Transcription(text=text)))


def m_tool_call(call_id: str, args: dict, name: str = "ask_stonic"):
    return types.LiveServerMessage(tool_call=types.LiveServerToolCall(
        function_calls=[types.FunctionCall(id=call_id, name=name, args=args)]))


def m_cancel(*ids: str):
    return types.LiveServerMessage(tool_call_cancellation=types.LiveServerToolCallCancellation(ids=list(ids)))


def m_handle(handle: str, resumable: bool = True):
    return types.LiveServerMessage(session_resumption_update=types.LiveServerSessionResumptionUpdate(new_handle=handle, resumable=resumable))


def m_goaway():
    return types.LiveServerMessage(go_away=types.LiveServerGoAway(time_left="10s"))


class FakeSession:
    """Behaves like the SDK session: ``receive`` ends after each turn_complete."""

    def __init__(self) -> None:
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.audio: list[bytes] = []
        self.stream_ends = 0
        self.tool_responses: list[dict] = []
        self.closed = False

    def push(self, *messages) -> None:
        for message in messages:
            self.inbox.put_nowait(message)

    def close_from_server(self, error: BaseException | None = None) -> None:
        """Server ends the connection. Without an error the socket is just closed and
        ``receive`` keeps returning immediately, as the SDK's does."""
        self.inbox.put_nowait(error or _CLOSED)

    async def send_realtime_input(self, *, audio=None, audio_stream_end=None, **_):
        if audio is not None:
            self.audio.append(audio["data"] if isinstance(audio, dict) else audio.data)
        if audio_stream_end:
            self.stream_ends += 1

    async def send_tool_response(self, *, function_responses):
        for response in function_responses:
            self.tool_responses.append(response if isinstance(response, dict) else response.model_dump())

    async def receive(self):
        while True:
            if self.closed:
                return
            item = await self.inbox.get()
            if item is _CLOSED:
                self.closed = True
                return
            if isinstance(item, BaseException):
                raise item
            yield item
            content = item.server_content
            if content is not None and content.turn_complete:
                return


class FakeConnector:
    """``connector(key)`` → ``connect(model, config)`` → async context manager."""

    session_class = FakeSession

    def __init__(self, failures: list[BaseException] | None = None) -> None:
        self.sessions: list[FakeSession] = []
        self.configs: list[dict] = []
        self.models: list[str] = []
        self.keys: list[str] = []
        self.failures = list(failures or [])
        self.connected = asyncio.Event()

    def __call__(self, key: str):
        self.keys.append(key)
        outer = self

        class _Ctx:
            def __init__(self, model, config):
                self.model, self.config = model, config

            async def __aenter__(self):
                outer.models.append(self.model)
                outer.configs.append(self.config)
                if outer.failures:
                    raise outer.failures.pop(0)
                session = outer.session_class()
                outer.sessions.append(session)
                outer.connected.set()
                return session

            async def __aexit__(self, *exc):
                return False

        return lambda model, config: _Ctx(model, config)

    @property
    def session(self) -> FakeSession:
        return self.sessions[-1]


class FakeMicStream:
    def __init__(self, callback):
        self.callback, self.started, self.closed = callback, False, False

    def start(self): self.started = True
    def stop(self): self.started = False
    def close(self): self.closed = True

    def push(self, pcm: bytes) -> None:
        self.callback(pcm, len(pcm) // 2, None, None)


class FakeSpeakerStream:
    latency = 0.05

    def __init__(self, callback):
        self.callback, self.started, self.closed = callback, False, False

    def start(self): self.started = True
    def stop(self): self.started = False
    def close(self): self.closed = True

    def pump(self, frames: int = 1024) -> bytes:
        out = bytearray(frames * 2)
        self.callback(out, frames, None, None)
        return bytes(out)


class FakeDevices:
    """Factories the service uses instead of sounddevice; remembers the streams it made."""

    def __init__(self) -> None:
        self.service = None
        self.mic: FakeMicStream | None = None
        self.speaker: FakeSpeakerStream | None = None
        self.opened: list[tuple[str, object]] = []
        self.fail_named = False

    def mic_factory(self, device):
        self.opened.append(("mic", device))
        self.mic = FakeMicStream(self.service._mic._callback)
        return self.mic

    def speaker_factory(self, device):
        self.opened.append(("speaker", device))
        self.speaker = FakeSpeakerStream(self.service._playback._callback)
        return self.speaker


async def wait_for(condition, timeout: float = 2.0, step: float = 0.01):
    end = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < end:
        if condition():
            return True
        await asyncio.sleep(step)
    return condition()
