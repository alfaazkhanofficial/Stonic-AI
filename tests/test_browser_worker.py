"""The owned-browser worker, driven over its stdin/stdout protocol against a fake Playwright.

Regression: clicking YouTube's Search button navigates the page; the worker re-read the page immediately, while it was
still re-rendering, and one detached element (or a 30 s wait for it) failed the whole action even though the click worked.
Real Chromium is not available in CI, so the fake reproduces the parts of Playwright the worker relies on, including
elements that vanish while the page is being read."""
import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")

FAKE_PLAYWRIGHT = textwrap.dedent("""
    // A tiny stand-in for the Playwright API surface browser-worker.mjs uses.
    const scenario = JSON.parse(process.env.FAKE_SCENARIO);
    class Element {
      constructor(spec, page) { this.spec = spec; this.page = page; }
      get attached() { return !this.gone; }
      async isVisible() {
        const visible = this.attached && this.spec.visible !== false;
        if (this.spec.vanishesWhenRead) this.gone = true;       // visible when checked, gone an instant later (the page re-rendered)
        return visible;
      }
      async evaluate(fn) {
        if (!this.attached) throw new Error('Element is not attached to the DOM');
        const spec = this.spec;
        return fn({ tagName: spec.tag.toUpperCase(), innerText: spec.name, getAttribute: (k) => ({ role: spec.role ?? null, type: spec.type ?? null, 'aria-label': spec.label ?? null, placeholder: null, name: null })[k] ?? null });
      }
      async fill(text) { this.page.filled = text; this.page.change(); }
      async click() { this.page.clicked = this.spec.name; if (this.spec.navigatesTo) { this.page.location = this.spec.navigatesTo; this.page.change(); } }
    }
    class Locator {
      constructor(page, index) { this.page = page; this.index = index; }
      async count() { if (scenario.countThrows && this.page.reads > 0) throw new Error('Execution context was destroyed'); return this.page.elements().length; }
      nth(i) { return new Locator(this.page, i); }
      async isVisible() { const e = this.page.elements()[this.index]; return e ? e.isVisible() : false; }
      async evaluate(fn) {   // Locator.evaluate resolves the element first, waiting like Playwright does
        return (await this.elementHandle()).evaluate(fn);
      }
      async elementHandle(options) {
        const e = this.page.elements()[this.index];
        if (!e || !e.attached) {
          // Real Playwright waits for the element for `timeout` (30 s by default) and then throws.
          await new Promise(r => setTimeout(r, Math.min(options?.timeout ?? 30000, 30000)));
          throw new Error('Timeout waiting for element');
        }
        return e;
      }
    }
    class Page {
      constructor() { this.location = scenario.startUrl; this.reads = 0; this.filled = null; this.clicked = null; this.version = 0; }
      elements() {
        if (this.cacheKey !== this.location + this.version) { this.cacheKey = this.location + this.version; this.cache = (scenario.pages[this.location] || []).map(s => new Element(s, this)); }
        return this.cache;
      }

      change() { this.reads = 0; this.version++; }
      isClosed() { return false; }
      url() { return this.location; }
      async goto(url) { this.location = url; this.change(); }
      locator(sel) { return sel === 'body' ? { innerText: async () => 'body text' } : new Locator(this, -1); }
      async title() { if (scenario.titleThrows) throw new Error('navigating'); return 'Fake page'; }
      async evaluate() { this.reads++; return 'page text'; }
      async waitForLoadState() {}
      async waitForTimeout() {}
    }
    export const chromium = { launch: async () => ({ newContext: async () => ({ route: async () => {}, on: () => {}, newPage: async () => new Page() }), close: async () => {} }) };
""")


def run_worker(tmp_path, scenario, commands, timeout=20):
    (tmp_path / "node_modules" / "playwright").mkdir(parents=True, exist_ok=True)
    (tmp_path / "node_modules" / "playwright" / "package.json").write_text(json.dumps({"name": "playwright", "type": "module", "main": "index.js"}))
    (tmp_path / "node_modules" / "playwright" / "index.js").write_text(FAKE_PLAYWRIGHT)
    (tmp_path / "package.json").write_text(json.dumps({"type": "module"}))
    shutil.copy(ROOT / "scripts" / "browser-worker.mjs", tmp_path / "browser-worker.mjs")
    import os
    # Node needs more than PATH to start on Windows (e.g. SystemRoot), so extend the real
    # environment rather than replacing it; only FAKE_SCENARIO is specific to this test.
    env = {**os.environ, "FAKE_SCENARIO": json.dumps(scenario)}
    result = subprocess.run(["node", "browser-worker.mjs"], cwd=tmp_path, input="\n".join(json.dumps(c) for c in commands) + "\n",
                            capture_output=True, text=True, timeout=timeout, env=env)
    lines = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert lines, f"the worker produced no output (exit {result.returncode}); stderr:\n{result.stderr}"
    return lines


