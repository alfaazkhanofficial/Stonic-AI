"""The Live session runner against a scripted fake Google session."""
import asyncio

import pytest

from stonic.config.settings import Settings
from stonic.voicelive import live as live_module
from stonic.voicelive.live import AuthError, LiveRunner, build_config
from voicelive_fakes import (FakeConnector, m_audio, m_cancel, m_goaway, m_handle, m_interrupted, m_model_text,
                             m_tool_call, m_turn_complete, m_user_text, wait_for)


class Host:
    def __init__(self, request_handler=None):
        self.events = []
        self.audio = []
        self.exchanges = []
        self.requests = []
        self.fatal = None
        self.cancelled_requests = 0
        self.tools_pending = []
        self._handler = request_handler
        self.s = Settings()
        self.key = "test-key"

    def live_settings(self): return self.s
    def api_key(self): return self.key
    def system_prompt(self): return "prompt"
    def on_connecting(self): self.events.append("connecting")
    def on_connected(self, resumed): self.events.append(("connected", resumed))
    def on_disconnected(self, reason, retrying): self.events.append(("disconnected", reason))
    def on_fatal(self, reason): self.fatal = reason
    def log(self, level, message): self.events.append(("log", level, message))
    def on_audio(self, pcm): self.audio.append(pcm)
    def on_server_interrupted(self): self.events.append("interrupted")
    def on_turn_complete(self): self.events.append("turn_complete")
    def on_exchange(self, user, model, used_tool): self.exchanges.append((user, model, used_tool))
    def on_tools_changed(self, n): self.tools_pending.append(n)
    def cancel_running_request(self): self.cancelled_requests += 1

    async def run_request(self, request):
        self.requests.append(request)
        if self._handler:
            return await self._handler(request)
        return {"ok": True, "reply": "done", "approval_required": False}


@pytest.fixture
def sleeps():
    return []


def make(host=None, connector=None, sleeps=None):
    host = host or Host()
    connector = connector or FakeConnector()
    calls = sleeps if sleeps is not None else []

    async def fake_sleep(seconds):
        calls.append(seconds)
        await asyncio.sleep(0)
    return host, connector, LiveRunner(host, connector, sleep=fake_sleep)


async def start(runner):
    return asyncio.create_task(runner.run())


async def stop(task):
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def test_setup_message_carries_model_tool_transcription_and_resumption():
    host, connector, runner = make()
    task = await start(runner)
    await asyncio.wait_for(connector.connected.wait(), 2)
    config = connector.configs[0]
    assert connector.keys == ["test-key"] and connector.models == ["gemini-3.8-live"]
    assert config["response_modalities"] == ["AUDIO"]
    assert config["input_audio_transcription"] == {} and config["output_audio_transcription"] == {}
    fn = config["tools"][0]["function_declarations"][0]
    assert fn["name"] == "ask_stonic" and fn["behavior"] == "BLOCKING" and fn["parameters"]["required"] == ["request"]
    assert config["realtime_input_config"]["automatic_activity_detection"]["silence_duration_ms"] == 650
    assert config["session_resumption"] == {"handle": None} and "sliding_window" in config["context_window_compression"]
    assert config["speech_config"]["voice_config"]["prebuilt_voice_config"]["voice_name"] == "Charon"
    await stop(task)


def test_the_setup_message_is_valid_for_the_real_sdk():
    from google.genai import types
    for tier in (0, 1, 2):
        types.LiveConnectConfig.model_validate(build_config(Settings(), "p", "handle-1", tier))


async def test_microphone_audio_reaches_the_server_in_order_and_end_of_stream_is_signalled():
    host, connector, runner = make()
    task = await start(runner)
    await asyncio.wait_for(connector.connected.wait(), 2)
    for chunk in (b"\x01\x00" * 4, b"\x02\x00" * 4, b"\x03\x00" * 4):
        runner.offer_audio(chunk)
    runner.end_audio()
    session = connector.session
    assert await wait_for(lambda: len(session.audio) == 3 and session.stream_ends == 1)
    assert session.audio[0][:2] == b"\x01\x00" and session.audio[2][:2] == b"\x03\x00"
    await stop(task)


async def test_stalled_network_drops_old_audio_not_new():
    host, connector, runner = make()
    for i in range(live_module.QUEUE_MAX + 10):
        runner.offer_audio(bytes([i % 250]) * 4)
    assert runner._send_q.qsize() == live_module.QUEUE_MAX
    assert runner._send_q.get_nowait() == bytes([10]) * 4   # the ten oldest are gone


