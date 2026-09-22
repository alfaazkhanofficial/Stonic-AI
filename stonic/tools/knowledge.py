import re
from typing import Literal
from uuid import uuid4
from pydantic import Field
from stonic.core.models import Contract, PermissionLevel as Level, utc_now
from stonic.tools.registry import Tool
from stonic.tools.workspace import success


class RecordSearch(Contract):
    kind: Literal["notes", "tasks", "memory"]
    query: str = Field(default="", max_length=500)


class RecordSave(Contract):
    kind: Literal["notes", "tasks", "memory"]
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(default="", max_length=20000)
    memory_type: Literal["user", "conversation", "task", "environment"] = "user"
    confirm_memory: bool = False


class RecordEdit(RecordSave):
    id: str
    status: Literal["open", "done"] = "open"


class RecordRemove(Contract):
    kind: Literal["notes", "tasks", "memory"]
    id: str


class PreferenceSave(Contract):
    category: Literal["communication", "applications", "workflow", "gaming"]
    value: str = Field(min_length=1, max_length=1000)


class Knowledge:
    def __init__(self, db, config):
        self.db, self.config = db, config

    def relevant(self, text, limit=5):
        if not self.config.values.memory_enabled:
            return []
        words = [w for w in re.findall(r"\w+", text, re.UNICODE) if len(w) > 2][:16]
        if not words:
            return []
        expression = " OR ".join('"' + w.replace('"', '""') + '"' for w in words)
        rows = self.db.query("SELECT id,title,content FROM memory_index WHERE memory_index MATCH ? ORDER BY rank LIMIT ?", (expression, limit))
        return [{**row, "content": row["content"][:1500]} for row in rows]

    def search(self, args):
        records = self.db.records(args.kind)
        words = args.query.casefold().split()
        matches = [r for r in records if all(w in (r["title"] + " " + r["content"]).casefold() for w in words)][:40]
        return success("Local records searched.", {"records": matches}, "Read matching records from SQLite")

    def save(self, args):
        if not args.title.strip():raise ValueError("Title cannot be blank")
        if args.kind == "memory" and not args.confirm_memory:raise ValueError("Explicitly confirm this memory before saving it")
        record = self.db.create_record(args.kind, args.title, args.content)
        if args.kind == "memory":
            self.db.classify_memory(record["id"],args.memory_type)
        return success("Local record saved.", {"record": record}, "Record read back after committed insert")

    def edit(self, args):
        if args.kind == "memory" and not args.confirm_memory:raise ValueError("Explicitly confirm this memory before changing it")
        record = self.db.update_record(args.kind, args.id, {"title": args.title, "content": args.content, "status": args.status})
        if not record:
            raise ValueError("Record does not exist")
        if args.kind == "memory":
            self.db.classify_memory(record["id"],args.memory_type)
        return success("Local record updated.", {"record": record}, "Updated record read back from SQLite")

    def remove(self, args):
        if self.db.execute("DELETE FROM records WHERE kind=? AND id=?", (args.kind, args.id)) != 1:
            raise ValueError("Record does not exist")
        return success("Local record forgotten.", {"id": args.id}, "Exactly one record deleted; memory index updated by transaction trigger")

    def preference(self, args):
        identifier = str(uuid4())
        self.db.execute("INSERT INTO preferences VALUES(?,?,?,1,?)", (identifier, args.category, args.value, utc_now()))
        return success("Approved preference saved.", {"id": identifier}, "Preference committed with explicit approval")

    def preferences(self):
        return self.db.query("SELECT * FROM preferences ORDER BY created_at DESC LIMIT 100")

    def register(self, registry):
        registry.register(Tool("records.search", "Find local notes, tasks, or saved memories", RecordSearch, Level.SAFE, self.search, True))
        registry.register(Tool("records.create", "Save a note, todo, or explicitly requested memory", RecordSave, Level.NORMAL, self.save))
        registry.register(Tool("records.update", "Update an existing note, task, or memory identified by its record id", RecordEdit, Level.SENSITIVE, self.edit))
        registry.register(Tool("records.forget", "Permanently forget one identified local record", RecordRemove, Level.SENSITIVE, self.remove))
        registry.register(Tool("preferences.save", "Save a user-approved communication, application, workflow, or gaming preference. Never infer sensitive traits.", PreferenceSave, Level.SENSITIVE, self.preference))
