import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from stonic.app.api import create_app
from stonic.config.settings import Configuration, Settings
from stonic.core.models import ActionResult, Activity, ChatInput, PermissionLevel
from stonic.core.service import EmptyArguments
from stonic.providers.llm import OpenAICompatibleProvider
from stonic.security.permissions import PermissionGate
from stonic.state.engine import StateEngine
from stonic.storage.database import Database
from stonic.tools.registry import Tool, ToolRegistry


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path, "test-session-token")
    with TestClient(app, headers={"X-Stonic-Token": "test-session-token"}) as client:
        yield client


def test_invalid_state_transition_does_not_mutate_state():
    state = StateEngine()
    with pytest.raises(ValueError):
        state.transition(Activity.THINKING)
    assert state.activity == Activity.INITIALIZING
    state.transition(Activity.IDLE)
    state.transition(Activity.THINKING)
    state.transition(Activity.ERROR)
    state.transition(Activity.IDLE)


def test_permissions_are_exact_and_single_use():
    gate = PermissionGate()
    assert not gate.authorize("file.delete", PermissionLevel.SENSITIVE)
    request = gate.request("file.delete", PermissionLevel.SENSITIVE, "Delete one specified file")
    gate.decide(request.id, True)
    assert gate.authorize("file.delete", PermissionLevel.SENSITIVE, request.id)
    assert not gate.authorize("file.delete", PermissionLevel.SENSITIVE, request.id)
    wrong = gate.request("file.delete", PermissionLevel.SENSITIVE, "Delete")
    gate.decide(wrong.id, True)
    assert not gate.authorize("external.send", PermissionLevel.SENSITIVE, wrong.id)


def test_registry_blocks_unvalidated_and_unapproved_actions():
    calls = []
    registry = ToolRegistry(PermissionGate())
    tool = Tool("sensitive.test", "A test only tool", EmptyArguments, PermissionLevel.SENSITIVE,
                lambda args: calls.append(args) or ActionResult(success=True, status="completed", message="Done"))
    registry.register(tool)
    with pytest.raises(ValueError): registry.register(tool)
    assert registry.execute("unknown", {}).status == "unavailable"
    assert registry.execute(tool.name, {"injected": "argument"}).status == "failed"
    assert registry.execute(tool.name, {}).status == "denied"
    assert not calls


def test_loopback_api_auth_and_origin(client):
    assert client.get("/api/status", headers={"X-Stonic-Token":"wrong"}).status_code == 401
    assert client.get("/api/status", headers={"Origin":"https://attacker.invalid"}).status_code == 403
    assert client.get("/api/status").status_code == 200
    assert client.get("/api/status", headers={"Host":"attacker.invalid"}).status_code == 400


def test_honest_degraded_status_and_live_metrics(client):
    data = client.get("/api/status").json()
    assert data["health"] == "degraded"
    assert "voice_capture" not in data and "voice" not in data
    assert data["activity"] == "idle"
    assert data["metrics"]["memory_total_gb"] > 0
    assert 0 <= data["metrics"]["cpu_percent"] <= 100
    assert not any(check["id"] in {"stt","tts","vad"} for check in data["checks"])
    assert data["counts"] == {"notes":0,"tasks":0,"memory":0}


@pytest.mark.parametrize("kind", ["notes","tasks","memory"])
def test_records_crud_validation_and_deletion_confirmation(client, kind):
    assert client.post(f"/api/records/{kind}",json={"title":"   "}).status_code == 422
    assert client.post(f"/api/records/{kind}",json={"title":"x","unexpected":True}).status_code == 422
    payload={"title":"A real record","content":"Persist this"}
    if kind == "memory":
        payload["confirm_memory"] = True
    record = client.post(f"/api/records/{kind}",json=payload).json()
    endpoint = f"/api/records/{kind}/{record['id']}"
    update_payload={"title":"Updated", "status":"done"}
    if kind == "memory":
        update_payload["confirm_memory"] = True
    assert client.patch(endpoint,json=update_payload).json()["title"] == "Updated"
    assert client.get(f"/api/records/{kind}").json()[0]["content"] == "Persist this"
    assert client.delete(endpoint).status_code == 400
    assert client.delete(endpoint, headers={"X-Stonic-Confirm":"delete"}).status_code == 200
    assert client.get(f"/api/records/{kind}").json() == []


def test_config_is_atomic_and_persists_across_restart(tmp_path):
    with TestClient(create_app(tmp_path,"token"),headers={"X-Stonic-Token":"token"}) as first:
        assert first.patch("/api/config",json={"display_name":"Ada"}).status_code == 200
        record = first.post("/api/records/notes",json={"title":"Restart check"}).json()
        assert first.patch("/api/config",json={"display_name":"Lost", "temperature":99}).status_code == 422
        assert first.get("/api/config").json()["values"]["display_name"] == "Ada"
    with TestClient(create_app(tmp_path,"token2"),headers={"X-Stonic-Token":"token2"}) as second:
        assert second.get("/api/config").json()["values"]["display_name"] == "Ada"
        assert second.get("/api/records/notes").json()[0]["id"] == record["id"]


