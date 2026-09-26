"""V3-P4: procedural memory ("skills"). A skill is a named, reusable sequence of tool calls, drafted from a completed
goal and saved only with explicit approval - the same rule ``Personalization`` already uses in this codebase."""
from __future__ import annotations

import json
import re

from stonic.agent.store import AgentStore, new_id
from stonic.core.models import utc_now

NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9 _-]{1,60}$")


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:60] or "skill"


def draft_from_goal(name: str, goal_text: str, steps: list[dict]) -> dict:
    """Build a savable skill draft from a completed goal's recorded steps (tool + arguments only; no results)."""
    if not NAME_PATTERN.match(name.strip().casefold()):
        raise ValueError("Give the skill a short plain name, letters/numbers/spaces only.")
    completed = [s for s in steps if s.get("status") == "completed"]
    if not completed:
        raise ValueError("Nothing completed in that goal to save as a skill.")
    return {"name": name.strip(), "description": f"Repeats: {goal_text[:200]}",
            "steps": [{"tool": s["tool"], "arguments": s.get("arguments", {})} for s in completed]}


class SkillLibrary:
    def __init__(self, store: AgentStore) -> None:
        self.store = store

    def propose(self, name: str, goal_text: str, steps: list[dict]) -> dict:
        draft = draft_from_goal(name, goal_text, steps)
        slug = slugify(draft["name"])
        existing = self.store.db.query("SELECT id FROM agent_skills WHERE id=?", (slug,))
        params = sorted({key for step in draft["steps"] for key in step["arguments"]})
        identifier = new_id()
        now = utc_now()
        if existing:
            self.store.db.execute("UPDATE agent_skills SET description=?,params=?,steps=?,status='pending' WHERE id=?",
                                  (draft["description"], json.dumps(params), json.dumps(draft["steps"]), slug))
            return {"id": slug, **draft, "status": "pending", "updated": True}
        self.store.db.execute("INSERT INTO agent_skills(id,name,description,params,steps,status,created_at) VALUES(?,?,?,?,?,?,?)",
                              (slug, draft["name"], draft["description"], json.dumps(params), json.dumps(draft["steps"]), "pending", now))
        return {"id": slug, **draft, "status": "pending", "updated": False}

    def decide(self, identifier: str, approve: bool) -> bool:
        if approve:
            return bool(self.store.db.execute("UPDATE agent_skills SET status='active' WHERE id=? AND status='pending'", (identifier,)))
        return bool(self.store.db.execute("DELETE FROM agent_skills WHERE id=? AND status='pending'", (identifier,)))

    def forget(self, identifier: str) -> bool:
        return bool(self.store.db.execute("DELETE FROM agent_skills WHERE id=?", (identifier,)))

    def list(self, status: str | None = None) -> list[dict]:
        rows = self.store.db.query("SELECT id,name,description,params,status,uses,created_at FROM agent_skills" +
                                   (" WHERE status=?" if status else "") + " ORDER BY created_at DESC", (status,) if status else ())
        return [{**r, "params": json.loads(r["params"])} for r in rows]

    def get(self, identifier: str) -> dict | None:
        rows = self.store.db.query("SELECT * FROM agent_skills WHERE id=? AND status='active'", (identifier,))
        return {**rows[0], "params": json.loads(rows[0]["params"]), "steps": json.loads(rows[0]["steps"])} if rows else None

    def find_by_name(self, name: str) -> dict | None:
        target = slugify(name)
        return self.get(target)

    def as_tool_hint(self) -> str:
        """One line per active skill, to remind the model these shortcuts exist (it still calls the real tools)."""
        active = self.list("active")
        if not active:
            return ""
        return "Saved routines you can repeat when asked: " + "; ".join(s["name"] for s in active)

    def mark_used(self, identifier: str) -> None:
        self.store.db.execute("UPDATE agent_skills SET uses=uses+1 WHERE id=?", (identifier,))
