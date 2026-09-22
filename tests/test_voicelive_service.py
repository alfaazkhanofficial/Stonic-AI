"""VoiceService end to end: real CoreService, real audio classes, fake sound card and fake Google."""
import asyncio
import json

import numpy as np
import pytest

from stonic.config.settings import Configuration
from stonic.core.models import Activity, ChatInput
from stonic.core.service import CoreService
from stonic.diagnostics.health import Diagnostics
from stonic.events.bus import EventBus
from stonic.security.secrets import SecretStore
from stonic.storage.database import Database
from stonic.tasks.contracts import Decision
from stonic.voicelive import VoiceService, VoiceUnavailable
from stonic.voicelive import audio as audio_module
from voicelive_fakes import (FakeConnector, FakeDevices, m_audio, m_interrupted, m_model_text, m_tool_call,
                             m_turn_complete, m_user_text, wait_for)
from voicelive_synth import SR_IN, SR_OUT, ROOMS, _resample, room_echo, speech_like, SR_SIM

GEMINI_KEY = "gem-test-key-12345"


class Provider:
    def __init__(self):
        self.calls = []

    def available(self, _): return True

    async def complete(self, settings, messages):
        self.calls.append(messages[-1]["content"])
        return "CPU is at twelve percent."


class Rig:
    pass


@pytest.fixture
async def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", GEMINI_KEY)
    monkeypatch.setenv("XKIRO_API_KEY", "xkiro-secret-value")
    monkeypatch.setenv("STONIC_LLM_API_KEY", "llm-secret-value")
    r = Rig()
    r.db = Database(tmp_path / "db.sqlite")
    r.config = Configuration(r.db)
    r.config.update({"voice_cloud_consent": True})
    r.provider = Provider()
    r.core = CoreService(r.db, r.config, Diagnostics(tmp_path), EventBus(r.db), r.provider)
    r.core.state.transition(Activity.IDLE)
    r.devices = FakeDevices()
    r.connector = FakeConnector()
    r.credentials = SecretStore(tmp_path)
    r.service = VoiceService(r.core, r.credentials, connector=r.connector, mic_stream_factory=r.devices.mic_factory,
                             speaker_stream_factory=r.devices.speaker_factory)
    r.devices.service = r.service
    r.tmp = tmp_path
    yield r
    await r.service.shutdown()
    r.db.close()


async def up(r, **settings):
    if settings:
        r.config.update(settings)
    await r.service.start()
    await asyncio.wait_for(r.connector.connected.wait(), 2)
    assert await wait_for(lambda: r.service._runner and r.service._runner.connected)
    return r.connector.session


def pcm(seed: int, n: int = 1024, amp: int = 6000) -> bytes:
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(n) * amp).astype(np.int16).tobytes()


# ── starting, and refusing to start ─────────────────────────────────────────

async def test_voice_needs_explicit_cloud_consent_and_a_key(rig):
    rig.config.update({"voice_cloud_consent": False})
    with pytest.raises(VoiceUnavailable, match="Privacy"):
        await rig.service.start()
    rig.config.update({"voice_cloud_consent": True})
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        __import__("os").environ.pop(name, None)
    with pytest.raises(VoiceUnavailable, match="Gemini API key"):
        await rig.service.start()
    assert rig.devices.opened == [] and rig.connector.keys == []     # no device touched, nothing sent anywhere


