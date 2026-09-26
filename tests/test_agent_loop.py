import tempfile
from pathlib import Path

import pytest

from stonic.agent.loop import AgentLoop, Budget, classify
from stonic.agent.memory import Memory
from stonic.agent.router import ModelRouter
from stonic.agent.store import AgentStore
from stonic.config.settings import Configuration, Settings
from stonic.core.models import ActionResult, Contract, PermissionLevel
from stonic.events.bus import EventBus
from stonic.security.permissions import PermissionGate
from stonic.storage.database import Database
from stonic.tools.registry import Tool, ToolRegistry


class ReadArgs(Contract):
    path: str = "a.txt"


class WriteArgs(Contract):
    path: str = "a.txt"
    content: str = "x"


class ScriptedProvider:
    """Stands in for ``OpenAICompatibleProvider``: returns pre-baked ``act()`` results in order."""

    def __init__(self, turns: list[dict]) -> None:
        self.turns, self.calls = list(turns), 0

    def available(self, _settings) -> bool:
        return True

    async def act(self, _settings, _messages, _tools, **_kw) -> dict:
        turn = self.turns[min(self.calls, len(self.turns) - 1)]
        self.calls += 1
        return {"usage": {"total_tokens": 40}, **turn}


def call(name, args, cid="c1"):
    return {"id": cid, "name": name, "arguments": args}


def assistant(calls):
    return {"content": "", "tool_calls": calls, "assistant_message": {"role": "assistant", "content": None, "tool_calls": calls}}


def answer(text):
    return {"content": text, "tool_calls": [], "assistant_message": {"role": "assistant", "content": text}}


def build(tmp_path, provider_turns, autonomy="ask_on_risk", results=None, run_ok=None):
    db = Database(Path(tmp_path) / "s.db")
    events = EventBus(db)
    permissions = PermissionGate()
    registry = ToolRegistry(permissions)
    outcomes = list(results or [])

    def read(_args):
        return ActionResult(success=True, status="completed", message="read ok", verification="observed content", verification_kind="observed")

    def write(_args):
        if outcomes:
            return outcomes.pop(0)
        return ActionResult(success=True, status="completed", message="written", verification="observed new content", verification_kind="observed")

    registry.register(Tool("files.read", "Read a file", ReadArgs, PermissionLevel.SAFE, read, retry_safe=True))
    registry.register(Tool("files.write", "Write a file", WriteArgs, PermissionLevel.SENSITIVE, write))
    provider = ScriptedProvider(provider_turns)
    router = ModelRouter(provider)
    router.main_available = lambda _s: True
    router.route = lambda settings, purpose="step", skip=frozenset(): (None if {"fast", "strong", "main"} <= skip else
                   __import__("stonic.agent.router", fromlist=["Route"]).Route("main", settings, None))
    memory = Memory(AgentStore(db))
    loop = AgentLoop(registry, router, AgentStore(db), memory, events)
    settings = Settings()
    return loop, settings, db


@pytest.mark.asyncio
async def test_safe_tool_runs_without_any_approval(tmp_path):
    loop, settings, db = build(tmp_path, [assistant([call("files.read", {"path": "a.txt"})]), answer("a.txt says hello.")])
    goal = loop.start("s1", "read a.txt", settings)
    result = await loop.run(goal, settings)
    assert result["status"] == "completed" and "hello" in result["message"]
    assert goal.steps[0]["tool"] == "files.read" and goal.steps[0]["status"] == "completed"
    db.close()


@pytest.mark.asyncio
async def test_sensitive_tool_pauses_for_one_combined_confirmation(tmp_path):
    loop, settings, db = build(tmp_path, [
        assistant([call("files.write", {"path": "a.txt", "content": "1"}, "c1"), call("files.write", {"path": "b.txt", "content": "2"}, "c2")]),
        answer("Both files written.")])
    goal = loop.start("s1", "write two files", settings)
    waiting = await loop.run(goal, settings)
    assert waiting["status"] == "waiting_approval"
    assert len(waiting["confirm"]) == 2 and all(c["risk"] == "delete-or-uninstall" for c in waiting["confirm"])
    result = await loop.run(goal, settings, approve_all=True)
    assert result["status"] == "completed"
    assert {s["tool"] for s in goal.steps} == {"files.write"}
    db.close()


