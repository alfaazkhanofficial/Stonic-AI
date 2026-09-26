"""Check both halves of STONIC's web research from this PC.

    python scripts/websearch-check.py
    python scripts/websearch-check.py --data-dir C:\\STONIC_V2\\data     # where STONIC saved your xKiro key

1. Web search + page reading (no key needed): a real search, then the first pages are fetched.
2. The model provider (xKiro): one tiny request with your saved key and configured model, to show the exact
   HTTP status if the key, model id, quota or network is the problem. The key is never printed.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sys as _sys
if _sys.stdout.encoding and _sys.stdout.encoding.lower() != "utf-8":
    # Windows consoles often default to a legacy codepage (cp1252/cp437) that cannot encode
    # arbitrary Unicode; a plain print() of anything outside it would crash this script.
    _sys.stdout.reconfigure(errors="replace")
    _sys.stderr.reconfigure(errors="replace")


import httpx

from stonic.config.settings import Settings
from stonic.providers import websearch
from stonic.security.secrets import SecretStore


async def check_search(query: str, out=print) -> bool:
    out(f"1) Web search for: {query!r}")
    try:
        hits = await websearch.search(query, max_results=5)
    except websearch.SearchUnavailable as error:
        out(f"   FAIL: search could not be reached: {error}")
        out("   Check your internet connection, VPN, proxy or firewall (python.exe needs outbound HTTPS).")
        return False
    except websearch.NoResults as error:
        out(f"   FAIL: no results ({error}). Try again in a minute; search engines rate-limit bursts.")
        return False
    for i, hit in enumerate(hits, 1):
        out(f"   [{i}] {hit.title[:70]}  {hit.url}")
    await websearch.fetch_pages(hits, 2)
    for hit in hits[:2]:
        out(f"   page text from {hit.url[:60]}: {len(hit.text)} characters" + ("" if hit.text else "  (could not be read; the snippet is used instead)"))
    out("   OK: search works.")
    return True


async def check_provider(settings: Settings, key: str, out=print) -> bool:
    out(f"2) Model provider: {settings.llm_base_url}  model: {settings.llm_model}")
    if not key:
        out("   SKIP: no xKiro key found. Save it in STONIC -> Settings -> AI & Providers (or pass --data-dir).")
        return False
    body = {"model": settings.llm_model, "messages": [{"role": "user", "content": "Reply with the single word: ready"}], "max_tokens": 16, "stream": False}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=8)) as client:
            response = await client.post(f"{settings.llm_base_url.rstrip('/')}/chat/completions", json=body,
                                         headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    except httpx.HTTPError as error:
        out(f"   FAIL: could not reach the provider ({type(error).__name__}). Check your internet connection.")
        return False
    if response.status_code == 200:
        out("   OK: the provider accepted the key and model.")
        return True
    detail = response.text[:300].replace(key, "***")
    hints = {401: "the key was rejected", 403: "the key was rejected or lacks access to this model", 404: "the model id was not found (it must look like vendor/model)",
             402: "no credit / plan does not cover this model", 429: "rate limit or quota reached"}
    out(f"   FAIL: HTTP {response.status_code}: {hints.get(response.status_code, 'provider error')}\n   {detail}")
    return False


def load_key(data_dir: Path, settings: Settings) -> str:
    try:
        return SecretStore(data_dir).key(settings.llm_base_url)
    except Exception:
        return os.environ.get("XKIRO_API_KEY", "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default=os.environ.get("STONIC_DATA_DIR", "data"))
    parser.add_argument("--query", default="latest stable Python release")
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    settings = Settings()
    try:                                       # use the model/endpoint the app is actually configured with
        from stonic.config.settings import Configuration
        from stonic.storage.database import Database
        for name in ("stonic.db", "stonic.sqlite", "stonic.sqlite3"):
            if (data_dir / name).is_file():
                settings = Configuration(Database(data_dir / name)).values
                break
    except Exception:
        pass
    search_ok = asyncio.run(check_search(args.query))
    print()
    provider_ok = asyncio.run(check_provider(settings, load_key(data_dir, settings)))
    print("\nResult: " + ("web research should work." if search_ok and provider_ok else "fix the FAIL/SKIP item(s) above, then retry in STONIC."))
    return 0 if search_ok and provider_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
