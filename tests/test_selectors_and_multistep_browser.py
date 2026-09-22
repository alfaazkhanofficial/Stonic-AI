"""Output-path selectors ({"$step": id, "path": [...]}), including the "index" extension, and the multi-step
browser plan they now make possible: search-and-click-the-first-result in ONE plan, no replanning round trip."""
import json
from dataclasses import replace

import pytest

from stonic.config.settings import Configuration
from stonic.diagnostics.health import Diagnostics
from stonic.events.bus import EventBus
from stonic.security.permissions import PermissionGate
from stonic.storage.database import Database
from stonic.tasks.contracts import Decision
from stonic.tasks.engine import TaskEngine
from stonic.tools.registry import ToolRegistry, Tool
from stonic.core.models import Contract, PermissionLevel
from stonic.tools.workspace import success
from pydantic import Field


class Args(Contract):
    text: str = Field(default="")


@pytest.fixture
def runtime(tmp_path):
    db = Database(tmp_path / "test.db")
    registry = ToolRegistry(PermissionGate())
    engine = TaskEngine(db, registry, EventBus(db))
    yield db, registry, engine
    db.close()


def step(identifier, tool, args, deps=()):
    return {"id": identifier, "title": identifier, "tool": tool, "arguments_json": json.dumps(args), "depends_on": list(deps)}


def make_job(engine, *steps):
    return engine.create(Decision(kind="plan", message="test", steps=steps), "main")


PAGE = {"url": "https://x.example/", "elements": [
    {"ref": "a", "name": "Guide", "tag": "button"},
    {"ref": "b", "name": "Search", "tag": "input"},
    {"ref": "c", "name": "Search", "tag": "button"},
    {"ref": "d", "name": "Python Full Course", "tag": "a"},
    {"ref": "e", "name": "Learn Python in 1 Hour", "tag": "a"},
]}


def test_a_selector_picks_the_first_match_by_default(runtime):
    db, registry, engine = runtime
    registry.register(Tool("noop.read", "d", Contract, PermissionLevel.SAFE, lambda a: success("ok", PAGE, "d"), True, 5))
    registry.register(Tool("noop.take", "d", Args, PermissionLevel.SAFE, lambda a: success("ok", {"got": a.text}, "d"), True, 5))
    job = make_job(engine,
        step("read", "noop.read", {}),
        step("take", "noop.take", {"text": {"$step": "read", "path": ["data", "elements", {"tag": "a"}, "name"]}}, ["read"]))
    job = pytest.run(engine.run(job["id"])) if False else __import__("asyncio").run(engine.run(job["id"]))
    assert job["status"] == "completed"
    assert job["steps"][1]["result"]["data"] == {"got": "Python Full Course"}


def test_a_selector_with_index_picks_the_nth_match(runtime):
    db, registry, engine = runtime
    registry.register(Tool("noop.read", "d", Contract, PermissionLevel.SAFE, lambda a: success("ok", PAGE, "d"), True, 5))
    registry.register(Tool("noop.take", "d", Args, PermissionLevel.SAFE, lambda a: success("ok", {"got": a.text}, "d"), True, 5))
    job = make_job(engine,
        step("read", "noop.read", {}),
        step("take", "noop.take", {"text": {"$step": "read", "path": ["data", "elements", {"tag": "a", "index": 1}, "name"]}}, ["read"]))
    job = __import__("asyncio").run(engine.run(job["id"]))
    assert job["steps"][1]["result"]["data"] == {"got": "Learn Python in 1 Hour"}


def test_a_selector_index_beyond_the_matches_fails_the_plan_cleanly(runtime):
    db, registry, engine = runtime
    registry.register(Tool("noop.read", "d", Contract, PermissionLevel.SAFE, lambda a: success("ok", PAGE, "d"), True, 5))
    registry.register(Tool("noop.take", "d", Args, PermissionLevel.SAFE, lambda a: success("ok", {}, "d"), True, 5))
    job = make_job(engine,
        step("read", "noop.read", {}),
        step("take", "noop.take", {"text": {"$step": "read", "path": ["data", "elements", {"tag": "a", "index": 9}, "name"]}}, ["read"]))
    job = __import__("asyncio").run(engine.run(job["id"]))
    assert job["status"] == "failed" and "could not be validated" in job["error"]


def test_a_selector_with_no_filter_fields_just_picks_by_position(runtime):
    db, registry, engine = runtime
    registry.register(Tool("noop.read", "d", Contract, PermissionLevel.SAFE, lambda a: success("ok", PAGE, "d"), True, 5))
    registry.register(Tool("noop.take", "d", Args, PermissionLevel.SAFE, lambda a: success("ok", {"got": a.text}, "d"), True, 5))
    job = make_job(engine,
        step("read", "noop.read", {}),
        step("take", "noop.take", {"text": {"$step": "read", "path": ["data", "elements", {"index": 2}, "name"]}}, ["read"]))
    job = __import__("asyncio").run(engine.run(job["id"]))
    assert job["steps"][1]["result"]["data"] == {"got": "Search"}