async def test_reply_audio_and_interruption_are_forwarded():
    host, connector, runner = make()
    task = await start(runner)
    await asyncio.wait_for(connector.connected.wait(), 2)
    connector.session.push(m_audio(b"\x05\x00" * 8), m_audio(b"\x06\x00" * 8), m_interrupted(), m_turn_complete())
    assert await wait_for(lambda: "turn_complete" in host.events)
    assert host.audio == [b"\x05\x00" * 8, b"\x06\x00" * 8]
    assert host.events.index("interrupted") < host.events.index("turn_complete")
    await stop(task)


async def test_casual_turns_are_reported_as_exchanges_without_a_tool():
    host, connector, runner = make()
    task = await start(runner)
    await asyncio.wait_for(connector.connected.wait(), 2)
    connector.session.push(m_user_text("hello "), m_user_text("there"), m_model_text("Good evening."), m_turn_complete())
    assert await wait_for(lambda: host.exchanges)
    assert host.exchanges == [("hello there", "Good evening.", False)]
    await stop(task)


async def test_tool_call_runs_the_request_returns_the_answer_and_marks_the_exchange_as_used_tool():
    host, connector, runner = make()
    task = await start(runner)
    await asyncio.wait_for(connector.connected.wait(), 2)
    session = connector.session
    session.push(m_user_text("what is my cpu"), m_model_text("One moment."),
                 m_tool_call("c1", {"request": "what is my cpu usage"}))
    assert await wait_for(lambda: session.tool_responses)
    assert host.requests == ["what is my cpu usage"]
    assert session.tool_responses[0] == {"id": "c1", "name": "ask_stonic",
                                          "response": {"ok": True, "reply": "done", "approval_required": False}}
    session.push(m_model_text("CPU is at twelve percent."), m_turn_complete())
    assert await wait_for(lambda: host.exchanges)
    assert host.exchanges[0][2] is True     # chat() already stored it; the service must not store it twice
    assert host.tools_pending[0] == 1 and host.tools_pending[-1] == 0
    await stop(task)


async def test_a_turn_complete_while_a_request_is_running_does_not_end_the_exchange():
    gate = asyncio.Event()

    async def slow(request):
        await gate.wait()
        return {"ok": True, "reply": "late", "approval_required": False}
    host, connector, runner = make(Host(slow))
    task = await start(runner)
    await asyncio.wait_for(connector.connected.wait(), 2)
    session = connector.session
    session.push(m_user_text("do it"), m_tool_call("c1", {"request": "do it"}), m_turn_complete())
    await asyncio.sleep(0.05)
    assert host.exchanges == []
    gate.set()
    assert await wait_for(lambda: session.tool_responses)
    await stop(task)


async def test_server_cancelling_a_call_cancels_the_work_and_sends_no_answer():
    started = asyncio.Event()

    async def slow(request):
        started.set()
        await asyncio.sleep(30)
    host, connector, runner = make(Host(slow))
    task = await start(runner)
    await asyncio.wait_for(connector.connected.wait(), 2)
    session = connector.session
    session.push(m_tool_call("c1", {"request": "long job"}))
    await asyncio.wait_for(started.wait(), 2)
    session.push(m_cancel("c1"))
    assert await wait_for(lambda: runner.pending_tools == 0)
    await asyncio.sleep(0.05)
    assert session.tool_responses == [] and host.cancelled_requests == 1
    await stop(task)


async def test_unknown_tools_and_crashing_requests_get_an_honest_failure_not_silence():
    async def boom(request):
        raise RuntimeError("secret internals")
    host, connector, runner = make(Host(boom))
    task = await start(runner)
    await asyncio.wait_for(connector.connected.wait(), 2)
    session = connector.session
    session.push(m_tool_call("a", {}, name="rm_rf"), m_tool_call("b", {"request": "x"}))
    assert await wait_for(lambda: len(session.tool_responses) == 2)
    by_id = {r["id"]: r["response"] for r in session.tool_responses}
    assert by_id["a"]["ok"] is False and "Unknown" in by_id["a"]["error"]
    assert by_id["b"]["ok"] is False and "secret" not in str(by_id["b"])
    await stop(task)