async def test_the_llm_providers_key_is_never_sent_to_google(rig, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(VoiceUnavailable):
        await rig.service.start()        # only XKIRO / STONIC_LLM keys exist: they must not be borrowed
    assert rig.service.api_key() == ""
    monkeypatch.setenv("GEMINI_API_KEY", GEMINI_KEY)
    await up(rig)
    assert rig.connector.keys == [GEMINI_KEY]


async def test_start_opens_speaker_then_microphone_and_is_idempotent(rig):
    await up(rig)
    assert [kind for kind, _ in rig.devices.opened] == ["speaker", "mic"]
    await rig.service.start()
    assert len(rig.devices.opened) == 2 and len(rig.connector.sessions) == 1


async def test_an_unopenable_device_is_reported_and_nothing_is_left_open(rig):
    def broken(device):
        raise OSError("device busy")
    rig.service._mic_factory = broken
    with pytest.raises(VoiceUnavailable, match="audio device"):
        await rig.service.start()
    assert not rig.service.running and rig.devices.speaker.closed


async def test_stop_releases_everything_and_voice_can_start_again(rig):
    await up(rig)
    await rig.service.stop()
    assert rig.devices.mic.closed and rig.devices.speaker.closed
    assert rig.service.state().value == "off" and not rig.service._tasks
    connections = len(rig.connector.sessions)
    await up(rig)
    assert len(rig.connector.sessions) == connections + 1


# ── microphone → Google ─────────────────────────────────────────────────────

async def test_microphone_blocks_reach_google(rig):
    session = await up(rig)
    for i in range(3):
        rig.devices.mic.push(pcm(i))
    assert await wait_for(lambda: len(session.audio) == 3)
    assert rig.service.status()["state"] == "listening"


async def test_mute_closes_the_microphone_device_and_flushes_the_stream(rig):
    session = await up(rig)
    rig.service.set_muted(True)
    assert rig.devices.mic.closed and rig.service.status()["state"] == "muted"
    assert await wait_for(lambda: session.stream_ends == 1)
    rig.service.set_muted(False)
    assert rig.devices.mic.started and not rig.devices.mic.closed
    rig.devices.mic.push(pcm(1))
    assert await wait_for(lambda: len(session.audio) == 1)


async def test_push_to_talk_sends_nothing_until_held_and_flushes_on_release(rig):
    session = await up(rig, voice_push_to_talk="f9")
    assert await wait_for(lambda: rig.service.status()["state"] == "standby", 3)
    rig.devices.mic.push(pcm(1))
    await asyncio.sleep(0.1)
    assert session.audio == []
    rig.service.set_ptt_held(True)
    rig.devices.mic.push(pcm(2))
    assert await wait_for(lambda: len(session.audio) == 1)
    rig.service.set_ptt_held(False)
    assert await wait_for(lambda: session.stream_ends == 1)
    rig.devices.mic.push(pcm(3))
    await asyncio.sleep(0.1)
    assert len(session.audio) == 1


async def test_the_global_key_poller_drives_push_to_talk(rig):
    down = {"ctrl": False, "space": False}
    rig.service._key_state = lambda name: down[name]
    session = await up(rig, voice_push_to_talk="ctrl+space")
    assert await wait_for(lambda: rig.service._ptt_active_mode == "ctrl+space", 3)
    down["ctrl"] = down["space"] = True
    assert await wait_for(lambda: rig.service._ptt_held)
    rig.devices.mic.push(pcm(1))
    assert await wait_for(lambda: len(session.audio) == 1)
    down["space"] = False
    assert await wait_for(lambda: not rig.service._ptt_held and session.stream_ends == 1)


# ── Google → speakers ───────────────────────────────────────────────────────

async def test_reply_audio_is_played_and_state_follows_speaking_then_listening(rig):
    session = await up(rig)
    reply = pcm(9, 4096, 3000)
    session.push(m_audio(reply), m_turn_complete())
    assert await wait_for(lambda: rig.service.status()["state"] == "speaking")
    heard = b"".join(rig.devices.speaker.pump(1024) for _ in range(4))
    assert heard[: len(reply)] == reply           # played back intact and in order
    assert await wait_for(lambda: rig.service.status()["state"] == "listening")


async def test_while_stonic_speaks_the_microphone_is_not_streamed_by_default(rig):
    session = await up(rig)
    session.push(m_audio(pcm(9, 8192, 3000)))
    assert await wait_for(lambda: rig.service._playback.active)
    for i in range(5):
        rig.devices.mic.push(pcm(20 + i))
    await asyncio.sleep(0.1)
    assert session.audio == []


async def test_interrupt_silences_at_once_and_discards_the_rest_of_that_reply(rig):
    session = await up(rig)
    session.push(m_audio(pcm(9, 8192, 3000)))
    assert await wait_for(lambda: rig.service._playback.active)
    rig.service.interrupt()
    assert rig.devices.speaker.pump(1024) == b"\x00" * 2048        # the very next callback is silent
    session.push(m_audio(pcm(10, 2048, 3000)))                      # rest of the interrupted reply still in flight
    await asyncio.sleep(0.1)
    assert not rig.service._playback.active
    session.push(m_turn_complete(), m_audio(pcm(11, 2048, 3000)))   # a new reply is a new turn
    assert await wait_for(lambda: rig.service._playback.active)


async def test_a_server_interruption_clears_playback(rig):
    session = await up(rig)
    session.push(m_audio(pcm(9, 8192, 3000)))
    assert await wait_for(lambda: rig.service._playback.active)
    session.push(m_interrupted())
    assert await wait_for(lambda: not rig.service._playback.active)
    assert rig.devices.speaker.pump(1024) == b"\x00" * 2048


# ── barge-in ────────────────────────────────────────────────────────────────

class StubGuard:
    calibrated = reliable = True
    required_blocks = 6
    has_output = True

    def __init__(self):
        self.run = 0
        self.resets = 0
        self.voice = False

    @property
    def sustained(self): return self.run >= self.required_blocks

    def is_user_speech(self, pcm, sr, when=None):
        self.run = self.run + 1 if self.voice else 0
        return self.voice

    def note_output(self, *a, **k): pass
    def reset(self): self.resets += 1
    def snapshot(self): return {}


async def test_guarded_barge_in_interrupts_and_hands_google_the_words_it_missed(rig):
    session = await up(rig, voice_barge_in="guarded")
    rig.service._guard = guard = StubGuard()
    session.push(m_audio(pcm(9, 16384, 3000)))
    assert await wait_for(lambda: rig.service._playback.active)
    guard.voice = True
    blocks = [pcm(40 + i) for i in range(6)]
    for b in blocks:
        rig.devices.mic.push(b)
    assert await wait_for(lambda: not rig.service._playback.active)
    assert await wait_for(lambda: len(session.audio) == 6)
    assert session.audio == blocks                              # the pre-roll: onset preserved, in order
    rig.devices.mic.push(pcm(99))
    assert await wait_for(lambda: len(session.audio) == 7)      # and it keeps flowing afterwards


async def test_barge_in_is_ignored_when_the_guard_says_the_room_cannot_be_judged(rig):
    session = await up(rig, voice_barge_in="guarded")
    guard = rig.service._guard = StubGuard()
    guard.reliable = False
    guard.voice = True
    session.push(m_audio(pcm(9, 16384, 3000)))
    assert await wait_for(lambda: rig.service._playback.active)
    for i in range(12):
        rig.devices.mic.push(pcm(60 + i))
    await asyncio.sleep(0.15)
    assert rig.service._playback.active and session.audio == []
    assert rig.service.status()["barge_in_active"] is False


async def test_barge_in_off_never_interrupts_even_if_the_guard_hears_a_voice(rig):
    session = await up(rig)             # default: off
    guard = rig.service._guard = StubGuard()
    guard.voice = True
    session.push(m_audio(pcm(9, 16384, 3000)))
    assert await wait_for(lambda: rig.service._playback.active)
    for i in range(12):
        rig.devices.mic.push(pcm(70 + i))
    await asyncio.sleep(0.15)
    assert rig.service._playback.active and session.audio == []


# ── the tail after a reply: echo dropped, a person answering is not ─────────

class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


async def _reply_then_tail(rig, monkeypatch, user_in_tail: bool):
    """Play a 4 s reply against a simulated desk room, then feed the microphone through the tail.
    Returns (session, tail_end, offer_times) where offer_times are the clock times blocks were streamed."""
    clock = Clock()
    monkeypatch.setattr(audio_module, "now", clock)
    rig.service._now = clock
    session = await up(rig)
    offers = []
    real_offer = rig.service._runner.offer_audio
    rig.service._runner.offer_audio = lambda b: (offers.append(clock.t), real_offer(b))

    reply_seconds = 4.0
    out48 = speech_like(7.0, 5)
    out48[int(reply_seconds * SR_SIM):] = 0.0            # the reply ends; only its echo trails on
    echo48 = room_echo(out48, ROOMS["desk"])
    echo48 = echo48 + ROOMS["desk"]["noise"] * np.random.default_rng(3).standard_normal(len(echo48))
    out24 = (_resample(out48, SR_SIM, SR_OUT) * 12000).astype(np.int16)
    echo16 = (_resample(echo48, SR_SIM, SR_IN) * 12000).astype(np.int16)
    user48 = speech_like(7.0, 11, f0=190.0)
    user48 = user48 / np.sqrt(np.mean(user48 ** 2)) * np.sqrt(np.mean(echo48 ** 2)) * 1.8
    user16 = (_resample(user48, SR_SIM, SR_IN) * 12000).astype(np.int16)

    session.push(m_audio(out24[: int(reply_seconds * SR_OUT)].tobytes()), m_turn_complete())
    assert await wait_for(lambda: rig.service._playback.active)
    step = 1024 / SR_IN                        # one microphone block = 64 ms
    per_step = int(step * SR_OUT)              # speaker frames in the same time
    mic_i = 0
    while rig.service._playback.active:        # the reply plays; its echo is heard but never streamed
        clock.t += step
        rig.devices.speaker.pump(per_step)
        await asyncio.sleep(0)
        rig.devices.mic.push(echo16[mic_i:mic_i + 1024].tobytes()); mic_i += 1024
        await asyncio.sleep(0)
    await asyncio.sleep(0.02)
    assert session.audio == [] and offers == []
    assert rig.service._guard.calibrated                  # it learned this room while STONIC talked
    tail_end = rig.service._tail_until
    j = 0
    while clock.t < tail_end + 3 * step:
        clock.t += step
        block = echo16[mic_i:mic_i + 1024].astype(np.int32)
        if user_in_tail:
            block = block + user16[j * 1024:(j + 1) * 1024]
        rig.devices.mic.push(block.clip(-32768, 32767).astype(np.int16).tobytes()); mic_i += 1024; j += 1
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)
    return session, tail_end, offers


