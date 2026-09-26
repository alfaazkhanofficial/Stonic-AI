"""V3 evaluation harness (V3-P0 skeleton).

Runs realistic goals through the REAL CoreService / TaskEngine / PermissionGate using a scripted provider,
and reports success, decisions used, tools called, approvals and elapsed time. Scenarios whose required
capability does not exist yet are registered as ``target`` scenarios: they are counted and reported as
pending, never silently dropped and never faked as passing.

Run the report:  python scripts/run-evals.py
"""
from __future__ import annotations

import json
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from stonic.config.settings import Configuration
from stonic.core.models import Activity, ChatInput
from stonic.core.service import CoreService
from stonic.diagnostics.health import Diagnostics
from stonic.events.bus import EventBus
from stonic.storage.database import Database
from stonic.tasks.contracts import Decision


def plan(message: str, *steps: tuple[str, str, dict, list[str]]) -> Decision:
    """Build a plan Decision from (id, tool, arguments, depends_on) tuples."""
    return Decision(kind="plan", message=message, steps=[
        {"id": i, "title": f"{tool} step", "tool": tool, "arguments_json": json.dumps(args), "depends_on": deps}
        for i, tool, args, deps in steps])


def answer(message: str) -> Decision:
    return Decision(kind="answer", message=message, steps=[])


def clarify(message: str) -> Decision:
    return Decision(kind="clarify", message=message, steps=[])


class ScriptedProvider:
    """Deterministic stand-in for the model: returns the scripted decisions in order."""

    def __init__(self, decisions: list[Decision | Callable[["CoreService"], Decision]]) -> None:
        self.script, self.calls, self.core = list(decisions), 0, None

    def available(self, _settings) -> bool:
        return True

    async def complete(self, *_args) -> str:
        return "Task finished; evidence recorded."

    async def stream(self, *_args):
        yield "Understood."

    async def decide(self, _settings, _messages, _tools, _context) -> Decision:
        item = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        return item(self.core) if callable(item) else item


@dataclass
class Scenario:
    id: str
    workstream: str                       # A agent core, B memory, C voice, D pc control, E reliability, F signature
    utterance: str
    script: list = field(default_factory=list)
    setup: Callable[[CoreService], None] | None = None
    check: Callable[[CoreService, str], str | None] | None = None   # returns a failure reason, or None when satisfied
    auto_approve: bool = True
    expect_tools: list[str] = field(default_factory=list)
    max_decisions: int = 6
    required_phase: str = "baseline"      # "baseline" runs now; any "V3-Pn" value is a pending target
    note: str = ""


@dataclass
class Result:
    id: str
    workstream: str
    status: str                           # passed | failed | pending
    reason: str = ""
    decisions: int = 0
    tools: list[str] = field(default_factory=list)
    approvals: int = 0
    seconds: float = 0.0
    required_phase: str = "baseline"


async def run_scenario(scenario: Scenario, root: Path | None = None) -> Result:
    if scenario.required_phase != "baseline":
        return Result(scenario.id, scenario.workstream, "pending", f"needs {scenario.required_phase}: {scenario.note}",
                      required_phase=scenario.required_phase)
    root = root or Path(tempfile.mkdtemp(prefix="stonic-eval-"))
    db = Database(root / "eval.sqlite")
    started = time.perf_counter()
    approvals = 0
    try:
        provider = ScriptedProvider(scenario.script)
        core = CoreService(db, Configuration(db), Diagnostics(root), EventBus(db), provider)
        provider.core = core
        core.state.transition(Activity.IDLE)
        if scenario.setup:
            scenario.setup(core)
        reply = (await core.chat(ChatInput(content=scenario.utterance)))["content"]
        for _ in range(scenario.max_decisions):
            waiting = next((j for j in core.tasks.list() if j["status"] == "waiting_approval"), None)
            if not waiting or not scenario.auto_approve:
                break
            approvals += 1
            job = await core.tasks.decide(waiting["id"], waiting["approval"]["id"], True)
            reply = await core.advance(job)
        tools = [s["tool"] for j in core.tasks.list() for s in j["steps"] if s.get("status") == "completed"]
        reason = None
        missing = [t for t in scenario.expect_tools if t not in tools]
        if missing:
            reason = f"expected tools not completed: {missing}"
        elif provider.calls > scenario.max_decisions:
            reason = f"used {provider.calls} decisions (budget {scenario.max_decisions})"
        elif scenario.check:
            reason = scenario.check(core, reply)
        return Result(scenario.id, scenario.workstream, "failed" if reason else "passed", reason or "",
                      provider.calls, tools, approvals, round(time.perf_counter() - started, 3))
    except Exception as error:  # a crashing scenario is a failed scenario, never a skipped one
        return Result(scenario.id, scenario.workstream, "failed", f"{type(error).__name__}: {error}",
                      seconds=round(time.perf_counter() - started, 3))
    finally:
        db.close()


def summarize(results: list[Result]) -> dict:
    ran = [r for r in results if r.status != "pending"]
    return {
        "total": len(results), "passed": sum(r.status == "passed" for r in results),
        "failed": sum(r.status == "failed" for r in results), "pending": sum(r.status == "pending" for r in results),
        "pass_rate_of_runnable": round(sum(r.status == "passed" for r in ran) / len(ran), 3) if ran else None,
        "by_workstream": {w: {"passed": sum(r.status == "passed" and r.workstream == w for r in results),
                              "failed": sum(r.status == "failed" and r.workstream == w for r in results),
                              "pending": sum(r.status == "pending" and r.workstream == w for r in results)}
                          for w in sorted({r.workstream for r in results})},
        "results": [r.__dict__ for r in results],
    }
