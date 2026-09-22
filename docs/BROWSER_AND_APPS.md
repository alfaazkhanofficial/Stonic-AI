# Browser control and application launching

## Multi-step browser plans

A plan can now chain several `browser.*` steps in one shot and act on a page it has not seen yet, using an
output-path selector instead of a guessed control ID:

    {"$step": "open", "path": ["data", "elements", {"name": "Search", "tag": "input"}, "ref"]}

This picks the first element of the referenced step's result whose listed fields all match. Add `"index"`
(0-based) to pick the Nth match, e.g. `{"tag": "a", "index": 0}` for "the first result" when nothing about
it can be named in advance:

    {"$step": "submit", "path": ["data", "elements", {"tag": "a", "index": 0}, "ref"]}

Regression example this fixes: "open YouTube, search for Python tutorials, and play the first result" can
now be written as one plan (open → fill the search box → click Search → click the first result link) using
selectors for every ref and every `expected_url`, instead of failing at the fill step because the search
box's ID could not be known until the page was read.

When even the field to select on cannot be named ahead of time, the plan still runs only the steps it can,
and STONIC automatically continues from what was observed (see "replanning" below), up to two extra rounds
per task.

## Owned-browser reliability

`scripts/browser-worker.mjs` (the Playwright-driven browser STONIC owns) now tolerates a page that is still
settling right after a click, fill or navigation:

* it waits briefly for the page to finish loading before reading it,
* an element that disappears while the page is being read (common right after a search submits or a link is
  clicked) is skipped rather than failing the whole read,
* a read is retried once if the page's context was replaced mid-read (a full navigation racing the read).

Regression example this fixes: clicking YouTube's Search button navigated the page; reading it immediately
afterward, while it was still re-rendering, could fail the whole action even though the click itself worked.

Safety is unchanged: acting on a stale control (from an older page reading) or a page other than the one a
step expects still fails with a clear reason.

## Replanning from what was observed

When a step's inputs cannot be resolved at all (a selector was not or could not be used, and the target
still cannot be known), the task fails, but if earlier steps already completed, STONIC asks the planner
again with what was actually observed instead of just giving up. This runs at most twice per task, and
never when nothing has been observed yet (so a plan that is broken from the very first step still fails
immediately rather than looping).

## Launching applications

`computer.launch` now recognizes common ways of naming an application, not just its exact executable name:

* Known shortcuts match by meaning, not exact wording: "chrome", "Google Chrome" and "chrome browser" all
  resolve to Chrome; "edge", "Microsoft Edge" and "msedge" all resolve to Edge. (Also: notepad, calculator,
  explorer/file explorer.)
* Anything else is matched against `computer.applications`' registered names: an exact name still works,
  and a descriptive name whose meaningful words are fully contained in the request also resolves uniquely
  (e.g. "Visual Studio Code" → the registered `Code.exe`).
* An unresolved name gives a specific reason and, where possible, the closest registered names, instead of
  a generic "unknown or ambiguous" dead end.

Regression example this fixes: "Launch Google Chrome" and "Launch Microsoft Edge" failed outright, because
the tool only accepted the bare words "chrome"/"edge" or an exact registry name, and a model naturally
writes the product's full name.

## Failure detail

Any tool failure now carries the real reason in `result.data.detail` when the tool raised it on purpose
(a `ValueError`, an `OSError`, or a timeout) — visible in Task activity's diagnostics and available to a
replanning attempt. Unexpected internal errors still surface only as a bare error type, never their raw
text, since that text was never written to be shown to a user.