async def test_after_a_reply_our_own_echo_is_dropped_not_sent_back_to_the_model(rig, monkeypatch):
    session, tail_end, offers = await _reply_then_tail(rig, monkeypatch, user_in_tail=False)
    inside = [t for t in offers if t < tail_end]
    assert inside == [], "our own echo was streamed back to the model during the tail"


async def test_a_person_who_answers_instantly_is_heard_inside_the_tail(rig, monkeypatch):
    session, tail_end, offers = await _reply_then_tail(rig, monkeypatch, user_in_tail=True)
    inside = [t for t in offers if t < tail_end]
    assert inside, "a person answering right after STONIC was deafened out by the echo tail"
    assert len(session.audio) >= 3


# ── STONIC is the brain ─────────────────────────────────────────────────────

async def test_a_spoken_request_goes_through_the_normal_chat_pipeline_and_is_stored_once(rig):
    session = await up(rig)
    session.push(m_user_text("what is my cpu"), m_model_text("One moment."),
                 m_tool_call("c1", {"request": "What is my CPU usage?"}))
    assert await wait_for(lambda: session.tool_responses)
    assert session.tool_responses[0]["response"] == {"ok": True, "reply": "CPU is at twelve percent.", "approval_required": False}
    session.push(m_model_text("CPU is at twelve percent."), m_turn_complete())
    await asyncio.sleep(0.1)
    history = [(m["role"], m["content"]) for m in rig.core.history("main")]
    assert history == [("user", "What is my CPU usage?"), ("assistant", "CPU is at twelve percent.")]
    assert rig.provider.calls and "CPU" in rig.provider.calls[0]


