"""A web task can only be finished by observing pages: refs like s2e5 do not exist until the page has been read.

Regression: "open YouTube, search for Python tutorials and play the first result" was planned in ONE shot, so the fill
step held a ref nobody could know yet; it could not be validated and the whole task died after opening YouTube.
Now such a plan is re-planned from the observed evidence, and the planner is told to use exact observed refs."""
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from stonic.app.api import create_app
from stonic.core.models import Activity, ChatInput
from stonic.tasks.contracts import Decision
from stonic.providers.llm import OpenAICompatibleProvider
from stonic.tools.workspace import success

TOKEN = "browser-test-token"


class FakeBrowser:
    """Behaves like the owned browser: every read re-numbers the refs, and acting on a stale ref or URL fails."""

    def __init__(self):
        self.page = "home"
        self.n = 0
        self.query = ""
        self.log = []

    URLS = {"home": "https://www.youtube.com/", "results": "https://www.youtube.com/results?search_query=python+tutorials",
            "watch": "https://www.youtube.com/watch?v=abc123"}

    def observe(self):
        self.n += 1
        names = {"home": ["Guide", "Skip navigation", "Search", "Search", "Sign in"],
                 "results": ["Guide", "Search", "Search", "Python Full Course for Beginners", "Learn Python in 1 Hour"],
                 "watch": ["Guide", "Search", "Play"]}[self.page]
        elements = [{"ref": f"s{self.n}e{i + 1}", "tag": "button", "role": "combobox" if (i == 2 and self.page != "watch") else None, "name": name}
                    for i, name in enumerate(names)]
        return {"url": self.URLS[self.page], "title": "YouTube", "text": self.page, "elements": elements}

    def check(self, args):
        if args.expected_url != self.URLS[self.page]:
            raise ValueError("The page changed since it was inspected")
        if not args.ref.startswith(f"s{self.n}e"):
            raise ValueError("That control belongs to an older page reading")
        return int(args.ref.split("e")[1]) - 1

    async def open(self, args):
        self.log.append(("open", args.url))
        self.page = "home"
        return success("Public web page opened in the owned browser.", self.observe(), "re-read")

    async def snapshot(self, _):
        self.log.append(("snapshot",))
        return success("Owned browser page inspected.", self.observe(), "read")

    async def fill(self, args):
        index = self.check(args)
        assert index == 2, f"filled the wrong control {index}"
        self.query = args.text
        self.log.append(("fill", args.text))
        return success("Browser field updated.", self.observe(), "re-read")

    async def click(self, args):
        index = self.check(args)
        if self.page == "home" and index == 3:
            assert self.query == "Python tutorials", "searched before typing the query"
            self.page = "results"
        elif self.page == "results" and index == 3:
            self.page = "watch"
        else:
            raise ValueError(f"Clicked something that does nothing (control {index} on {self.page})")
        self.log.append(("click", self.page))
        return success("Browser control completed.", self.observe(), "re-read")


def step(identifier, tool, arguments, depends=()):
    return {"id": identifier, "title": identifier.replace("_", " "), "tool": tool, "arguments_json": json.dumps(arguments), "depends_on": list(depends)}


def observed(messages):
    """What a planner reads: the newest observation in the evidence it was handed."""
    packet = json.loads(messages[-1]["content"].split("\n", 1)[1])
    seen = [s["result"]["data"] for s in packet["evidence"] if s.get("result") and (s["result"].get("data") or {}).get("elements")]
    return seen[-1], packet


def find(data, name, nth=0):
    return [e for e in data["elements"] if e["name"] == name][nth]["ref"]


class Planner:
    """Scripted like a model that plans the way the failing one did in stage 1, then behaves once shown evidence."""

    def __init__(self, first_plan):
        self.first_plan = first_plan
        self.calls = []

    def available(self, _): return True
    async def complete(self, settings, messages): return "summary"

    async def decide(self, settings, messages, tools, context):
        self.calls.append((messages, context))
        if len(self.calls) == 1:
            return Decision(kind="plan", message="Open YouTube, search and play", steps=self.first_plan)
        data, packet = observed(messages)
        if data["url"] == FakeBrowser.URLS["home"] and not self.browser.query:
            return Decision(kind="plan", message="Type the query", steps=[step("type_query", "browser.fill", {"ref": find(data, "Search", 0) if False else data["elements"][2]["ref"], "expected_url": data["url"], "text": "Python tutorials"})])
        if data["url"] == FakeBrowser.URLS["home"]:
            return Decision(kind="plan", message="Submit", steps=[step("submit", "browser.click", {"ref": data["elements"][3]["ref"], "expected_url": data["url"]})])
        if data["url"] == FakeBrowser.URLS["results"]:
            return Decision(kind="plan", message="Play first", steps=[step("play_first", "browser.click", {"ref": data["elements"][3]["ref"], "expected_url": data["url"]})])
        return Decision(kind="answer", message="Playing the first Python tutorial.", steps=[])


