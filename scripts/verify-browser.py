"""Exercise STONIC's real owned-browser adapter against a public acceptance form.

The production browser intentionally blocks loopback/private network targets, so this
acceptance check uses httpbin's public form instead of a local HTTP server.
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["STONIC_BROWSER_HEADLESS"] = "1"

from stonic.tools.browser import BrowserTools, BrowserOpen, BrowserRef, BrowserFill


async def main():
    browser = BrowserTools()
    url = "https://httpbin.org/forms/post"
    try:
        result = await browser.open(BrowserOpen(url=url))
        assert result.success, result.message
        opened_url = result.data.get("url", "")
        assert opened_url.startswith("https://httpbin.org/"), opened_url

        elements = result.data["elements"]
        input_ref = next(
            e["ref"] for e in elements
            if e.get("tag") == "input" and e.get("type") in {None, "text"}
        )
        submit_ref = next(
            e["ref"] for e in elements
            if e.get("tag") == "button" or e.get("type") == "submit"
        )

        result = await browser.fill(
            BrowserFill(ref=input_ref, expected_url=url, text="Stonic 7319")
        )
        assert result.success, result.message

        # The old inspection is now stale because fill re-inspected the page.
        # The production adapter deliberately raises on rejected browser actions;
        # the verifier must treat this expected rejection as a PASS, not as an
        # unhandled test error.
        try:
            await browser.click(BrowserRef(ref=submit_ref, expected_url=url))
        except ValueError as exc:
            assert "stale" in str(exc).lower(), str(exc)
        else:
            raise AssertionError("Expected stale browser reference to be rejected")

        result = await browser.snapshot(None)
        assert result.success, result.message
        fresh_submit = next(
            e["ref"] for e in result.data["elements"]
            if e.get("tag") == "button" or e.get("type") == "submit"
        )

        result = await browser.click(BrowserRef(ref=fresh_submit, expected_url=url))
        assert result.success, result.message
        assert result.data["url"].startswith("https://httpbin.org/")

        print(
            "PASS: real browser open, inspection, field fill, click, post-action "
            "verification and stale-reference rejection.",
            flush=True,
        )
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
