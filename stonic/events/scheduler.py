import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from pydantic import Field, field_validator
from stonic.core.models import Contract, PermissionLevel as Level, utc_now
from stonic.tools.registry import Tool
from stonic.tools.workspace import success


class ReminderCreate(Contract):
    title: str = Field(min_length=1, max_length=200)
    due_at: datetime
    interval_seconds: int | None = Field(default=None, ge=60, le=31536000)

    @field_validator("due_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("A timezone offset is required")
        return value.astimezone(timezone.utc)


class TimerCreate(Contract):
    title: str = Field(default="Timer", min_length=1, max_length=200)
    seconds: int = Field(ge=1, le=604800)


class ReminderCancel(Contract):
    id: str


class Empty(Contract):
    pass


class Scheduler:
    def __init__(self, db, events, config, diagnostics, memory=None):
        self.memory = memory
        self.db, self.events, self.config, self.diagnostics = db, events, config, diagnostics
        self.worker = None
        self.triggers = None

    def start(self):
        self.worker = asyncio.create_task(self.loop())

    async def close(self):
        if self.worker:
            self.worker.cancel()
            try:
                await self.worker
            except asyncio.CancelledError:
                pass

    def create(self, args):
        now = datetime.now(timezone.utc)
        if args.due_at < now - timedelta(seconds=5):
            raise ValueError("Reminder time is in the past")
        identifier = str(uuid4())
        self.db.execute("INSERT INTO schedules VALUES(?,?,?,?,?,?,NULL)",
            (identifier, args.title, args.due_at.isoformat(), args.interval_seconds, "active", utc_now()))
        return success("Reminder scheduled.", {"id": identifier, "due_at": args.due_at.isoformat()}, "Schedule committed to SQLite")

    def timer(self, args):
        return self.create(ReminderCreate(title=args.title, due_at=datetime.now(timezone.utc) + timedelta(seconds=args.seconds)))

    def list(self, _=None):
        return success("Schedules loaded.", {"schedules": self.db.query("SELECT * FROM schedules ORDER BY due_at LIMIT 200")}, "Read persisted schedules")

    def cancel(self, args):
        if not self.db.execute("UPDATE schedules SET status='cancelled' WHERE id=? AND status='active'", (args.id,)):
            raise ValueError("No active reminder with this id")
        return success("Reminder cancelled.", {"id": args.id}, "Schedule status committed as cancelled")

    def notify(self, title, body, source, dedup):
        inserted = self.db.execute("INSERT OR IGNORE INTO notifications VALUES(?,?,?,?,?,0,?)",
            (str(uuid4()), title, body, source, utc_now(), dedup))
        if inserted:
            self.events.emit("notification", {"title":title, "body":body, "source":source,"quiet":self.quiet()})
        return inserted

    def tick(self, now=None):
        now = now or datetime.now(timezone.utc)
        for reminder in self.db.query("SELECT * FROM schedules WHERE status='active' AND due_at<=?", (now.isoformat(),)):
            # Due marker and notice share one transaction, so restart cannot lose or duplicate delivery.
            with self.db.lock, self.db.connection:
                self.db.connection.execute("INSERT OR IGNORE INTO notifications VALUES(?,?,?,?,?,0,?)",
                    (str(uuid4()), reminder["title"], "Your scheduled reminder is due.", "reminder", now.isoformat(),
                     f"reminder:{reminder['id']}:{reminder['due_at']}"))
                interval = reminder["interval_seconds"]
                if interval:
                    old = datetime.fromisoformat(reminder["due_at"])
                    missed = max(1, int((now - old).total_seconds() // interval) + 1)
                    due = old + timedelta(seconds=missed * interval)
                    self.db.connection.execute("UPDATE schedules SET due_at=?,last_fired=? WHERE id=?", (due.isoformat(), now.isoformat(), reminder["id"]))
                else:
                    self.db.connection.execute("UPDATE schedules SET status='completed',last_fired=? WHERE id=?", (now.isoformat(), reminder["id"]))
            self.events.publish("reminders", "A scheduled reminder was delivered.")
            self.events.emit("notification", {"title":reminder["title"], "body":"Your scheduled reminder is due.", "source":"reminder","quiet":self.quiet()})

    def quiet(self):
        values = self.config.values
        if values.gaming_mode:
            return True
        hour = datetime.now().hour
        return values.quiet_start != values.quiet_end and (values.quiet_start <= hour < values.quiet_end if values.quiet_start < values.quiet_end else hour >= values.quiet_start or hour < values.quiet_end)

    def proactive(self):
        values = self.config.values
        if not values.proactive_enabled:
            return
        if self.quiet():
            return
        metrics = self.diagnostics.metrics()
        bucket = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
        if metrics["disk_percent"] >= 92:
            self.notify("Disk space is running low", f"The system drive is {metrics['disk_percent']}% full.", "system", f"disk:{bucket}")
        if metrics["memory_percent"] >= 95:
            self.notify("Memory use is high", f"Memory use is {metrics['memory_percent']}%.", "system", f"memory:{bucket}")

    async def loop(self):
        count = 0
        while True:
            try:
                self.tick()
                if count % 30 == 0:
                    self.proactive()
                if self.triggers and count % 5 == 0:
                    self.triggers.tick()
                if self.memory and count % 7200 == 0:      # roughly every 4 hours at the 2s tick rate
                    report = self.memory.consolidate()
                    if any(report.values()):
                        self.events.publish("agent", f"Memory consolidated: {report}", "info")
                count += 1
            except Exception:
                self.events.publish("scheduler", "A scheduler cycle failed; it will retry on the next cycle.", "error")
            await asyncio.sleep(2)

    def register(self, registry):
        registry.register(Tool("reminders.create", "Schedule a persistent reminder with explicit timezone and optional recurring interval", ReminderCreate, Level.NORMAL, self.create))
        registry.register(Tool("timers.create", "Start a persistent timer for a duration in seconds", TimerCreate, Level.NORMAL, self.timer))
        registry.register(Tool("reminders.list", "List reminders, timers and their delivery status", Empty, Level.SAFE, self.list, True))
        registry.register(Tool("reminders.cancel", "Cancel one active reminder or timer", ReminderCancel, Level.NORMAL, self.cancel))
