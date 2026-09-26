"""Registered V3 scenarios. ``baseline`` scenarios must pass on the current codebase; every other scenario names the
phase that must deliver it and is reported as pending until then.

Status as of the V3.0 build (P0-P8, partial P9, P10 script): every workstream A/B/D/F pending item below except the
explicitly-marked ones is now delivered and covered by its own dedicated test module rather than this generic
harness, because those mechanisms (native tool calling, the goal loop, full-system control, skills, voice
confirmation) need real fakes/mocks (a scripted OpenAI-compatible transport, PermissionGate, winget) that this
harness's simple ``decide()``-only ScriptedProvider does not model. See:
  tests/test_agent_provider.py    - native tool calling, schema simplification, model router fallback chain
  tests/test_agent_loop.py        - plan/act/verify/reflect, budgets, checkpoint/resume, combined confirmations, skills
  tests/test_agent_memory.py      - hybrid retrieval, relevance floor, episodes, consolidation
  tests/test_agent_skills.py      - propose/approve/reject procedural memory
  tests/test_system_control.py    - full-disk files, undo journal, app uninstall matching, organize-folder dry-run
  tests/test_agent_chat_integration.py - CoreService.chat -> real agent loop, including the Altrex/Jarvis/uninstall
                                         compound example with one combined confirmation
  tests/test_voicelive_live.py, test_agent_chat_integration.py - the confirm_pending_action voice bridge
  tests/test_agent_api.py         - goals/lessons/skills/kill-switch REST endpoints
This file's PENDING list is kept for what genuinely still needs a real Windows machine or further UI work (see
docs/V3_AUDIT.md's "Still open after this build" section) rather than duplicating the above as generic scenarios.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from tests.evals.harness import Scenario, answer, clarify, plan


def _seed(name: str, text: str):
    def setup(core):
        core.workspace.root.mkdir(parents=True, exist_ok=True)
        (core.workspace.root / name).write_text(text)
    return setup


def _file_edit_script():
    def second(core):
        from stonic.tools.workspace import FilePath
        sha = core.workspace.read(FilePath(path="note.txt")).data["sha256"]
        return plan("Apply the requested correction", ("edit", "files.write",
                    {"path": "note.txt", "expected_sha256": sha, "content": "after"}, []))
    return [plan("Inspect the file", ("read", "files.read", {"path": "note.txt"}, [])), second,
            answer("note.txt now contains 'after'.")]


def _reminder_script():
    def make(_core):
        due = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        return plan("Create the reminder", ("r", "reminders.create", {"title": "stretch", "due_at": due}, []))
    return [make, answer("Reminder set.")]


def _check_file(name: str, expected: str):
    def check(core, _reply):
        path = core.workspace.root / name
        return None if path.is_file() and path.read_text() == expected else f"{name} does not contain {expected!r}"
    return check


def _check_reminder(core, _reply):
    listed = json.dumps(core.tools.execute("reminders.list", {}).data)
    return None if "stretch" in listed else "reminder was not persisted"


def _check_note(core, _reply):
    found = core.db.query("SELECT title FROM records WHERE title=?", ("Buy filters",))
    return None if found else "note was not persisted"


def _check_clarify(_core, reply):
    return None if "?" in reply else "ambiguous request should produce a clarifying question"


def _check_no_deletion(core, _reply):
    return None if (core.workspace.root / "keep.txt").exists() else "file was deleted without clarification"


BASELINE = [
    Scenario("file_edit_needs_approval", "A", "Change note.txt to after.", _file_edit_script(),
             setup=_seed("note.txt", "before"), expect_tools=["files.read", "files.write"],
             check=_check_file("note.txt", "after"), max_decisions=3),
    Scenario("multi_step_read_then_write", "A", "Read a.txt and save a copy of it as b.txt.",
             [plan("Copy a to b", ("read", "files.read", {"path": "a.txt"}, []),
                   ("write", "files.write", {"path": "b.txt", "content": "alpha"}, ["read"])),
              answer("Saved b.txt.")],
             setup=_seed("a.txt", "alpha"), expect_tools=["files.read", "files.write"],
             check=_check_file("b.txt", "alpha"), max_decisions=2),
    Scenario("ambiguous_request_clarifies", "A", "Delete the file.", [clarify("Which file do you want deleted?")],
             setup=_seed("keep.txt", "x"), check=lambda c, r: _check_clarify(c, r) or _check_no_deletion(c, r),
             max_decisions=1),
    Scenario("reminder_is_persisted", "F", "Remind me to stretch in ten minutes.", _reminder_script(),
             expect_tools=["reminders.create"], check=_check_reminder, max_decisions=2),
    Scenario("note_is_persisted", "B", "Create a note titled Buy filters.",
             [plan("Save the note", ("n", "records.create", {"kind": "notes", "title": "Buy filters", "content": "HEPA"}, [])),
              answer("Saved the note.")],
             expect_tools=["records.create"], check=_check_note, max_decisions=2),
]

# Genuinely still open - needs a real Windows machine, more UI work, or is intentionally out of scope for this pass.
PENDING = [
    ("gui_fallback_when_no_api", "D", "V3-P6/P7", "Turn on dark mode in this app.",
     "computer-use loop (UIA tree -> vision fallback) for apps with no API - needs pywinauto/uiautomation on real Windows; see scripts/validate_windows.py's ui_automation_library check"),
    ("browser_multitab_research", "F", "V3-P7", "Research two topics across several tabs and cite findings.",
     "multi-tab browser agent; current web.research is single-query, not a full tabbed browsing agent"),
    ("offline_lite_small_local_model", "F", "V3-P8", "Open notepad (with no internet).",
     "a small local model for basic commands when the cloud is down; current fallback is the existing deterministic plan/answer path, not a bundled local model"),
    ("crash_recovery_restores_goal", "E", "V3-P10", "(after a real process crash)",
     "checkpoint/resume is implemented and unit-tested (test_agent_loop.py), but a real kill -9 / Windows crash recovery pass needs the actual packaged app"),
    ("voice_multistep_real_hardware", "C", "V3-P10", "(voice, on real hardware) Clean my temp files, with a spoken confirmation and a barge-in.",
     "the confirm_pending_action bridge is implemented and tested against a scripted Gemini Live session; real microphone/speaker latency and barge-in timing need the real machine"),
    ("electron_ui_e2e", "E", "V3-P9/P10", "(Playwright e2e)",
     "tests/e2e/*.spec.ts need msedge and are Windows-only; not runnable in this Linux sandbox - run `npm run test:ui` on the Windows machine"),
]

SCENARIOS = BASELINE + [Scenario(i, w, u, required_phase=p, note=n) for i, w, p, u, n in PENDING]
