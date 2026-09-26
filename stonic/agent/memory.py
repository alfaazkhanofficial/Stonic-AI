"""Agent memory: hybrid (keyword + vector) retrieval, episodes, lessons and consolidation.

Vectors are CPU-cheap hashed n-gram embeddings (no model download, no network) so retrieval works on any machine.
Recency never admits an irrelevant memory: an item must clear a relevance threshold before recency can order it.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone

import numpy as np

from stonic.agent.store import AgentStore, new_id
from stonic.core.models import utc_now

DIM = 384
STOP = frozenset("the a an and or of to in on for with at by from is are was were be been it this that these those my me i you your our we they he she "
                 "please can could would should do does did have has had not no yes as if then than so up out about into over after before "
                 "kar karo ka ki ke hai hain ko se me par aur ya".split())
RELEVANCE_FLOOR = 0.16       # cosine below this is noise unless keyword search also hit
CONSOLIDATE_SIMILARITY = 0.85
EPISODE_CAP = 500


def tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"\w+", text.casefold(), re.UNICODE) if len(w) > 1 and w not in STOP]


def _slot(feature: str) -> tuple[int, float]:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "little")
    return value % DIM, 1.0 if (value >> 40) & 1 else -1.0


class HashEmbedder:
    def embed(self, text: str) -> np.ndarray:
        words = tokens(text)
        counts: dict[str, float] = {}
        for word in words:
            counts["w:" + word] = counts.get("w:" + word, 0) + 1
            if len(word) >= 5:
                for i in range(len(word) - 2):
                    counts["c:" + word[i:i + 3]] = counts.get("c:" + word[i:i + 3], 0) + 0.25
        for a, b in zip(words, words[1:]):
            counts[f"b:{a}_{b}"] = counts.get(f"b:{a}_{b}", 0) + 0.7
        vector = np.zeros(DIM, dtype=np.float32)
        for feature, count in counts.items():
            slot, sign = _slot(feature)
            vector[slot] += sign * (1 + math.log(count)) if count >= 1 else sign * count
        norm = float(np.linalg.norm(vector))
        return vector / norm if norm else vector


def _load(vector_json: str) -> np.ndarray | None:
    try:
        array = np.asarray(json.loads(vector_json), dtype=np.float32)
        return array if array.shape == (DIM,) else None
    except (ValueError, TypeError):
        return None


class Memory:
    def __init__(self, store: AgentStore, embedder: HashEmbedder | None = None) -> None:
        self.store, self.embedder = store, embedder or HashEmbedder()

    # -- lessons -----------------------------------------------------------------------------------------------------
    def save_lesson(self, text: str, source: str = "user", status: str = "active") -> dict:
        text = " ".join(text.split())[:600]
        if not text:
            raise ValueError("A lesson cannot be blank")
        vector = self.embedder.embed(text)
        for row in self.store.db.query("SELECT id,text,vector,status FROM agent_lessons WHERE status IN ('active','pending')"):
            other = _load(row["vector"])
            if other is not None and float(vector @ other) >= CONSOLIDATE_SIMILARITY:
                if status == "active" and row["status"] == "pending":
                    self.store.db.execute("UPDATE agent_lessons SET status='active',updated_at=? WHERE id=?", (utc_now(), row["id"]))
                return {"id": row["id"], "text": row["text"], "duplicate": True}
        identifier, now = new_id(), utc_now()
        self.store.db.execute("INSERT INTO agent_lessons(id,text,status,source,created_at,updated_at,vector) VALUES(?,?,?,?,?,?,?)",
                              (identifier, text, status, source, now, now, json.dumps(vector.tolist())))
        self.store.index("lesson", identifier, text)
        return {"id": identifier, "text": text, "duplicate": False, "status": status}

    def decide_lesson(self, identifier: str, approve: bool) -> bool:
        changed = self.store.db.execute("UPDATE agent_lessons SET status=?,updated_at=? WHERE id=? AND status='pending'",
                                        ("active" if approve else "rejected", utc_now(), identifier))
        if not approve:
            self.store.unindex("lesson", identifier)
        return bool(changed)

    def forget_lesson(self, identifier: str) -> bool:
        self.store.unindex("lesson", identifier)
        return bool(self.store.db.execute("DELETE FROM agent_lessons WHERE id=?", (identifier,)))

    def lessons(self, status: str | None = None) -> list[dict]:
        rows = self.store.db.query("SELECT id,text,status,source,created_at,uses FROM agent_lessons" + (" WHERE status=?" if status else "") +
                                   " ORDER BY updated_at DESC LIMIT 200", (status,) if status else ())
        return rows

    # -- episodes ----------------------------------------------------------------------------------------------------
    def record_episode(self, goal_id: str, goal: str, outcome: str, steps: list[dict]) -> dict:
        tools = [s["tool"] for s in steps]
        failed = [s for s in steps if s.get("status") == "failed"]
        summary = f"Goal: {goal[:200]}. Outcome: {outcome}. Tools: {' > '.join(tools[:12]) or 'none'}." + \
                  (f" Failures: {'; '.join(f'{s['tool']}: {s.get('message', '')[:80]}' for s in failed[:3])}." if failed else "")
        identifier = new_id()
        self.store.db.execute("INSERT INTO agent_episodes(id,goal_id,goal,outcome,summary,tools,created_at,vector) VALUES(?,?,?,?,?,?,?,?)",
                              (identifier, goal_id, goal[:2000], outcome, summary, json.dumps(tools), utc_now(),
                               json.dumps(self.embedder.embed(goal + " " + " ".join(tools)).tolist())))
        self.store.index("episode", identifier, goal + " " + " ".join(tools))
        lesson = self._draft_lesson(goal, steps) if outcome == "completed" else None
        return {"id": identifier, "summary": summary, "lesson": lesson}

    def _draft_lesson(self, goal: str, steps: list[dict]) -> dict | None:
        """A failure followed by a different successful tool for the same goal becomes a pending lesson (needs approval)."""
        for index, step in enumerate(steps):
            if step.get("status") == "failed":
                later = next((s for s in steps[index + 1:] if s.get("status") == "completed" and s["tool"] != step["tool"]), None)
                if later:
                    text = f"When asked like \"{goal[:90]}\", {step['tool']} failed ({step.get('message', '')[:90]}); {later['tool']} worked instead."
                    return self.save_lesson(text, source="agent", status="pending")
        return None

    # -- retrieval ---------------------------------------------------------------------------------------------------
    def retrieve(self, query: str, k: int = 4) -> dict:
        words = tokens(query)
        if not words:
            return {"lessons": [], "episodes": []}
        query_vector = self.embedder.embed(query)
        return {"lessons": self._rank("lesson", "agent_lessons", "text", "status='active'", query_vector, words, k),
                "episodes": self._rank("episode", "agent_episodes", "summary", "outcome='completed'", query_vector, words, min(k, 3))}

    def _rank(self, kind: str, table: str, text_column: str, where: str, query_vector, words, k: int) -> list[dict]:
        keyword_hits = {ref: index for index, ref in enumerate(self.store.search(kind, words))}
        rows = self.store.db.query(f"SELECT id,{text_column} AS text,vector,created_at FROM {table} WHERE {where} ORDER BY created_at DESC LIMIT 1000")
        scored = []
        for position, row in enumerate(rows):
            vector = _load(row["vector"])
            cosine = float(query_vector @ vector) if vector is not None else 0.0
            keyword = row["id"] in keyword_hits
            if cosine < RELEVANCE_FLOOR and not (keyword and cosine >= 0.05):
                continue                                   # irrelevant: recency must never rescue it
            lexical = 1.0 - keyword_hits[row["id"]] / max(len(keyword_hits), 1) if keyword else 0.0
            score = 0.65 * cosine + 0.35 * lexical + 0.01 * (1 - position / max(len(rows), 1))
            scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        chosen = [{"id": r["id"], "text": r["text"], "score": round(s, 3)} for s, r in scored[:k]]
        if chosen:
            marks = ",".join("?" * len(chosen))
            self.store.db.execute(f"UPDATE {table} SET uses=uses+1 WHERE id IN ({marks})", tuple(c["id"] for c in chosen))
        return chosen

    # -- consolidation -----------------------------------------------------------------------------------------------
    def consolidate(self, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        merged = expired = trimmed = 0
        lessons = self.store.db.query("SELECT id,text,vector,uses,status FROM agent_lessons WHERE status='active' ORDER BY uses DESC, created_at ASC")
        kept: list[tuple[str, np.ndarray]] = []
        for row in lessons:
            vector = _load(row["vector"])
            if vector is None:
                continue
            twin = next((kid for kid, kv in kept if float(vector @ kv) >= CONSOLIDATE_SIMILARITY), None)
            if twin:
                self.store.db.execute("UPDATE agent_lessons SET uses=uses+? WHERE id=?", (row["uses"], twin))
                self.forget_lesson(row["id"]); merged += 1
            else:
                kept.append((row["id"], vector))
        cutoff = (now - timedelta(days=30)).isoformat()
        for row in self.store.db.query("SELECT id FROM agent_lessons WHERE status='pending' AND created_at<?", (cutoff,)):
            self.decide_lesson(row["id"], False); expired += 1
        extra = self.store.db.query("SELECT id FROM agent_episodes WHERE uses=0 ORDER BY created_at DESC LIMIT -1 OFFSET ?", (EPISODE_CAP,))
        for row in extra:
            self.store.unindex("episode", row["id"]); self.store.db.execute("DELETE FROM agent_episodes WHERE id=?", (row["id"],)); trimmed += 1
        return {"merged_lessons": merged, "expired_pending": expired, "trimmed_episodes": trimmed}