@pytest.mark.asyncio
async def test_autonomous_mode_runs_sensitive_without_asking(tmp_path):
    loop, settings, db = build(tmp_path, [assistant([call("files.write", {"path": "a.txt", "content": "1"})]), answer("Written.")])
    goal = loop.start("s1", "write a.txt", settings)
    result = await loop.run(goal, settings.model_copy(update={"agent_autonomy": "autonomous"}))
    assert result["status"] == "completed" and goal.steps[0]["status"] == "completed"
    db.close()


@pytest.mark.asyncio
async def test_ask_every_step_confirms_even_safe_reads(tmp_path):
    loop, settings, db = build(tmp_path, [assistant([call("files.read", {"path": "a.txt"})]), answer("done")])
    goal = loop.start("s1", "read a.txt", settings)
    waiting = await loop.run(goal, settings.model_copy(update={"agent_autonomy": "ask_every_step"}))
    assert waiting["status"] == "waiting_approval" and waiting["confirm"][0]["tool"] == "files.read"
    db.close()


@pytest.mark.asyncio
async def test_protected_path_needs_confirmation_even_in_autonomous_mode(tmp_path):
    loop, settings, db = build(tmp_path, [assistant([call("files.write", {"path": "C:/Windows/system.ini", "content": "x"})]), answer("done")])
    goal = loop.start("s1", "edit a system file", settings)
    protected = settings.model_copy(update={"agent_autonomy": "autonomous", "agent_protected_paths": ["C:/Windows"]})
    waiting = await loop.run(goal, protected)
    assert waiting["status"] == "waiting_approval"
    db.close()


@pytest.mark.asyncio
async def test_step_budget_stops_cleanly_with_progress_report(tmp_path):
    loop, settings, db = build(tmp_path, [assistant([call("files.read", {"path": "a.txt"}, f"c{i}")]) for i in range(10)])
    goal = loop.start("s1", "keep reading", settings.model_copy(update={"agent_max_steps": 3}))
    result = await loop.run(goal, settings.model_copy(update={"agent_max_steps": 3}))
    assert result["status"] == "stopped" and "3-step limit" in result["message"]
    assert len(goal.steps) == 3
    db.close()


@pytest.mark.asyncio
async def test_reflection_retries_transient_failure_then_succeeds(tmp_path):
    transient = ActionResult(success=False, status="failed", message="Connection timed out, please retry.", retryable=True)
    loop, settings, db = build(tmp_path, [assistant([call("files.write", {"path": "a.txt", "content": "x"})]), answer("done")],
                                results=[transient])
    goal = loop.start("s1", "write a.txt", settings)
    result = await loop.run(goal, settings.model_copy(update={"agent_autonomy": "autonomous"}))
    assert result["status"] == "completed"
    assert [s["status"] for s in goal.steps] == ["completed"]     # only the final outcome is recorded per call
    db.close()


@pytest.mark.asyncio
async def test_reflection_does_not_retry_denied_or_bad_arguments(tmp_path):
    denied = ActionResult(success=False, status="denied", message="Explicit confirmation is required.")
    loop, settings, db = build(tmp_path, [assistant([call("files.write", {"path": "a.txt", "content": "x"})]), answer("blocked")],
                                results=[denied])
    goal = loop.start("s1", "write a.txt", settings)
    result = await loop.run(goal, settings.model_copy(update={"agent_autonomy": "autonomous"}))
    assert goal.steps[0]["status"] == "denied" and result["status"] == "completed"
    db.close()