def test_legacy_voice_settings_are_migrated_away(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    try:
        legacy = Settings().model_dump()
        legacy.update({"voice_language":"en","voice_threads":4,"vad_threshold":0.5,"audio_input_device":"old-mic"})
        db.save_settings(legacy)
        config = Configuration(db)
        # The retired local STT/TTS/VAD settings stay gone. (Live cloud voice has its own,
        # differently named voice_* settings, so the prefix alone is no longer a signal.)
        assert not any(key in Configuration.RETIRED_SETTINGS for key in config.values.model_dump())
        stored = db.settings() or {}
        assert "voice_language" not in stored and "audio_input_device" not in stored
    finally:
        db.close()


@pytest.mark.parametrize("endpoint", ["http://remote.example/v1","file:///etc/passwd","https://key:secret@example.com/v1","https://example.com/v1?key=secret"])
def test_invalid_provider_urls_are_rejected(endpoint):
    with pytest.raises(ValidationError): Settings(llm_base_url=endpoint)


def test_no_credentials_in_config_or_logs(client, monkeypatch):
    monkeypatch.setenv("XKIRO_API_KEY","secret-must-not-leak")
    config = client.get("/api/config")
    assert config.json()["credential_configured"] is True
    assert "secret-must-not-leak" not in config.text
    assert "secret-must-not-leak" not in client.get("/api/logs").text


def test_chat_without_provider_is_clear_and_status_tool_runs(client):
    response = client.post("/api/chat",json={"content":"Hello"}).json()
    assert "Connect an intelligence provider" in response["content"]
    result = client.post("/api/chat",json={"content":"/status"}).json()
    assert "CPU:" in result["content"]
    history = client.get("/api/chat/main").json()
    assert len(history) == 4
    assert [entry["role"] for entry in history] == ["user","assistant","user","assistant"]
    assert client.get("/api/status").json()["activity"] == "idle"


def test_disabled_conversation_saving_keeps_only_ephemeral_context(client):
    client.patch("/api/config", json={"save_conversations":False})
    client.post("/api/chat",json={"content":"ephemeral text"})
    assert len(client.get("/api/chat/main").json()) == 2
    assert client.app.state.core.db.messages("main") == []
    assert "ephemeral text" not in client.get("/api/logs").text


async def test_provider_adapter_validates_completions_and_preserves_context():
    requests = []
    def handle(request):
        import json
        requests.append(json.loads(request.content))
        return httpx.Response(200,json={"choices":[{"message":{"content":"A real adapter response from the test server"}}]})
    provider = OpenAICompatibleProvider()
    await provider.client.aclose()
    provider.client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    history = [{"role":"user","content":"First turn"},{"role":"assistant","content":"Answer"},{"role":"user","content":"Follow up"}]
    response = await provider.complete(Settings(llm_model="test-model"), history)
    assert response.startswith("A real adapter")
    assert requests[0]["messages"] == history
    await provider.close()


async def test_malformed_provider_completion_is_not_success():
    provider = OpenAICompatibleProvider()
    await provider.client.aclose()
    provider.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200,json={"choices":[]})))
    with pytest.raises(ValueError): await provider.complete(Settings(llm_model="test"), [])
    await provider.close()


async def test_cancellation_restores_idle(client):
    service = client.app.state.core
    service.config.update({"llm_model":"test"})
    began = asyncio.Event()
    class SlowProvider:
        async def complete(self, *_):
            began.set()
            await asyncio.sleep(30)
    service.provider = SlowProvider()
    task = asyncio.create_task(service.chat(ChatInput(content="Wait")))
    await began.wait()
    assert service.cancel()
    response = await task
    assert response["content"] == "Generation stopped."
    assert service.state.activity == Activity.IDLE


def test_reset_requires_confirmation(client):
    client.patch("/api/config",json={"display_name":"Test"})
    assert client.post("/api/config/reset",json={}).status_code == 400
    assert client.post("/api/config/reset",json={"confirm":True,"key":"display_name"}).json()["display_name"] == ""


def test_child_process_environment_excludes_stonic_secrets(monkeypatch):
    from stonic.security.process import sanitized_environment
    monkeypatch.setenv("STONIC_API_TOKEN", "must-not-leak")
    monkeypatch.setenv("XKIRO_API_KEY", "must-not-leak")
    monkeypatch.setenv("STONIC_LLM_API_KEY", "must-not-leak")
    env = sanitized_environment()
    assert "STONIC_API_TOKEN" not in env
    assert "XKIRO_API_KEY" not in env
    assert "STONIC_LLM_API_KEY" not in env


def test_browser_blocks_private_network_targets():
    from stonic.security.network import validate_http_url
    with pytest.raises(ValueError): validate_http_url("http://127.0.0.1:8000/")
    with pytest.raises(ValueError): validate_http_url("http://192.168.1.1/")
    with pytest.raises(ValueError): validate_http_url("http://localhost/")
    assert validate_http_url("https://example.com/") == "https://example.com/"
