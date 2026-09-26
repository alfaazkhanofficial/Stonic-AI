from pathlib import Path

from stonic.agent.skills import SkillLibrary, draft_from_goal, slugify
from stonic.agent.store import AgentStore
from stonic.storage.database import Database


def build(tmp_path):
    db = Database(Path(tmp_path) / "s.db")
    return SkillLibrary(AgentStore(db)), db


def test_slugify_normalizes_to_a_stable_key():
    assert slugify("Upload Prep!!") == "upload-prep"
    assert slugify("Upload   prep") == "upload-prep"


def test_draft_from_goal_rejects_bad_names_and_empty_steps():
    steps = [{"tool": "files.write", "arguments": {"path": "a.txt"}, "status": "completed"}]
    draft_from_goal("upload prep", "prep uploads", steps)
    try:
        draft_from_goal("", "x", steps); assert False
    except ValueError:
        pass
    try:
        draft_from_goal("valid name", "x", [{"tool": "a", "status": "failed"}]); assert False
    except ValueError:
        pass


def test_propose_creates_pending_skill_not_visible_until_approved(tmp_path):
    library, db = build(tmp_path)
    steps = [{"tool": "files.write", "arguments": {"path": "a.txt", "content": "x"}, "status": "completed"}]
    proposal = library.propose("upload prep", "prepare upload folder", steps)
    assert proposal["status"] == "pending" and library.list("active") == []
    assert library.decide(proposal["id"], True) is True
    assert library.list("active")[0]["id"] == proposal["id"]
    db.close()


def test_reject_deletes_the_pending_skill(tmp_path):
    library, db = build(tmp_path)
    steps = [{"tool": "files.write", "arguments": {"path": "a.txt"}, "status": "completed"}]
    proposal = library.propose("temp skill", "goal", steps)
    assert library.decide(proposal["id"], False) is True
    assert library.list() == []
    db.close()


def test_find_by_name_only_returns_active_skills(tmp_path):
    library, db = build(tmp_path)
    steps = [{"tool": "files.write", "arguments": {"path": "a.txt"}, "status": "completed"}]
    proposal = library.propose("nightly cleanup", "goal", steps)
    assert library.find_by_name("nightly cleanup") is None
    library.decide(proposal["id"], True)
    found = library.find_by_name("Nightly Cleanup")
    assert found and found["steps"][0]["tool"] == "files.write"
    db.close()


def test_re_proposing_the_same_name_updates_and_resets_to_pending(tmp_path):
    library, db = build(tmp_path)
    steps = [{"tool": "files.write", "arguments": {"path": "a.txt"}, "status": "completed"}]
    first = library.propose("upload prep", "goal one", steps)
    library.decide(first["id"], True)
    second = library.propose("upload prep", "goal two, more detail", steps)
    assert second["id"] == first["id"] and second["updated"] is True
    assert library.list("active") == []           # back to pending until re-approved
    db.close()


def test_forget_removes_regardless_of_status(tmp_path):
    library, db = build(tmp_path)
    steps = [{"tool": "files.write", "arguments": {"path": "a.txt"}, "status": "completed"}]
    proposal = library.propose("xx cleanup", "goal", steps)
    library.decide(proposal["id"], True)
    assert library.forget(proposal["id"]) is True
    assert library.list() == []
    db.close()