async def test_small_talk_is_stored_like_typed_chat_and_shown_to_the_ui(rig):
    session = await up(rig)
    queue = rig.service.subscribe()
    session.push(m_user_text("good evening"), m_model_text("Good evening."), m_turn_complete())
    assert await wait_for(lambda: len(rig.core.history("main")) == 2)
    assert [(m["role"], m["content"]) for m in rig.core.history("main")] == [("user", "good evening"), ("assistant", "Good evening.")]
    seen = []
    while not queue.empty():
        seen.append(queue.get_nowait())
    assert {"type": "transcript", "role": "user", "text": "good evening"} in seen


async def test_a_sensitive_spoken_request_cannot_bypass_approval(rig):
    from stonic.tools.workspace import FilePath

    class Planner(Provider):
        calls_n = 0

        async def decide(self, settings, messages, tools, context):
            Planner.calls_n += 1
            if Planner.calls_n == 1:
                return Decision(kind="plan", message="Inspect", steps=[{"id": "read", "title": "Inspect file", "tool": "files.read",
                                "arguments_json": json.dumps({"path": "note.txt"}), "depends_on": []}])
            observed = rig.core.workspace.read(FilePath(path="note.txt")).data
            return Decision(kind="plan", message="Edit", steps=[{"id": "edit", "title": "Correct file", "tool": "files.write",
                            "arguments_json": json.dumps({"path": "note.txt", "expected_sha256": observed["sha256"], "content": "after"}),
                            "depends_on": []}])
    rig.core.provider = Planner()
    target = rig.core.workspace.root / "note.txt"
    target.write_text("before")
    result = await rig.service.run_request("Change note.txt to after.")
    assert result["ok"] is True and result["approval_required"] is True
    assert target.read_text() == "before"          # spoken words did not approve anything
    target.unlink()