@pytest.mark.parametrize("bad", [{"index": -1}, {"index": "0"}, {"index": True}, {f"f{i}": i for i in range(8)}])
def test_malformed_selectors_fail_the_plan_rather_than_crash_or_misbehave(runtime, bad):
    db, registry, engine = runtime
    registry.register(Tool("noop.read", "d", Contract, PermissionLevel.SAFE, lambda a: success("ok", PAGE, "d"), True, 5))
    registry.register(Tool("noop.take", "d", Args, PermissionLevel.SAFE, lambda a: success("ok", {}, "d"), True, 5))
    job = make_job(engine,
        step("read", "noop.read", {}),
        step("take", "noop.take", {"text": {"$step": "read", "path": ["data", "elements", bad, "name"]}}, ["read"]))
    job = __import__("asyncio").run(engine.run(job["id"]))
    assert job["status"] == "failed"


# ── the actual regression: search YouTube and click the first result, in ONE plan ──────────────────────────

class FakeBrowser:
    """The owned browser: every read re-numbers refs; acting on a stale ref or the wrong page fails, as real."""

    def __init__(self):
        self.page, self.n, self.query, self.log = "home", 0, "", []
    URLS = {"home": "https://www.youtube.com/", "results": "https://www.youtube.com/results?search_query=python+tutorials"}

    def observe(self):
        self.n += 1
        names = {"home": ["Guide", "Search", "Search"],
                  "results": ["Python Full Course for Beginners", "Learn Python in 1 Hour"]}[self.page]
        tags = {"home": ["button", "input", "button"], "results": ["a", "a"]}[self.page]
        return {"url": self.URLS[self.page], "elements": [{"ref": f"s{self.n}e{i}", "name": n, "tag": t} for i, (n, t) in enumerate(zip(names, tags))]}

    def check(self, args):
        if args.expected_url != self.URLS[self.page]:
            raise ValueError("Page changed since inspection")
        if not args.ref.startswith(f"s{self.n}e"):
            raise ValueError("That control is from a stale page reading")

    async def open(self, args):
        self.page = "home"
        self.log.append(("open",))
        return success("opened", self.observe(), "re-read")

    async def fill(self, args):
        self.check(args)
        self.query = args.text
        self.log.append(("fill", args.text))
        return success("filled", self.observe(), "re-read")

    async def click(self, args):
        self.check(args)
        if self.page == "home":
            assert self.query == "Python tutorials", "clicked search before typing the query"
            self.page = "results"
        else:
            self.page = "watch"
        self.log.append(("click", self.page))
        return success("clicked", self.observe() if self.page != "watch" else {"url": "https://www.youtube.com/watch?v=abc"}, "re-read")


@pytest.fixture
def browser_engine(tmp_path):
    from stonic.tools.browser import BrowserOpen, BrowserRef, BrowserFill
    db = Database(tmp_path / "test.db")
    registry = ToolRegistry(PermissionGate())
    browser = FakeBrowser()
    registry.register(Tool("browser.open", "d", BrowserOpen, PermissionLevel.NORMAL, browser.open, False, 35))
    registry.register(Tool("browser.fill", "d", BrowserFill, PermissionLevel.NORMAL, browser.fill, False, 35))
    registry.register(Tool("browser.click", "d", BrowserRef, PermissionLevel.NORMAL, browser.click, False, 35))
    engine = TaskEngine(db, registry, EventBus(db))
    yield engine, browser
    db.close()


def selector(step_id, name=None, tag=None, index=0):
    filt = {k: v for k, v in {"name": name, "tag": tag}.items() if v is not None}
    return {"$step": step_id, "path": ["data", "elements", {**filt, "index": index}, "ref"]}


def url_of(step_id):
    return {"$step": step_id, "path": ["data", "url"]}


async def _run(engine, job):
    return await engine.run(job["id"])


def test_search_and_click_the_first_result_completes_in_a_single_plan_no_replan_needed(browser_engine):
    import asyncio
    engine, browser = browser_engine
    plan = [
        step("open", "browser.open", {"url": "https://www.youtube.com/"}),
        step("type", "browser.fill", {"ref": selector("open", tag="input"), "expected_url": url_of("open"), "text": "Python tutorials"}, ["open"]),
        step("submit", "browser.click", {"ref": selector("type", name="Search", tag="button"), "expected_url": url_of("type")}, ["type"]),
        step("play_first", "browser.click", {"ref": selector("submit", tag="a", index=0), "expected_url": url_of("submit")}, ["submit"]),
    ]
    job = engine.create(Decision(kind="plan", message="Search and play", steps=plan), "main")
    job = asyncio.run(_run(engine, job))
    assert job["status"] == "completed"
    assert [e[0] for e in browser.log] == ["open", "fill", "click", "click"]
    assert browser.query == "Python tutorials" and browser.page == "watch"
    assert job["steps"][3]["result"]["data"]["url"].startswith("https://www.youtube.com/watch")


def test_the_stale_ref_safety_check_still_applies_inside_a_chained_plan(browser_engine):
    """A selector always resolves against the FRESH result of the step it points at, so it cannot itself go
    stale - but a hand-written plan that reuses an old page's ref directly (not via a selector) must still fail."""
    import asyncio
    engine, browser = browser_engine
    browser.n = 5   # simulate a ref left over from an earlier page reading, before this job even started
    plan = [
        step("open", "browser.open", {"url": "https://www.youtube.com/"}),
        step("bad_click", "browser.click", {"ref": "s1e2", "expected_url": url_of("open")}, ["open"]),  # a literal, pre-guessed ref
    ]
    job = engine.create(Decision(kind="plan", message="x", steps=plan), "main")
    job = asyncio.run(_run(engine, job))
    assert job["status"] == "failed"
    result = job["steps"][1]["result"]
    assert result["success"] is False and "stale" in result["data"]["detail"]
