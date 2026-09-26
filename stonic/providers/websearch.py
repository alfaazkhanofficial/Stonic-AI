"""Real web search and page retrieval for Web intelligence.

Why this exists: STONIC's web research used to ask the model provider to browse
(``tools: [{"type": "browser_search"}]``). That is a Groq-only feature. xKiro, the
configured provider, accepts function tools only and has no built-in browsing, so
every research request failed. Search is therefore done here, on this PC, and the
model is only asked to write an answer from the pages that were actually retrieved.

Two steps:

* ``search``: a keyless metasearch (the ``ddgs`` library, which queries several
  engines and merges the results). Runs in a worker thread; it is synchronous.
* ``fetch_pages``: reads the top results so the answer rests on page text and not
  just snippets. Result URLs are untrusted, so a page is only fetched if it is a
  plain http(s) URL on the default port whose host resolves ONLY to public
  addresses (no localhost, private LAN, link-local or metadata addresses), at
  every redirect hop. Responses are size-capped and read as text only.
"""
from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

_LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa")
MAX_PAGE_BYTES = 500_000
PAGE_TEXT_CHARS = 6000
FETCH_TIMEOUT_S = 7.0
MAX_REDIRECTS = 3
SEARCH_TIMEOUT_S = 12
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


class SearchUnavailable(Exception):
    """The search engines could not be reached (network, firewall, rate limit)."""


class NoResults(Exception):
    """The search worked but returned nothing usable."""


@dataclass
class Hit:
    title: str
    url: str
    snippet: str
    text: str = ""       # readable page text, when it could be fetched safely


def search_available() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("ddgs") is not None
    except Exception:
        return False


def _hostname_allowed(url: str, domains: list[str]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    if not domains:
        return True
    return any(host == d.lstrip("*.").lower() or host.endswith("." + d.lstrip("*.").lower()) for d in domains)


def _query_with_domains(query: str, domains: list[str]) -> str:
    if not domains:
        return query
    return f"{query} ({' OR '.join('site:' + d.lstrip('*.') for d in domains)})"


def _search_sync(query: str, max_results: int) -> list[dict]:
    from ddgs import DDGS
    return DDGS(timeout=SEARCH_TIMEOUT_S).text(query, max_results=max_results)


async def search(query: str, *, max_results: int = 8, domains: list[str] | None = None, runner=None) -> list[Hit]:
    """Search the web. ``runner`` lets tests replace the network call."""
    domains = domains or []
    run = runner or _search_sync
    try:
        raw = await asyncio.to_thread(run, _query_with_domains(query, domains), max_results * 2 if domains else max_results)
    except ImportError as error:
        raise SearchUnavailable("The web search library is not installed. Run Setup-Stonic.cmd.") from error
    except Exception as error:
        name = type(error).__name__
        if "no results" in str(error).lower():
            raise NoResults(str(error)) from error
        raise SearchUnavailable(f"{name}: {str(error)[:200]}") from error
    hits: dict[str, Hit] = {}
    for item in raw or []:
        url = str(item.get("href") or item.get("url") or "").strip()
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            continue
        if not _hostname_allowed(url, domains):
            continue
        hits.setdefault(url, Hit(title=str(item.get("title") or parts.hostname)[:300], url=url,
                                 snippet=str(item.get("body") or item.get("snippet") or "")[:1600]))
    if not hits:
        raise NoResults("The search returned no usable results.")
    return list(hits.values())[:max_results]


# ── safe page fetching ───────────────────────────────────────────────────────

def _is_public_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%")[0])
    except ValueError:
        return False
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_loopback or ip.is_link_local)


def _resolve_public_sync(host: str) -> bool:
    """True only if every address the name resolves to is public."""
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except OSError:
        return False
    return bool(addresses) and all(_is_public_ip(a) for a in addresses)


async def url_is_safe(url: str, resolver=None) -> bool:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        return False
    if parts.port not in (None, 80, 443):
        return False
    host = parts.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(_LOCAL_SUFFIXES):
        return False                           # never even ask DNS about local names
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass                                   # a name: check what it resolves to
    else:
        return _is_public_ip(host)             # a literal address must itself be public
    return await asyncio.to_thread(resolver or _resolve_public_sync, host)


class _Readable(HTMLParser):
    _SKIP = {"script", "style", "noscript", "svg", "template", "head", "nav", "footer", "form", "iframe"}
    _BREAK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
        elif tag in self._BREAK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data)


def readable_text(html: str, limit: int = PAGE_TEXT_CHARS) -> str:
    parser = _Readable()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(parser.parts))
    text = re.sub(r"\s*\n\s*", "\n", text).strip()
    return text[:limit]


async def fetch_text(client: httpx.AsyncClient, url: str, resolver=None) -> str:
    """Readable text of a page, or "" if it is unsafe, slow, huge or not text. Never raises."""
    try:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            if not await url_is_safe(current, resolver):
                return ""
            async with client.stream("GET", current, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9"},
                                     follow_redirects=False) as response:
                if response.is_redirect:
                    location = response.headers.get("location", "")
                    if not location:
                        return ""
                    current = urljoin(current, location)
                    continue
                if response.status_code != 200:
                    return ""
                kind = response.headers.get("content-type", "").split(";")[0].strip().lower()
                if kind not in {"text/html", "application/xhtml+xml", "text/plain"}:
                    return ""
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) >= MAX_PAGE_BYTES:
                        break
                text = bytes(body).decode(response.encoding or "utf-8", errors="replace")
                return " ".join(text.split())[:PAGE_TEXT_CHARS] if kind == "text/plain" else readable_text(text)
        return ""
    except Exception:
        return ""


async def fetch_pages(hits: list[Hit], limit: int, client: httpx.AsyncClient | None = None, resolver=None) -> None:
    """Fill ``hit.text`` for the first ``limit`` hits, concurrently. Failures leave the snippet in place."""
    owns = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(FETCH_TIMEOUT_S, connect=4.0))
    try:
        results = await asyncio.gather(*(fetch_text(client, h.url, resolver) for h in hits[:limit]), return_exceptions=True)
        for hit, text in zip(hits[:limit], results):
            hit.text = text if isinstance(text, str) else ""
    finally:
        if owns:
            await client.aclose()