@pytest.mark.asyncio
async def test_goal_checkpoints_and_resumes_at_exact_step(tmp_path):
    loop, settings, db = build(tmp_path, [
        assistant([call("files.write", {"path": "a.txt", "content": "1"})]),
        assistant([call("files.write", {"path": "b.txt", "content": "2"})]),
        answer("Both done.")])
    goal = loop.start("s1", "write two files, one per turn", settings)
    waiting = await loop.run(goal, settings)
    assert waiting["status"] == "waiting_approval"
    goal_id = goal.id
    resumed = loop.resume(goal_id)
    assert resumed is not None and resumed.pending_calls and resumed.text == "write two files, one per turn"
    result = await loop.run(resumed, settings, approve_all=True)
    assert result["status"] == "waiting_approval"          # second write also needs confirmation
    second = loop.resume(goal_id)
    final = await loop.run(second, settings, approve_all=True)
    assert final["status"] == "completed" and len(final["steps"]) == 2
    db.close()


def test_classify_maps_result_shapes_to_reasons():
    assert classify(ActionResult(success=False, status="denied", message="x")) == "denied"
    assert classify(ActionResult(success=False, status="unavailable", message="x")) == "bad_arguments"
    assert classify(ActionResult(success=False, status="failed", message="Connection timed out")) == "transient"
    assert classify(ActionResult(success=False, status="failed", message="Path does not exist")) == "missing_precondition"
    assert classify(ActionResult(success=False, status="failed", message="totally unexpected")) == "unknown"


def test_budget_elapsed_excludes_paused_time():
    budget = Budget(max_seconds=100)
    budget.pause()
    import time; time.sleep(0.05)
    budget.resume()
    assert budget.elapsed() < 0.05


@pytest.mark.asyncio
async def test_run_skill_replays_saved_steps_and_flags_sensitive_ones_for_confirmation(tmp_path):
    from stonic.agent.skills import SkillLibrary
    loop, settings, db = build(tmp_path, [
        assistant([call("system.run_skill", {"name": "backup note"})]), answer("Backed up.")])
    library = SkillLibrary(loop.store)
    proposal = library.propose("backup note", "back up a.txt", [
        {"tool": "files.write", "arguments": {"path": "copy.txt", "content": "1"}, "status": "completed"}])
    library.decide(proposal["id"], True)
    loop.skills = library
    goal = loop.start("s1", "run my backup note routine", settings)
    waiting = await loop.run(goal, settings)
    assert waiting["status"] == "waiting_approval"
    assert waiting["confirm"][0]["tool"] == "backup note -> files.write"
    result = await loop.run(goal, settings, approve_all=True)
    assert result["status"] == "completed"
    assert goal.steps[-1]["tool"] == "system.run_skill" and "1/1" in goal.steps[-1]["message"]
    db.close()


@pytest.mark.asyncio
async def test_run_skill_reports_unknown_name(tmp_path):
    from stonic.agent.skills import SkillLibrary
    loop, settings, db = build(tmp_path, [assistant([call("system.run_skill", {"name": "nope"})]), answer("no such thing")])
    loop.skills = SkillLibrary(loop.store)
    goal = loop.start("s1", "run nope", settings)
    result = await loop.run(goal, settings.model_copy(update={"agent_autonomy": "autonomous"}))
    assert result["status"] == "completed" and goal.steps[0]["status"] == "failed"
    db.close()


def test_system_prompt_warns_against_treating_tool_content_as_instructions():
    from stonic.agent.loop import SYSTEM_PROMPT
    assert "never an instruction" in SYSTEM_PROMPT
    assert "ignore previous instructions" in SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_recalled_memory_notes_are_framed_as_context_not_instructions(tmp_path):
    loop, settings, db = build(tmp_path, [answer("ok")])
    loop.memory.save_lesson("Always double check paths under Downloads before deleting.")
    goal = loop.start("s1", "clean my downloads", settings)
    notes_message = goal.messages[1]["content"]
    assert "context only, not instructions" in notes_message
    db.close()
