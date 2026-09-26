"""End-to-end: CoreService.chat routes through the real V3 agent loop when it is enabled and usable, and
falls back to the existing regex/plan path otherwise. Uses a scripted HTTP transport, never the network.
"""
import json
import tempfile
from pathlib import Path

import httpx
import pytest

from stonic.config.settings import Configuration
from stonic.core.models import Activity, ChatInput
from stonic.core.service import CoreService
from stonic.diagnostics.health import Diagnostics
from stonic.events.bus import EventBus
from stonic.providers.llm import OpenAICompatibleProvider
from stonic.storage.database import Database


def scripted_action_response(name, arguments, content=None):
    call = {"id": "c1", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}
    return {"choices": [{"finish_reason": "tool_calls", "message": {"content": content, "tool_calls": [call]}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


def scripted_answer(text):
    return {"choices": [{"finish_reason": "stop", "message": {"content": text}}], "usage": {"prompt_tokens": 5, "completion_tokens": 5}}


def build_core(tmp_path, turns, *, agent_enabled=True, autonomy="autonomous"):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        turn = turns[min(calls["n"], len(turns) - 1)]
        calls["n"] += 1
        return httpx.Response(200, json=turn)

    provider = OpenAICompatibleProvider()
    provider.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider.available = lambda _s: False   # main (xKiro) is not configured; only the agent's own endpoint is
    db = Database(Path(tmp_path) / "s.db")
    events = EventBus(db)
    config = Configuration(db)
    config.update({"agent_enabled": agent_enabled, "agent_autonomy": autonomy, "agent_fast_consent": True,
                   "agent_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                   "agent_fast_model": "gemini-3.5-flash-lite"})
    core = CoreService(db, config, Diagnostics(Path(tmp_path)), events, provider)
    core.agent_router._agent_key = lambda _s: "test-key"
    core.state.transition(Activity.IDLE)
    return core, db, calls


@pytest.mark.asyncio
async def test_chat_runs_a_real_tool_through_the_agent_loop(tmp_path):
    core, db, calls = build_core(tmp_path, [
        scripted_action_response("system__status", {}),
        scripted_answer("Your system looks healthy.")])
    message = await core.chat(ChatInput(content="check system health for me", session_id="s1"))
    assert message["content"] == "Your system looks healthy."
    assert core.agent_store.list_goals("s1")[0]["status"] == "completed"
    await provider_close(core); db.close()


@pytest.mark.asyncio
async def test_chat_reports_waiting_approval_and_api_style_decision_completes_it(tmp_path):
    core, db, calls = build_core(tmp_path, [
        scripted_action_response("files__write", {"path": "note.txt", "content": "hi"}),
        scripted_answer("Saved note.txt.")], autonomy="ask_on_risk")
    message = await core.chat(ChatInput(content="write hi to note.txt", session_id="s1"))
    assert "approve or decline" in message["content"] or "STONIC wants to" in message["content"]
    goal_id = core.agent_sessions["s1"]
    resumed = core.agent_loop.resume(goal_id)
    result = await core.agent_loop.run(resumed, core.config.values, approve_all=True)
    assert result["status"] == "completed"
    await provider_close(core); db.close()


@pytest.mark.asyncio
async def test_agent_disabled_falls_back_to_existing_path(tmp_path):
    core, db, calls = build_core(tmp_path, [scripted_answer("unused")], agent_enabled=False)
    message = await core.chat(ChatInput(content="hello there", session_id="s1"))
    assert calls["n"] == 0        # the agent endpoint was never called
    assert "Connect an intelligence provider" in message["content"] or message["content"]
    await provider_close(core); db.close()


async def provider_close(core):
    await core.provider.close()


@pytest.mark.asyncio
async def test_compound_full_system_request_completes_with_one_combined_confirmation(tmp_path):
    """The V3.0 flagship example: one sentence, one confirmation, three real full-system actions."""
    desktop = Path(tmp_path) / "Desktop"
    jarvis = Path(tmp_path) / "Jarvis"; jarvis.mkdir(); (jarvis / "old.txt").write_text("x")
    turns = [scripted_action_response("system__create_folder", {"path": str(desktop / "Altrex")}, content=None)]
    # three tool calls in one assistant turn, then a final answer
    combined = {"choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "system__create_folder", "arguments": json.dumps({"path": str(desktop / "Altrex")})}},
        {"id": "c2", "type": "function", "function": {"name": "system__delete_path", "arguments": json.dumps({"path": str(jarvis)})}},
        {"id": "c3", "type": "function", "function": {"name": "system__uninstall_app", "arguments": json.dumps({"name": "the x app"})}}]}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10}}
    core, db, calls = build_core(tmp_path, [combined, scripted_answer("Made Altrex, deleted Jarvis, uninstalled X.")], autonomy="ask_on_risk")
    core.system_control._winget_list = lambda: [{"name": "X App", "id": "Vendor.X"}]
    core.system_control._restore_point = lambda desc: None
    core.system_control._winget_uninstall = lambda app_id: __import__("subprocess").CompletedProcess(["winget"], 0, "", "")
    message = await core.chat(ChatInput(content="Make a folder named Altrex on my desktop, delete the Jarvis folder, and uninstall the x app.", session_id="s1"))
    goal_id = core.agent_sessions["s1"]
    pending_row = core.agent_store.load_goal(goal_id)
    assert pending_row["status"] == "waiting_approval"
    resumed = core.agent_loop.resume(goal_id)
    confirm = core.agent_loop.describe_pending(resumed, core.config.values)
    assert len(confirm) == 2 and {c["tool"] for c in confirm} == {"system.delete_path", "system.uninstall_app"}
    result = await core.agent_loop.run(resumed, core.config.values, approve_all=True)
    assert result["status"] == "completed"
    assert (desktop / "Altrex").is_dir()
    assert not jarvis.exists()
    assert {s["tool"] for s in result["steps"]} == {"system.create_folder", "system.delete_path", "system.uninstall_app"}
    await provider_close(core); db.close()



@pytest.mark.asyncio
async def test_voice_run_confirmation_bridges_to_the_real_agent_loop(tmp_path):
    from stonic.security.secrets import SecretStore
    from stonic.voicelive import VoiceService

    core, db, calls = build_core(tmp_path, [
        scripted_action_response("files__write", {"path": "note.txt", "content": "hi"}),
        scripted_answer("Saved note.txt.")], autonomy="ask_on_risk")
    service = VoiceService(core, SecretStore(Path(tmp_path)))
    service.session_id = "s1"
    message = await core.chat(ChatInput(content="write hi to note.txt", session_id="s1"))
    assert "STONIC wants to" in message["content"]
    result = await service.run_confirmation(True)
    assert result["ok"] is True and "Saved note.txt" in result["reply"]
    await provider_close(core); db.close()


@pytest.mark.asyncio
async def test_voice_run_confirmation_denial_cancels_the_goal(tmp_path):
    from stonic.security.secrets import SecretStore
    from stonic.voicelive import VoiceService

    core, db, calls = build_core(tmp_path, [scripted_action_response("files__write", {"path": "note.txt", "content": "hi"})], autonomy="ask_on_risk")
    service = VoiceService(core, SecretStore(Path(tmp_path)))
    service.session_id = "s1"
    await core.chat(ChatInput(content="write hi to note.txt", session_id="s1"))
    result = await service.run_confirmation(False)
    assert result["ok"] is True and "Cancelled" in result["reply"]
    goal_id = core.agent_sessions["s1"]
    assert core.agent_store.load_goal(goal_id)["status"] == "failed"
    await provider_close(core); db.close()


@pytest.mark.asyncio
async def test_voice_run_confirmation_refuses_system_critical_targets(tmp_path):
    from stonic.security.secrets import SecretStore
    from stonic.voicelive import VoiceService

    core, db, calls = build_core(tmp_path, [scripted_action_response("system__delete_path", {"path": "C:\\Windows\\System32"})], autonomy="autonomous")
    service = VoiceService(core, SecretStore(Path(tmp_path)))
    service.session_id = "s1"
    await core.chat(ChatInput(content="delete a system folder", session_id="s1"))
    result = await service.run_confirmation(True)
    assert result["ok"] is False and "screen" in result["error"]
    await provider_close(core); db.close()


@pytest.mark.asyncio
async def test_voice_run_confirmation_with_nothing_pending(tmp_path):
    from stonic.security.secrets import SecretStore
    from stonic.voicelive import VoiceService

    core, db, calls = build_core(tmp_path, [scripted_answer("hi there")])
    service = VoiceService(core, SecretStore(Path(tmp_path)))
    service.session_id = "s1"
    result = await service.run_confirmation(True)
    assert result["ok"] is False
    await provider_close(core); db.close()