async def test_reconnect_resumes_with_the_handle_and_backs_off(sleeps):
    host, connector, runner = make(sleeps=sleeps)
    task = await start(runner)
    await asyncio.wait_for(connector.connected.wait(), 2)
    connector.session.push(m_handle("h-1"))
    await asyncio.sleep(0.05)
    connector.session.close_from_server(ConnectionResetError("network dropped"))
    assert await wait_for(lambda: len(connector.sessions) == 2)
    assert connector.configs[1]["session_resumption"] == {"handle": "h-1"}
    assert sleeps and sleeps[0] == live_module.INITIAL_BACKOFF
    assert ("connected", True) in host.events
    await stop(task)


async def test_non_resumable_handles_are_not_kept():
    host, connector, runner = make()
    task = await start(runner)
    await asyncio.wait_for(connector.connected.wait(), 2)
    connector.session.push(m_handle("h-x", resumable=False))
    await asyncio.sleep(0.05)
    assert runner._handle is None
    await stop(task)


async def test_backoff_doubles_up_to_a_ceiling_and_resets_after_a_healthy_session(sleeps):
    errors = [ConnectionResetError("x") for _ in range(6)]
    host, connector, runner = make(connector=FakeConnector(failures=errors), sleeps=sleeps)
    task = await start(runner)
    assert await wait_for(lambda: len(connector.sessions) == 1, 3)
    assert sleeps[:6] == [3.0, 6.0, 12.0, 24.0, 48.0, 60.0]
    await stop(task)


async def test_a_rejected_setup_drops_optional_fields_one_tier_at_a_time(sleeps):
    connector = FakeConnector(failures=[Exception("1007 Request contains an invalid argument"),
                                        Exception("1007 Request contains an invalid argument")])
    host, connector, runner = make(connector=connector, sleeps=sleeps)
    task = await start(runner)
    assert await wait_for(lambda: len(connector.sessions) == 1, 3)
    first, second, third = connector.configs
    assert "realtime_input_config" in first and first["tools"][0]["function_declarations"][0]["behavior"] == "BLOCKING"
    assert "realtime_input_config" not in second and "behavior" in second["tools"][0]["function_declarations"][0]
    assert "realtime_input_config" not in third and "behavior" not in third["tools"][0]["function_declarations"][0]
    assert sleeps == []      # tiering is immediate, it is not a network failure
    await stop(task)


async def test_when_the_model_defaults_to_async_the_answer_says_when_to_speak():
    connector = FakeConnector(failures=[Exception("invalid argument"), Exception("invalid argument")])
    host, connector, runner = make(connector=connector)
    task = await start(runner)
    assert await wait_for(lambda: len(connector.sessions) == 1, 3)
    connector.session.push(m_tool_call("c1", {"request": "x"}))
    assert await wait_for(lambda: connector.session.tool_responses)
    assert connector.session.tool_responses[0]["response"]["scheduling"] == "WHEN_IDLE"
    await stop(task)


async def test_a_resumed_session_that_dies_at_once_starts_fresh_next_time(sleeps):
    host, connector, runner = make(connector=FakeConnector(failures=[]), sleeps=sleeps)
    runner._handle = "poisoned"
    connector.failures = [Exception("1007 invalid argument")]
    task = await start(runner)
    assert await wait_for(lambda: len(connector.sessions) == 1, 3)
    assert connector.configs[0]["session_resumption"] == {"handle": "poisoned"}
    assert connector.configs[1]["session_resumption"] == {"handle": None}
    await stop(task)


async def test_a_refused_key_stops_retrying_and_says_so():
    connector = FakeConnector(failures=[Exception("API key not valid. Please pass a valid API key.")])
    host, connector, runner = make(connector=connector)
    await asyncio.wait_for(runner.run(), 2)      # returns instead of looping
    assert "rejected the API key" in host.fatal
    assert connector.sessions == []


async def test_quota_exhaustion_waits_longer_than_an_ordinary_drop(sleeps):
    connector = FakeConnector(failures=[Exception("429 RESOURCE_EXHAUSTED quota")])
    host, connector, runner = make(connector=connector, sleeps=sleeps)
    task = await start(runner)
    assert await wait_for(lambda: len(connector.sessions) == 1, 3)
    assert sleeps[0] >= live_module.QUOTA_BACKOFF
    assert any(e[0] == "disconnected" and "quota" in e[1].lower() for e in host.events if isinstance(e, tuple))
    await stop(task)


async def test_no_key_means_no_connection_attempt():
    host = Host()
    host.key = ""
    connector = FakeConnector()
    runner = LiveRunner(host, connector)
    await asyncio.wait_for(runner.run(), 2)
    assert connector.keys == [] and host.fatal