HOME = "https://93.184.216.34/"
RESULTS = "https://93.184.216.34/results"
PAGES = {
    HOME: [{"tag": "button", "name": "Guide"}, {"tag": "input", "name": "Search", "role": "combobox", "type": "text"},
           {"tag": "button", "name": "Search", "navigatesTo": RESULTS}],
    RESULTS: [{"tag": "a", "name": "Python Full Course"}, {"tag": "a", "name": "Learn Python in 1 Hour"}],
}


def test_snapshot_lists_visible_controls_with_refs_that_encode_the_reading(tmp_path):
    scenario = {"startUrl": HOME, "pages": PAGES}
    out = run_worker(tmp_path, scenario, [{"action": "open", "url": HOME}])
    data = out[0]["data"]
    assert out[0]["success"] and data["url"] == HOME and data["title"] == "Fake page"
    assert [e["name"] for e in data["elements"]] == ["Guide", "Search", "Search"]
    import re
    assert all(re.fullmatch(r"s\d+e\d+", e["ref"]) for e in data["elements"])


def test_a_control_that_vanishes_while_the_page_is_read_no_longer_fails_the_action(tmp_path):
    pages = {HOME: [{"tag": "button", "name": "Guide"}, {"tag": "input", "name": "Search", "role": "combobox", "type": "text"},
                    {"tag": "button", "name": "Suggestion", "vanishesWhenRead": True},      # visible, then re-rendered away mid-read
                    {"tag": "button", "name": "Search", "navigatesTo": RESULTS}],
             RESULTS: PAGES[RESULTS]}
    scenario = {"startUrl": HOME, "pages": pages}
    out = run_worker(tmp_path, scenario, [{"action": "open", "url": HOME}], timeout=15)
    assert out[0]["success"], out[0]["message"]                       # before the fix this waited 30 s+ and failed
    assert "Suggestion" not in [e["name"] for e in out[0]["data"]["elements"]]     # it is simply left out
    assert {"Guide", "Search"} <= {e["name"] for e in out[0]["data"]["elements"]}


def test_click_on_search_returns_the_new_page_and_its_fresh_refs(tmp_path):
    scenario = {"startUrl": HOME, "pages": PAGES}
    opened = run_worker(tmp_path, scenario, [{"action": "open", "url": HOME}])
    ref = [e["ref"] for e in opened[0]["data"]["elements"] if e["name"] == "Search"][-1]
    both = run_worker(tmp_path, scenario, [{"action": "open", "url": HOME}, {"action": "click", "ref": ref, "expected_url": HOME}])
    assert both[1]["success"], both[1]["message"]
    assert both[1]["data"]["url"] == RESULTS
    assert [e["name"] for e in both[1]["data"]["elements"]] == ["Python Full Course", "Learn Python in 1 Hour"]


def test_reading_a_page_in_the_middle_of_navigation_returns_what_it_can_instead_of_failing(tmp_path):
    scenario = {"startUrl": HOME, "pages": PAGES, "countThrows": True, "titleThrows": True}
    out = run_worker(tmp_path, scenario, [{"action": "open", "url": HOME}, {"action": "snapshot"}])
    assert out[1]["success"] and out[1]["data"]["title"] == "" and out[1]["data"]["elements"] == []


def test_the_safety_bindings_still_reject_wrong_pages_and_stale_refs(tmp_path):
    scenario = {"startUrl": HOME, "pages": PAGES}
    out = run_worker(tmp_path, scenario, [
        {"action": "open", "url": HOME},
        {"action": "click", "ref": "s1e2", "expected_url": "https://93.184.216.34/other"},
        {"action": "click", "ref": "s9e9", "expected_url": HOME}])
    assert not out[1]["success"] and "Page changed since inspection" in out[1]["message"]
    assert not out[2]["success"] and "stale" in out[2]["message"]
    private = run_worker(tmp_path, scenario, [{"action": "open", "url": "http://192.168.1.1/"}])
    assert not private[0]["success"] and "not allowed" in private[0]["message"].lower()
