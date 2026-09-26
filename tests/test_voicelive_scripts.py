"""The operator scripts must at least run: they are how a user validates real hardware and the real service."""
import asyncio
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from voicelive_fakes import FakeConnector, FakeSession, m_audio, m_model_text, m_turn_complete

ROOT = Path(__file__).resolve().parents[1]


def load(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Talkative(FakeSession):
    """Answers a text prompt with a second of speech, as the real model does."""
    async def send_realtime_input(self, **kw):
        await super().send_realtime_input(**kw)
        if kw.get("text"):
            self.push(m_audio(b"\x10\x00" * 24000), m_model_text("STONIC voice check complete."), m_turn_complete())


class ScriptedConnector(FakeConnector):
    session_class = Talkative


async def test_check_script_reports_success_when_speech_comes_back():
    check = load("voicelive-check")
    lines = []
    connector = ScriptedConnector()
    assert await check.check(connector("k"), "gemini-3.8-live", out=lines.append) is True
    text = "\n".join(lines)
    assert "OK: gemini-3.8-live works" in text and "1.0 s of speech" in text and "voice check complete" in text


async def test_check_script_steps_down_tiers_and_stops_on_a_refused_key():
    check = load("voicelive-check")
    lines = []
    refused = ScriptedConnector(failures=[Exception("API key not valid. Please pass a valid API key.")])
    assert await check.check(refused("k"), "test-model", out=lines.append) is False and "rejected the key" in "\n".join(lines)
    lines.clear()
    picky = ScriptedConnector(failures=[Exception("1007 invalid argument")])
    assert await check.check(picky("k"), "test-model", out=lines.append) is True
    assert "tier 1" in "\n".join(lines) and "rejected an optional field" in "\n".join(lines)


def test_check_script_never_prints_the_key(monkeypatch, capsys):
    check = load("voicelive-check")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSy-super-secret-value")
    monkeypatch.setattr(check, "default_connector", lambda key: (_ for _ in ()).throw(SystemExit(0)))
    with pytest.raises(SystemExit):
        monkeypatch.setattr(sys, "argv", ["x"]); check.main()
    assert "super-secret" not in capsys.readouterr().out


@pytest.mark.parametrize("room", ["desk", "phones"])
def test_calibration_script_runs_end_to_end_without_hardware(room):
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "voicelive-calibrate.py"), "--simulate", room],
                            capture_output=True, text=True, timeout=120, cwd=ROOT)
    assert result.returncode == 0, result.stderr
    assert "Phase 3/3" in result.stdout and "-- Result" in result.stdout and "would have interrupted it: 0" in result.stdout


async def test_check_script_gives_up_instead_of_hanging_when_the_model_never_answers():
    check = load("voicelive-check")
    lines = []
    silent = FakeConnector()               # a session that connects and then says nothing
    assert await asyncio.wait_for(check.check(silent("k"), "test-model", timeout=0.3, out=lines.append), 5) is False
    assert "no speech came back" in "\n".join(lines)


# ── the web research operator script ─────────────────────────────────────────

async def test_websearch_check_reports_each_half_separately(monkeypatch):
    check = load("websearch-check")
    from stonic.providers import websearch

    async def fake_search(query, **kw):
        return [websearch.Hit("Python 3.14", "https://python.org/", "snip")]

    async def fake_fetch(hits, limit, **kw):
        hits[0].text = "page text"
    monkeypatch.setattr(check.websearch, "search", fake_search)
    monkeypatch.setattr(check.websearch, "fetch_pages", fake_fetch)
    lines = []
    assert await check.check_search("q", out=lines.append) is True
    assert "OK: search works" in "\n".join(lines) and "9 characters" in "\n".join(lines)

    async def broken(query, **kw):
        raise websearch.SearchUnavailable("ConnectError")
    monkeypatch.setattr(check.websearch, "search", broken)
    lines.clear()
    assert await check.check_search("q", out=lines.append) is False and "firewall" in "\n".join(lines)


async def test_websearch_check_explains_provider_status_codes_without_printing_the_key(monkeypatch):
    import httpx
    check = load("websearch-check")
    settings = check.Settings()
    real = httpx.AsyncClient
    for code, hint in ((401, "key was rejected"), (404, "vendor/model"), (429, "quota")):
        def handler(request, code=code):
            return httpx.Response(code, text='{"error":"bad key sk-secret-value"}')
        monkeypatch.setattr(check.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler)))
        lines = []
        assert await check.check_provider(settings, "sk-secret-value", out=lines.append) is False
        text = "\n".join(lines)
        assert hint in text and "sk-secret-value" not in text
    monkeypatch.setattr(check.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))))
    lines = []
    assert await check.check_provider(settings, "k" * 12, out=lines.append) is True
    lines.clear()
    assert await check.check_provider(settings, "", out=lines.append) is False and "SKIP" in lines[-1]