async def test_a_request_while_stonic_is_busy_is_refused_honestly(rig):
    await rig.core.lock.acquire()
    try:
        result = await rig.service.run_request("anything")
    finally:
        rig.core.lock.release()
    assert result["ok"] is False and "busy" in result["error"]
    assert (await rig.service.run_request("   "))["ok"] is False


async def test_a_slow_request_is_stopped_and_reported(rig, monkeypatch):
    import stonic.voicelive.service as service_module
    monkeypatch.setattr(service_module, "REQUEST_TIMEOUT_S", 0.2)

    async def slow(settings, messages):
        await asyncio.sleep(30)
    rig.provider.complete = slow
    result = await rig.service.run_request("think forever")
    assert result["ok"] is False and "too long" in result["error"]
    assert not rig.core.lock.locked()


async def test_the_server_cancelling_a_call_also_stops_the_running_generation(rig):
    session = await up(rig)
    started = asyncio.Event()

    async def slow(settings, messages):
        started.set()
        await asyncio.sleep(30)
    rig.provider.complete = slow
    session.push(m_tool_call("c1", {"request": "long thing"}))
    await asyncio.wait_for(started.wait(), 2)
    from voicelive_fakes import m_cancel
    session.push(m_cancel("c1"))
    assert await wait_for(lambda: not rig.core.lock.locked())
    assert session.tool_responses == []


# ── status, health, secrets, idle ───────────────────────────────────────────

async def test_health_is_absent_until_the_user_engages_and_then_honest(rig, monkeypatch):
    rig.config.update({"voice_cloud_consent": False})
    monkeypatch.delenv("GEMINI_API_KEY")
    assert rig.service.health() is None                    # a text-only install reports exactly what it always did
    rig.config.update({"voice_cloud_consent": True})
    assert rig.service.health().status == "unconfigured" and "Gemini" in rig.service.health().detail
    monkeypatch.setenv("GEMINI_API_KEY", GEMINI_KEY)
    assert rig.service.health().status == "ready"
    await up(rig)
    assert rig.service.health().status == "ready" and "listening" in rig.service.health().detail
    rig.service.fatal = "Google rejected the API key."
    assert rig.service.health().status == "failed"


