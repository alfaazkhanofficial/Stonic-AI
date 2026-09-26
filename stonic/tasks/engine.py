import asyncio
import json
from uuid import uuid4
from stonic.core.models import PermissionLevel, utc_now
from stonic.tasks.contracts import Decision


class TaskEngine:
    """Durable sequential plans. Restart never silently repeats a side effect."""
    def __init__(self, db, tools, events):
        self.db, self.tools, self.events = db, tools, events
        self.lock = asyncio.Lock()
        self.running: dict[str, asyncio.Task] = {}
        for row in self.db.query("SELECT payload FROM jobs WHERE status IN ('running','waiting_approval','queued')"):
            job = json.loads(row["payload"])
            if job["status"] in {"running", "waiting_approval", "queued"}:
                job["status"] = "paused"
                job["approval"] = None
                for step in job["steps"]:
                    if step["status"] in {"running", "waiting_approval"}:
                        step["status"] = "uncertain" if step["status"] == "running" else "pending"
                self.save(job)

    def list(self):
        return [json.loads(row["payload"]) for row in self.db.query("SELECT payload FROM jobs ORDER BY created_at DESC LIMIT 100")]

    def get(self, identifier):
        rows = self.db.query("SELECT payload FROM jobs WHERE id=?", (identifier,))
        if not rows:
            raise ValueError("Task does not exist")
        return json.loads(rows[0]["payload"])

    def save(self, job):
        job["updated_at"] = utc_now()
        self.db.execute("""INSERT INTO jobs VALUES(?,?,?,?,?,?,?) ON CONFLICT(id)
            DO UPDATE SET status=excluded.status,payload=excluded.payload,updated_at=excluded.updated_at""",
            (job["id"], job["session_id"], job["goal"], job["status"], json.dumps(job), job["created_at"], job["updated_at"]))

    def create(self, decision: Decision, session: str, max_steps=8):
        if decision.kind != "plan" or len(decision.steps) > max_steps:
            raise ValueError("Plan exceeds configured action limit")
        for step in decision.steps:
            if step.tool not in self.tools.tools:
                raise ValueError("Plan requests an unavailable tool")
        job = {"id": str(uuid4()), "session_id": session, "goal": decision.message,
               "status": "queued", "created_at": utc_now(), "approval": None,
               "steps": [{**s.model_dump(), "status": "pending", "result": None, "attempts": 0} for s in decision.steps]}
        self.save(job)
        return job

    @staticmethod
    def _follow(result, key):
        """One step of an output path: a key, a list index, or a selector.

        A selector is an object such as {"name": "Search", "tag": "button"}: it picks the FIRST item of a list of
        objects whose fields all match. Add "index" (0-based) to pick the Nth match instead of the first, e.g.
        {"tag": "a", "index": 0} for "the first link" when nothing about it can be named in advance. A plan can then
        act on "the Search button" or "the first result" from a page nobody has seen yet, instead of guessing where
        it will sit in a list. Text matches ignore case; every listed field must match; no match is an error.
        """
        if isinstance(key, dict):
            if not isinstance(result, list):
                raise ValueError("A selector needs a list to select from")
            fields = {k: v for k, v in key.items() if k != "index"}
            if not 0 <= len(fields) <= 6:
                raise ValueError("A selector needs between zero and six matching fields")
            index = key.get("index", 0)
            if not isinstance(index, int) or isinstance(index, bool) or index < 0:
                raise ValueError("A selector's index must be a non-negative whole number")
            def same(a, b):
                return a.casefold() == b.casefold() if isinstance(a, str) and isinstance(b, str) else a == b
            matches = [item for item in result if isinstance(item, dict) and all(k in item and same(item[k], v) for k, v in fields.items())]
            if index >= len(matches):
                raise ValueError(f"Only {len(matches)} item(s) match the selector; index {index} does not exist")
            return matches[index]
        if isinstance(result, list) and isinstance(key, str) and key.lstrip("-").isdigit():
            key = int(key)
        return result[key]

    def resolve(self, value, job, dependencies):
        if isinstance(value, dict):
            if "$step" in value:
                if set(value) != {"$step", "path"} or value["$step"] not in dependencies:
                    raise ValueError("Output reference must name a declared dependency")
                step = next(s for s in job["steps"] if s["id"] == value["$step"])
                if step["status"] != "completed":
                    raise ValueError("Dependency has no completed result")
                result = step["result"]
                for key in value["path"]:
                    result = self._follow(result, key)
                return result
            return {k: self.resolve(v, job, dependencies) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve(v, job, dependencies) for v in value]
        return value

    async def run(self, identifier, grant=None):
        if identifier in self.running:
            raise ValueError("Task is already running")
        async with self.lock:
            job = self.get(identifier)
            if job["status"] in {"completed", "cancelled", "failed"}:
                return job
            if any(s["status"] == "uncertain" for s in job["steps"]):
                raise ValueError("An interrupted action has an uncertain outcome. Inspect it before creating a new plan.")
            self.running[identifier] = asyncio.current_task()
            job["status"] = "running"
            try:
                for step in job["steps"]:
                    await asyncio.sleep(0)
                    if step["status"] == "completed":
                        continue
                    tool = self.tools.tools.get(step["tool"])
                    if tool is None:
                        raise ValueError("A required tool is unavailable")
                    try:
                        arguments = self.resolve(json.loads(step["arguments_json"]), job, step["depends_on"])
                        model = tool.arguments.model_validate(arguments)
                    except (ValueError, KeyError, IndexError, TypeError):
                        # A step that needs values nobody could know when the plan was written (a page's control
                        # refs, a URL after redirects) cannot be filled in from the plan alone. If earlier steps
                        # already produced evidence, the service may plan again from what was observed.
                        if any(s["status"] == "completed" for s in job["steps"]):
                            job["replannable"] = True
                            job["unresolved_step"] = step["id"]
                        raise
                    if tool.prepare:
                        model = tool.prepare(model)
                    validated = model.model_dump(mode="json")
                    step["resolved_arguments"] = validated
                    if tool.level >= PermissionLevel.SENSITIVE and not grant:
                        if job.get("approval"):
                            self.tools.permissions.pending.pop(job["approval"]["id"],None)
                        request = self.tools.permissions.request(tool.name, tool.level, step["title"], validated)
                        job["approval"] = {**request.model_dump(), "arguments": validated, "step_id": step["id"]}
                        step["status"] = "waiting_approval"
                        job["status"] = "waiting_approval"
                        self.save(job)
                        self.events.publish("tasks", "A task is waiting for approval of its exact action and inputs.")
                        self.events.emit("panel",{"panel":"activity"})
                        return job
                    step["status"] = "running"
                    step["attempts"] += 1
                    job["approval"] = None
                    self.save(job)
                    result = await self.tools.invoke(tool.name, validated, grant)
                    grant = None
                    # Only explicitly retry-safe reads can repeat automatically.
                    if not result.success and result.retryable and tool.retry_safe and tool.level < PermissionLevel.SENSITIVE:
                        step["attempts"] += 1
                        result = await self.tools.invoke(tool.name, validated)
                    step["result"] = result.model_dump(mode="json")
                    step["status"] = "completed" if result.success else "failed"
                    if not result.success:
                        job["status"] = "failed"
                        self.save(job)
                        self.events.publish("tasks", "A task action failed; dependent steps were stopped.", "warning")
                        return job
                    self.save(job)
                job["status"] = "completed"
                self.events.publish("tasks", "All task actions completed with verification evidence.")
            except asyncio.CancelledError:
                job["status"] = "cancelled"
                for step in job["steps"]:
                    if step["status"] == "running":
                        step["status"] = "uncertain"
                self.events.publish("tasks", "Task cancelled. Any interrupted external action requires inspection.", "warning")
                raise
            except (ValueError, KeyError, IndexError, TypeError):
                job["status"] = "failed"
                job["error"] = "Plan inputs or dependency outputs could not be validated. No further steps ran."
            finally:
                self.save(job)
                self.running.pop(identifier, None)
            return job

    async def decide(self, identifier, approval_id, approved):
        job = self.get(identifier)
        if job["status"] != "waiting_approval" or not job["approval"] or job["approval"]["id"] != approval_id:
            raise ValueError("This approval is no longer current")
        self.tools.permissions.decide(approval_id, approved)
        if not approved:
            job["status"] = "cancelled"
            job["approval"] = None
            self.save(job)
            self.events.publish("security", "User denied a pending task action.")
            return job
        self.events.publish("security", "User approved a single task action with bound inputs.")
        return await self.run(identifier, approval_id)

    def cancel(self, identifier):
        job = self.get(identifier)
        if identifier in self.running:
            self.running[identifier].cancel()
        elif job["status"] not in {"completed", "failed", "cancelled"}:
            if job.get("approval"):
                self.tools.permissions.pending.pop(job["approval"]["id"], None)
            job["approval"] = None
            job["status"] = "cancelled"
            self.save(job)
        return self.get(identifier)
