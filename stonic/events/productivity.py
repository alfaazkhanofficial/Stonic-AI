"""Local daily briefing and an explicit, portable calendar handoff."""
import json
from datetime import datetime, timedelta, timezone
from stonic.core.models import Contract, PermissionLevel, utc_now
from stonic.tools.registry import Tool
from stonic.tools.workspace import success


class Empty(Contract):
    pass


def calendar_text(value):
    return str(value).replace("\\", "\\\\").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def fold_line(value):
    """RFC 5545: 75 octets, with no split inside a UTF-8 code point."""
    lines, current, length = [], "", 0
    for character in value:
        size = len(character.encode("utf-8"))
        if length + size > 75:
            lines.append(current)
            current, length = " ", 1
        current += character
        length += size
    return "\r\n".join([*lines, current])


class Productivity:
    def __init__(self, db):
        self.db = db
        db.execute("CREATE TABLE IF NOT EXISTS briefings (day TEXT PRIMARY KEY, payload TEXT NOT NULL, generated_at TEXT NOT NULL, viewed_at TEXT)")

    def briefing(self, _=None, now=None):
        now = now or datetime.now().astimezone()
        end = now + timedelta(hours=24)
        reminders = [r for r in self.db.query("SELECT * FROM schedules WHERE status='active' ORDER BY due_at LIMIT 200")
                     if datetime.fromisoformat(r["due_at"]) <= end]
        tasks = [r for r in self.db.records("tasks") if r["status"] == "open"]
        unread = self.db.query("SELECT COUNT(*) AS count FROM notifications WHERE read=0")[0]["count"]
        data = {"day":now.date().isoformat(), "timezone":str(now.tzinfo), "window_end":end.isoformat(),
                "reminders":reminders, "open_tasks":[{"id":r["id"],"title":r["title"]} for r in tasks[:30]],
                "open_task_count":len(tasks), "unread_notices":unread,
                "calendar":{"mode":"export", "detail":"Export active reminders as an iCalendar file to import into your calendar. External calendars are not read or synchronized."}}
        self.db.execute("INSERT INTO briefings VALUES(?,?,?,NULL) ON CONFLICT(day) DO UPDATE SET payload=excluded.payload,generated_at=excluded.generated_at",
                        (data["day"],json.dumps(data),utc_now()))
        data["viewed_at"] = self.db.query("SELECT viewed_at FROM briefings WHERE day=?",(data["day"],))[0]["viewed_at"]
        return success("Daily briefing refreshed from local records.",data,"Current reminder, task and notification rows read from SQLite")

    def viewed(self):
        day = datetime.now().astimezone().date().isoformat()
        self.db.execute("UPDATE briefings SET viewed_at=? WHERE day=?",(utc_now(),day))

    def calendar(self):
        lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Stonic//Local Reminders//EN","CALSCALE:GREGORIAN"]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for row in self.db.query("SELECT * FROM schedules WHERE status='active' ORDER BY due_at LIMIT 200"):
            due = datetime.fromisoformat(row["due_at"]).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            lines.extend(["BEGIN:VEVENT",f"UID:{row['id']}@stonic.local",f"DTSTAMP:{stamp}",f"DTSTART:{due}",
                          "SUMMARY:"+calendar_text(row["title"]),"DESCRIPTION:Exported Stonic reminder. Changes are not synchronized."])
            if row["interval_seconds"]:
                lines.append(f"RRULE:FREQ=SECONDLY;INTERVAL={row['interval_seconds']}")
            lines.append("END:VEVENT")
        return "\r\n".join(fold_line(line) for line in [*lines,"END:VCALENDAR"]) + "\r\n"

    def register(self, registry):
        registry.register(Tool("productivity.briefing","Read today's local briefing: next 24 hours of reminders, open tasks and unread notices",Empty,PermissionLevel.SAFE,self.briefing,True))