async def test_goaway_renews_the_connection_after_the_current_turn(sleeps):
    host, connector, runner = make(sleeps=sleeps)
    task = await start(runner)
    await asyncio.wait_for(connector.connected.wait(), 2)
    connector.session.push(m_handle("h-2"), m_goaway(), m_audio(b"\x01\x00" * 4), m_turn_complete())
    assert await wait_for(lambda: len(connector.sessions) == 2)
    assert connector.configs[1]["session_resumption"] == {"handle": "h-2"}
    assert host.audio == [b"\x01\x00" * 4]      # the reply in flight was not cut off
    await stop(task)


async def test_a_socket_that_closes_quietly_does_not_spin_the_loop(sleeps, monkeypatch):
    monkeypatch.setattr(live_module, "EMPTY_RECEIVES_BEFORE_DROP", 5)
    host, connector, runner = make(sleeps=sleeps)
    task = await start(runner)
    await asyncio.wait_for(connector.connected.wait(), 2)
    connector.session.close_from_server()
    assert await wait_for(lambda: len(connector.sessions) == 2, 3)
    assert any(e[0] == "disconnected" for e in host.events if isinstance(e, tuple))
    await stop(task)


def test_classification():
    from stonic.voicelive.live import QuotaError, SetupRejected, classify
    assert isinstance(classify(Exception("PERMISSION_DENIED"), True), AuthError)
    assert isinstance(classify(Exception("HTTP 429"), True), QuotaError)
    assert isinstance(classify(Exception("received 1007 (invalid frame payload data)"), True), SetupRejected)
    other = ConnectionResetError("reset")
    assert classify(other, True) is other


async def test_a_user_cancel_still_tells_the_model_so_it_is_not_left_waiting():
    started = asyncio.Event()

    async def slow(request):
        started.set()
        await asyncio.sleep(30)
    host, connector, runner = make(Host(slow))
    task = await start(runner)
    await asyncio.wait_for(connector.connected.wait(), 2)
    session = connector.session
    session.push(m_tool_call("c1", {"request": "long job"}))
    await asyncio.wait_for(started.wait(), 2)
    runner.cancel_tools(answer=True)
    assert await wait_for(lambda: session.tool_responses)
    assert session.tool_responses[0]["response"] == {"ok": False, "error": "The user cancelled this request."}
    await stop(task)


async def test_confirm_tool_is_not_declared_when_voice_can_confirm_is_off():
    host, connector, runner = make()
    task = await start(runner)
    await asyncio.wait_for(connector.connected.wait(), 2)
    names = {fn["name"] for fn in connector.configs[0]["tools"][0]["function_declarations"]}
    assert names == {"ask_stonic"}
    await stop(task)


async def test_confirm_tool_is_declared_and_dispatches_when_voice_can_confirm_is_on():
    class ConfirmHost(Host):
        def __init__(self):
            super().__init__()
            self.s = Settings(voice_can_confirm=True)
            self.confirmations = []

        async def run_confirmation(self, approved):
            self.confirmations.append(approved)
            return {"ok": True, "reply": "Cancelled." if not approved else "Done.", "approval_required": False}

    host, connector, runner = make(host=ConfirmHost())
    task = await start(runner)
    await asyncio.wait_for(connector.connected.wait(), 2)
    declarations = connector.configs[0]["tools"][0]["function_declarations"]
    names = {fn["name"] for fn in declarations}
    assert names == {"ask_stonic", "confirm_pending_action"}
    confirm_fn = next(fn for fn in declarations if fn["name"] == "confirm_pending_action")
    assert confirm_fn["parameters"]["required"] == ["approved"] and confirm_fn["behavior"] == "BLOCKING"
    session = connector.session
    session.push(m_tool_call("c1", {"approved": True}, name="confirm_pending_action"))
    assert await wait_for(lambda: session.tool_responses)
    assert host.confirmations == [True]
    assert session.tool_responses[0] == {"id": "c1", "name": "confirm_pending_action", "response": {"ok": True, "reply": "Done.", "approval_required": False}}
    await stop(task)


async def test_unknown_tool_name_is_reported_without_crashing_the_session():
    host, connector, runner = make()
    task = await start(runner)
    await asyncio.wait_for(connector.connected.wait(), 2)
    session = connector.session
    session.push(m_tool_call("c1", {}, name="something_else"))
    assert await wait_for(lambda: session.tool_responses)
    assert session.tool_responses[0]["response"]["ok"] is False
    await stop(task)
