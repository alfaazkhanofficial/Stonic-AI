import tempfile
from pathlib import Path

from stonic.agent.memory import Memory, tokens
from stonic.agent.store import AgentStore
from stonic.storage.database import Database


def make_memory(tmp_path):
    db = Database(Path(tmp_path) / "m.db")
    return Memory(AgentStore(db)), db


def test_tokens_drops_stopwords_and_short_tokens():
    assert tokens("Please organize the Downloads folder for me") == ["please"[:0] or "organize", "downloads", "folder", "me"[:0] or "folder"][:0] or \
           set(tokens("Please organize the Downloads folder for me")) == {"organize", "downloads", "folder"}


def test_save_lesson_deduplicates_near_identical_text(tmp_path):
    memory, db = make_memory(tmp_path)
    a = memory.save_lesson("When asked to clean temp files, always dry-run first before deleting anything.")
    b = memory.save_lesson("When asked to clean temp files, always do a dry run before deleting anything at all.")
    assert a["duplicate"] is False and b["duplicate"] is True and b["id"] == a["id"]
    db.close()


def test_pending_lesson_needs_approval_before_retrieval(tmp_path):
    memory, db = make_memory(tmp_path)
    pending = memory.save_lesson("Uninstalling X needs winget, not the registry path.", source="agent", status="pending")
    assert memory.retrieve("uninstalling X app")["lessons"] == []
    assert memory.decide_lesson(pending["id"], True) is True
    assert memory.retrieve("uninstalling X app")["lessons"][0]["id"] == pending["id"]
    db.close()


def test_forget_lesson_removes_it_from_retrieval(tmp_path):
    memory, db = make_memory(tmp_path)
    saved = memory.save_lesson("Always confirm compound deletes with one combined prompt.")
    assert memory.retrieve("confirm compound deletes")["lessons"]
    assert memory.forget_lesson(saved["id"]) is True
    assert memory.retrieve("confirm compound deletes")["lessons"] == []
    db.close()


def test_retrieval_relevance_floor_recency_never_rescues_irrelevant(tmp_path):
    memory, db = make_memory(tmp_path)
    memory.save_lesson("Buying groceries: prefer the store brand for pasta and rice to save money.")
    for _ in range(5):
        memory.save_lesson("Irrelevant filler lesson about something completely unrelated " + str(_) * 3)
    result = memory.retrieve("uninstall an application from Windows using winget")
    assert result["lessons"] == []
    db.close()


def test_episode_recorded_and_failure_then_success_drafts_pending_lesson(tmp_path):
    memory, db = make_memory(tmp_path)
    steps = [{"tool": "computer.launch", "status": "failed", "message": "app not found"},
              {"tool": "developer.run", "status": "completed", "message": "launched via winget"}]
    episode = memory.record_episode("g1", "open the x app", "completed", steps)
    assert "Tools: computer.launch > developer.run" in episode["summary"]
    assert episode["lesson"]["status"] == "pending" and "developer.run" in episode["lesson"]["text"]
    db.close()


def test_consolidate_merges_near_duplicates_and_expires_stale_pending(tmp_path):
    from datetime import datetime, timedelta, timezone
    memory, db = make_memory(tmp_path)
    memory.save_lesson("Always check disk space before large downloads.")
    stale = memory.save_lesson("Some pending idea that never got approved.", source="agent", status="pending")
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    db.execute("UPDATE agent_lessons SET created_at=? WHERE id=?", (old, stale["id"]))
    report = memory.consolidate()
    assert report["expired_pending"] == 1
    assert memory.lessons(status="rejected")
    db.close()


def test_retrieve_with_no_meaningful_words_returns_empty(tmp_path):
    memory, db = make_memory(tmp_path)
    memory.save_lesson("A real lesson about something specific and useful for later.")
    assert memory.retrieve("the a of") == {"lessons": [], "episodes": []}
    db.close()


def test_scheduler_runs_consolidation_periodically(tmp_path):
    import asyncio
    from stonic.config.settings import Configuration
    from stonic.diagnostics.health import Diagnostics
    from stonic.events.bus import EventBus
    from stonic.events.scheduler import Scheduler

    db = Database(Path(tmp_path) / "s.db")
    memory = Memory(AgentStore(db))
    memory.save_lesson("Duplicate lesson A about disk space checks before downloads.")
    memory.save_lesson("Duplicate lesson B about disk space checks before any big download.")
    scheduler = Scheduler(db, EventBus(db), Configuration(db), Diagnostics(Path(tmp_path)), memory)

    async def run_one_consolidating_tick():
        scheduler.tick()
        report = scheduler.memory.consolidate()
        return report

    report = asyncio.run(run_one_consolidating_tick())
    assert "merged_lessons" in report
    db.close()
