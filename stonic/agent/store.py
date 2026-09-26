"""SQLite tables for the agent: goals (checkpoints), actions (detailed audit), episodes, lessons, skills.

Tables are created with IF NOT EXISTS so the existing schema version and migration tests are untouched.
"""
from __future__ import annotations

import json
from uuid import uuid4

from stonic.core.models import utc_now

TABLES = (
    "CREATE TABLE IF NOT EXISTS agent_goals (id TEXT PRIMARY KEY, parent_id TEXT, session_id TEXT NOT NULL, goal TEXT NOT NULL, status TEXT NOT NULL, autonomy TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, payload TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS agent_actions (id TEXT PRIMARY KEY, goal_id TEXT NOT NULL, seq INTEGER NOT NULL, time TEXT NOT NULL, tool TEXT NOT NULL, level INTEGER NOT NULL, arguments TEXT NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL DEFAULT '', verification TEXT NOT NULL DEFAULT '', approved_by TEXT NOT NULL DEFAULT 'policy')",
    "CREATE TABLE IF NOT EXISTS agent_episodes (id TEXT PRIMARY KEY, goal_id TEXT NOT NULL, goal TEXT NOT NULL, outcome TEXT NOT NULL, summary TEXT NOT NULL, tools TEXT NOT NULL, created_at TEXT NOT NULL, uses INTEGER NOT NULL DEFAULT 0, vector TEXT NOT NULL DEFAULT '[]')",
    "CREATE TABLE IF NOT EXISTS agent_lessons (id TEXT PRIMARY KEY, text TEXT NOT NULL, status TEXT NOT NULL, source TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, uses INTEGER NOT NULL DEFAULT 0, vector TEXT NOT NULL DEFAULT '[]')",
    "CREATE TABLE IF NOT EXISTS agent_skills (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, description TEXT NOT NULL, params TEXT NOT NULL, steps TEXT NOT NULL, status TEXT NOT NULL, uses INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS agent_undo (id TEXT PRIMARY KEY, goal_id TEXT NOT NULL DEFAULT '', time TEXT NOT NULL, op TEXT NOT NULL, payload TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', undone INTEGER NOT NULL DEFAULT 0)",
    "CREATE INDEX IF NOT EXISTS agent_actions_goal ON agent_actions(goal_id, seq)",
    "CREATE INDEX IF NOT EXISTS agent_goals_session ON agent_goals(session_id, updated_at)",
)


def new_id() -> str:
    return uuid4().hex


class AgentStore:
    def __init__(self, db) -> None:
        self.db = db
        for statement in TABLES:
            db.execute(statement)
        try:
            db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS agent_fts USING fts5(kind UNINDEXED, ref UNINDEXED, text)")
            self.fts = True
        except Exception:      # SQLite built without FTS5: retrieval falls back to vectors only
            self.fts = False

    # -- goals -------------------------------------------------------------------------------------------------------
    def save_goal(self, goal_id: str, parent_id: str | None, session_id: str, text: str, status: str, autonomy: str, payload: dict) -> None:
        now = utc_now()
        self.db.execute(
            "INSERT INTO agent_goals(id,parent_id,session_id,goal,status,autonomy,created_at,updated_at,payload) VALUES(?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET status=excluded.status,updated_at=excluded.updated_at,payload=excluded.payload",
            (goal_id, parent_id, session_id, text[:2000], status, autonomy, now, now, json.dumps(payload, ensure_ascii=False, default=str)))

    def load_goal(self, goal_id: str) -> dict | None:
        rows = self.db.query("SELECT * FROM agent_goals WHERE id=?", (goal_id,))
        return {**rows[0], "payload": json.loads(rows[0]["payload"])} if rows else None

    def list_goals(self, session_id: str | None = None, limit: int = 30, statuses: tuple[str, ...] = ()) -> list[dict]:
        sql, values = "SELECT id,parent_id,session_id,goal,status,autonomy,created_at,updated_at FROM agent_goals", []
        clauses = []
        if session_id:
            clauses.append("session_id=?"); values.append(session_id)
        if statuses:
            clauses.append(f"status IN ({','.join('?' * len(statuses))})"); values.extend(statuses)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        return self.db.query(sql + " ORDER BY updated_at DESC LIMIT ?", (*values, limit))

    # -- actions (detailed audit; the shared audit table keeps only recent rows) ---------------------------------------
    def add_action(self, goal_id: str, seq: int, tool: str, level: int, arguments: dict, status: str, message: str = "",
                   verification: str = "", approved_by: str = "policy") -> str:
        identifier = new_id()
        self.db.execute("INSERT INTO agent_actions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (identifier, goal_id, seq, utc_now(), tool, int(level), json.dumps(arguments, ensure_ascii=False, default=str)[:4000],
                         status, message[:500], verification[:300], approved_by))
        return identifier

    def finish_action(self, identifier: str, status: str, message: str, verification: str) -> None:
        self.db.execute("UPDATE agent_actions SET status=?,message=?,verification=? WHERE id=?", (status, message[:500], verification[:300], identifier))

    def actions(self, goal_id: str | None = None, since: str | None = None, limit: int = 200) -> list[dict]:
        sql, values, clauses = "SELECT * FROM agent_actions", [], []
        if goal_id:
            clauses.append("goal_id=?"); values.append(goal_id)
        if since:
            clauses.append("time>=?"); values.append(since)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        return self.db.query(sql + " ORDER BY time DESC, seq DESC LIMIT ?", (*values, limit))

    # -- fts helpers -------------------------------------------------------------------------------------------------
    def index(self, kind: str, ref: str, text: str) -> None:
        if self.fts:
            self.db.execute("DELETE FROM agent_fts WHERE kind=? AND ref=?", (kind, ref))
            self.db.execute("INSERT INTO agent_fts(kind,ref,text) VALUES(?,?,?)", (kind, ref, text[:4000]))

    def unindex(self, kind: str, ref: str) -> None:
        if self.fts:
            self.db.execute("DELETE FROM agent_fts WHERE kind=? AND ref=?", (kind, ref))

    def search(self, kind: str, words: list[str], limit: int = 20) -> list[str]:
        if not self.fts or not words:
            return []
        expression = " OR ".join('"' + w.replace('"', '""') + '"' for w in words[:16])
        try:
            rows = self.db.query("SELECT ref FROM agent_fts WHERE kind=? AND agent_fts MATCH ? ORDER BY rank LIMIT ?", (kind, expression, limit))
        except Exception:
            return []
        return [r["ref"] for r in rows]

    # -- undo journal ------------------------------------------------------------------------------------------------
    def add_undo(self, op: str, payload: dict, description: str, goal_id: str = "") -> str:
        identifier = new_id()
        self.db.execute("INSERT INTO agent_undo(id,goal_id,time,op,payload,description) VALUES(?,?,?,?,?,?)",
                        (identifier, goal_id, utc_now(), op, json.dumps(payload, ensure_ascii=False), description[:500]))
        return identifier

    def undo_entries(self, limit: int = 20, include_undone: bool = False) -> list[dict]:
        rows = self.db.query(f"SELECT * FROM agent_undo {'' if include_undone else 'WHERE undone=0'} ORDER BY time DESC, rowid DESC LIMIT ?", (limit,))
        return [{**r, "payload": json.loads(r["payload"])} for r in rows]

    def mark_undone(self, identifier: str) -> None:
        self.db.execute("UPDATE agent_undo SET undone=1 WHERE id=?", (identifier,))