async def test_a_refused_key_stops_voice_and_leaves_a_clear_error(rig):
    rig.connector.failures = [Exception("API key not valid. Please pass a valid API key.")]
    await rig.service.start()
    assert await wait_for(lambda: rig.service.state().value == "error", 3)
    assert not rig.service.running and "rejected the API key" in rig.service.status()["detail"]
    assert rig.service.health().status == "failed"
    assert rig.devices.mic.closed                          # and the microphone is released


async def test_the_gemini_key_is_stored_encrypted_under_its_own_endpoint(rig, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setattr(SecretStore, "_crypt", staticmethod(lambda raw, decrypt=False: raw[::-1]))   # stand-in for DPAPI off Windows
    rig.service.save_key("AIzaSy-test-key-abcdefghij")
    assert rig.service.api_key() == "AIzaSy-test-key-abcdefghij"
    assert b"AIzaSy" not in (rig.tmp / "credentials.dpapi").read_bytes()      # not plaintext on disk
    assert rig.credentials.configured("https://api.xkiro.com/v1") is True     # the provider key is still its own
    assert rig.credentials.key("https://api.xkiro.com/v1") == "xkiro-secret-value"
    rig.service.delete_key()
    assert rig.service.api_key() == ""


async def test_idle_sleep_stops_voice_and_releases_the_microphone(rig):
    await up(rig, voice_idle_sleep_minutes=1)
    rig.service._last_activity -= 120
    assert await wait_for(lambda: not rig.service.running, 4)
    assert rig.devices.mic.closed and "idle" in rig.service.status()["detail"]


async def test_speaking_keeps_voice_awake_past_the_idle_limit(rig):
    session = await up(rig, voice_idle_sleep_minutes=1)
    session.push(m_audio(pcm(9, 48000, 3000)))
    assert await wait_for(lambda: rig.service._playback.active)
    rig.service._last_activity -= 600
    await asyncio.sleep(1.3)
    assert rig.service.running


async def test_subscribers_get_state_first_and_slow_ones_never_block_the_service(rig):
    queue = rig.service.subscribe()
    assert queue.get_nowait()["type"] == "state"
    await up(rig)
    for i in range(500):
        rig.service._emit({"type": "level", "in": 0.1, "out": 0.0})
    assert queue.qsize() <= 64
    rig.service.unsubscribe(queue)
    rig.service._emit({"type": "level"})


async def test_level_events_report_the_microphone_and_speaker(rig):
    session = await up(rig)
    queue = rig.service.subscribe()
    rig.devices.mic.push((np.sin(2 * np.pi * 300 * np.arange(1024) / 16000) * 9000).astype(np.int16).tobytes())
    levels = []

    async def collect():
        while len(levels) < 1:
            event = await queue.get()
            if event["type"] == "level":
                levels.append(event)
    await asyncio.wait_for(collect(), 2)
    assert levels[0]["in"] > 0.5


async def test_a_saved_but_missing_device_falls_back_to_the_default_and_says_so(rig, monkeypatch):
    opened = []

    def factory(device):
        opened.append(device)
        if device == 7:
            raise OSError("in use")
        return rig.devices.mic_factory(device)
    monkeypatch.setattr(audio_module, "resolve_device", lambda name, kind: 7 if name else None)
    rig.service._mic_factory = factory
    await up(rig, voice_input_device="USB Headset")
    assert opened == [7, None] and rig.service._mic.fell_back
    assert rig.service.status()["input_device"] == "system default"


async def test_pressing_stop_while_a_request_runs_cancels_it_and_answers_the_model(rig):
    session = await up(rig)
    started = asyncio.Event()

    async def slow(settings, messages):
        started.set()
        await asyncio.sleep(30)
    rig.provider.complete = slow
    session.push(m_tool_call("c1", {"request": "long thing"}))
    await asyncio.wait_for(started.wait(), 2)
    rig.service.interrupt()
    assert await wait_for(lambda: session.tool_responses and not rig.core.lock.locked())
    assert session.tool_responses[0]["response"]["ok"] is False