BAD_PLAN = [
    step("open_youtube", "browser.open", {"url": "https://www.youtube.com/"}),
    step("inspect_page", "browser.snapshot", {}, ["open_youtube"]),
    step("fill_search", "browser.fill", {"ref": "SEARCH_BOX_REF", "expected_url": "https://www.youtube.com/", "text": "Python tutorials"}, ["inspect_page"]),
    step("submit_search", "browser.click", {"ref": "SEARCH_BUTTON_REF", "expected_url": "https://www.youtube.com/"}, ["fill_search"]),
]


@pytest.fixture
def rig(tmp_path):
    with TestClient(create_app(tmp_path, TOKEN), headers={"X-Stonic-Token": TOKEN}) as client:
        core = client.app.state.core
        core.state.transition(Activity.IDLE)
        browser = FakeBrowser()
        for name in ("open", "snapshot", "fill", "click"):
            tool = core.tools.tools[f"browser.{name}"]
            core.tools.tools[tool.name] = replace(tool, run=getattr(browser, name))
        planner = Planner(BAD_PLAN)
        planner.browser = browser
        core.provider = planner
        yield core, browser, planner


async def test_the_youtube_task_now_completes_by_planning_from_what_was_observed(rig):
    core, browser, planner = rig
    message = await core.chat(ChatInput(content="Open YouTube, search for Python tutorials, and play the first result.", session_id="main"))
    assert browser.page == "watch"
    assert [e[0] for e in browser.log] == ["open", "snapshot", "fill", "click", "click"]
    assert browser.query == "Python tutorials"
    assert message["content"] == "Playing the first Python tutorial."


async def test_the_planner_is_told_why_it_is_being_asked_again_and_to_use_observed_refs(rig):
    core, browser, planner = rig
    await core.chat(ChatInput(content="Open YouTube, search for Python tutorials, and play the first result.", session_id="main"))
    second_messages, second_context = planner.calls[1]
    text = second_messages[-1]["content"]
    assert "could not run because its inputs" in text and "fill_search" in text and "placeholder" in text
    _, packet = observed(second_messages)
    statuses = {s["tool"]: s["status"] for s in packet["evidence"]}
    assert statuses["browser.open"] == "completed" and statuses["browser.fill"] in {"pending", "failed"}
    assert second_context["stage"] == 2


async def test_a_plan_that_fails_before_anything_was_observed_is_not_replanned(rig):
    core, browser, planner = rig
    planner.first_plan = [step("fill_first", "browser.fill", {"ref": "NOT_A_REF", "expected_url": "https://www.youtube.com/", "text": "x"})]
    message = await core.chat(ChatInput(content="Open YouTube, search for Python tutorials, and play the first result.", session_id="main"))
    assert len(planner.calls) == 1 and browser.log == []           # no evidence, no second attempt, no loop
    assert "could not be validated" in message["content"] or "Completed actions" in message["content"] or message["content"]


async def test_a_planner_that_keeps_guessing_is_stopped_after_two_replans(rig):
    core, browser, planner = rig

    async def stubborn(settings, messages, tools, context):
        planner.calls.append((messages, context))
        return Decision(kind="plan", message="again", steps=BAD_PLAN if len(planner.calls) == 1 else [
            step("still_guessing", "browser.fill", {"ref": "GUESS", "expected_url": "https://www.youtube.com/", "text": "x"}),
        ])
    planner.decide = stubborn
    await core.chat(ChatInput(content="Open YouTube, search for Python tutorials, and play the first result.", session_id="main"))
    assert len(planner.calls) <= 3                                   # first plan + at most two replans


async def test_stale_page_refs_are_still_rejected_so_the_safety_binding_is_intact(rig):
    core, browser, planner = rig
    await browser.open(type("A", (), {"url": "https://www.youtube.com/"}))
    stale = browser.observe()["elements"][2]["ref"]
    browser.observe()                                               # the page was read again: old refs are void
    args = type("A", (), {"ref": stale, "expected_url": FakeBrowser.URLS["home"]})
    with pytest.raises(ValueError, match="older page reading"):
        browser.check(args)


def test_the_planner_instructions_teach_the_ref_rule():
    import inspect
    source = inspect.getsource(OpenAICompatibleProvider.decide)
    assert "never guess" in source and "index" in source and "selector" in source
