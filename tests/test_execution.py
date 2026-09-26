import asyncio
import json
from datetime import datetime, timedelta, timezone
import pytest
from stonic.config.settings import Configuration
from stonic.core.models import PermissionLevel
from stonic.diagnostics.health import Diagnostics
from stonic.events.bus import EventBus
from stonic.events.scheduler import ReminderCreate, Scheduler
from stonic.security.permissions import PermissionGate
from stonic.security.secrets import SecretStore
from stonic.storage.database import Database
from stonic.tasks.contracts import Decision
from stonic.tasks.engine import TaskEngine
from stonic.tools.knowledge import Knowledge
from stonic.tools.registry import ToolRegistry
from stonic.tools.workspace import WorkspaceTools


@pytest.fixture
def runtime(tmp_path):
    db = Database(tmp_path / "test.db")
    config = Configuration(db)
    events = EventBus(db)
    registry = ToolRegistry(PermissionGate())
    workspace = WorkspaceTools(config, tmp_path)
    workspace.register(registry)
    Knowledge(db, config).register(registry)
    engine = TaskEngine(db, registry, events)
    yield db, config, events, registry, workspace, engine
    db.close()


def plan(*steps):
    return Decision(kind="plan", message="Execute the requested test plan", steps=[
        {"id": identifier, "title": identifier, "tool": tool, "arguments_json": json.dumps(args), "depends_on": deps}
        for identifier, tool, args, deps in steps])


def test_approval_binds_arguments():
    gate = PermissionGate()
    request = gate.request("files.write", PermissionLevel.SENSITIVE, "Edit A", {"path": "a", "content": "one"})
    gate.decide(request.id, True)
    assert not gate.authorize("files.write", PermissionLevel.SENSITIVE, request.id, {"path": "b", "content": "one"})
    assert not gate.authorize("files.write", PermissionLevel.SENSITIVE, request.id, {"path": "a", "content": "one"})


async def test_write_requires_review_then_verifies_bytes(runtime):
    _, _, _, _, workspace, engine = runtime
    job = engine.create(plan(("write", "files.write", {"path": "result.txt", "content": "Verified"}, [])), "test")
    waiting = await engine.run(job["id"])
    assert waiting["status"] == "waiting_approval"
    assert not (workspace.root / "result.txt").exists()
    assert waiting["approval"]["arguments"]["path"] == str(workspace.root / "result.txt")
    completed = await engine.decide(job["id"], waiting["approval"]["id"], True)
    assert completed["status"] == "completed"
    assert (workspace.root / "result.txt").read_text() == "Verified"
    assert completed["steps"][0]["result"]["verification"]
    with pytest.raises(ValueError): await engine.decide(job["id"], waiting["approval"]["id"], True)


async def test_denial_and_workspace_change_cannot_redirect_write(runtime, tmp_path):
    _, config, _, _, workspace, engine = runtime
    original = workspace.root
    job = engine.create(plan(("write", "files.write", {"path": "result.txt", "content": "x"}, [])), "test")
    waiting = await engine.run(job["id"])
    config.update({"workspace_root": str(tmp_path / "elsewhere")})
    result = await engine.decide(job["id"], waiting["approval"]["id"], True)
    assert result["status"] == "failed"
    assert not (original / "result.txt").exists()
    assert not (workspace.root / "result.txt").exists()


async def test_dependent_file_edit_detects_changed_content(runtime):
    _, _, _, _, workspace, engine = runtime
    target = workspace.root / "note.txt"
    target.write_text("before")
    job = engine.create(plan(("read", "files.read", {"path": "note.txt"}, []),
        ("edit", "files.write", {"path": "note.txt", "content": "after", "expected_sha256": {"$step": "read", "path": ["data", "sha256"]}}, ["read"])), "test")
    waiting = await engine.run(job["id"])
    assert waiting["steps"][0]["status"] == "completed"
    target.write_text("user edit")
    result = await engine.decide(job["id"], waiting["approval"]["id"], True)
    assert result["status"] == "failed"
    assert target.read_text() == "user edit"


async def test_cancel_pending_action_and_restart_do_not_execute(runtime):
    db, _, events, registry, workspace, engine = runtime
    job = engine.create(plan(("write", "files.write", {"path": "cancel.txt", "content": "x"}, [])), "test")
    await engine.run(job["id"])
    restored = TaskEngine(db, registry, events)
    assert restored.get(job["id"])["status"] == "paused"
    assert restored.cancel(job["id"])["status"] == "cancelled"
    assert (await restored.run(job["id"]))["status"] == "cancelled"
    assert not (workspace.root / "cancel.txt").exists()


def test_paths_and_graph_validation(runtime):
    workspace = runtime[4]
    for path in ["../outside", ".env", ".ssh/key", "node_modules/private"]:
        with pytest.raises(ValueError): workspace.resolve(path, False)
    with pytest.raises(ValueError):
        plan(("a", "files.read", {"path": "x"}, ["b"]), ("b", "files.read", {"path": "x"}, ["a"]))


def test_memory_index_tracks_edit_and_forget(runtime):
    db, config = runtime[:2]
    knowledge = Knowledge(db, config)
    record = db.create_record("memory", "Project language", "Kotlin compilers")
    assert knowledge.relevant("Kotlin")[0]["id"] == record["id"]
    db.update_record("memory", record["id"], {"content": "Python parsers"})
    assert knowledge.relevant("Kotlin") == []
    assert knowledge.relevant("Python")
    db.execute("DELETE FROM records WHERE id=?", (record["id"],))
    assert knowledge.relevant("Python") == []


def test_reminder_delivery_is_durable_and_deduplicated(runtime, tmp_path):
    db, config, events = runtime[:3]
    scheduler = Scheduler(db, events, config, Diagnostics(tmp_path))
    start = datetime.now(timezone.utc)
    scheduler.create(ReminderCreate(title="Recurring", due_at=start + timedelta(seconds=10), interval_seconds=60))
    scheduler.tick(start + timedelta(seconds=190))
    scheduler.tick(start + timedelta(seconds=191))
    assert len(db.query("SELECT * FROM notifications")) == 1
    assert datetime.fromisoformat(scheduler.list().data["schedules"][0]["due_at"]) > start + timedelta(seconds=190)
    restarted = Scheduler(db, events, config, Diagnostics(tmp_path))
    restarted.tick(start + timedelta(seconds=192))
    assert len(db.query("SELECT * FROM notifications")) == 1


def test_dpapi_roundtrip_and_provider_scope(tmp_path, monkeypatch):
    import os
    if os.name != "nt": pytest.skip("Windows DPAPI contract")
    monkeypatch.delenv("STONIC_LLM_API_KEY", raising=False)
    monkeypatch.delenv("XKIRO_API_KEY", raising=False)
    store = SecretStore(tmp_path)
    store.save("sk-xt-test-key-never-real")
    assert b"sk-xt-test-key-never-real" not in store.path.read_bytes()
    assert store.key("https://api.xkiro.com/v1") == "sk-xt-test-key-never-real"
    assert store.key("https://example.org/v1") == ""
    store.delete()
    assert not store.configured("https://api.xkiro.com/v1")
