"""HTTP surface, settings and diagnostics for live voice."""
import pytest
from fastapi.testclient import TestClient

from stonic.app.api import create_app
from stonic.security.secrets import SecretStore
from voicelive_fakes import FakeConnector, FakeDevices

TOKEN = "voice-test-token"
GEMINI_KEY = "AIzaSy-test-key-abcdefghij"


@pytest.fixture
def client(tmp_path, monkeypatch):
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(SecretStore, "_crypt", staticmethod(lambda raw, decrypt=False: raw[::-1]))   # DPAPI stand-in off Windows
    with TestClient(create_app(tmp_path, TOKEN), headers={"X-Stonic-Token": TOKEN}) as c:
        yield c


def wire_fakes(client):
    """Swap the sound card and Google for fakes so no test can touch a real device or the network."""
    voice = client.app.state.voice
    devices, connector = FakeDevices(), FakeConnector()
    devices.service = voice
    voice._connector, voice._mic_factory, voice._speaker_factory = connector, devices.mic_factory, devices.speaker_factory
    return voice, devices, connector


ROUTES = [("GET", "/api/voice/status"), ("GET", "/api/voice/devices"), ("POST", "/api/voice/start"), ("POST", "/api/voice/stop"),
          ("POST", "/api/voice/mute"), ("POST", "/api/voice/interrupt"), ("POST", "/api/voice/ptt"), ("PUT", "/api/voice/session"),
          ("PUT", "/api/voice/credential"), ("DELETE", "/api/voice/credential"), ("GET", "/api/voice/stream")]


@pytest.mark.parametrize("method,path", ROUTES)
def test_every_voice_route_needs_the_session_token_and_a_trusted_origin(client, method, path):
    bare = {"X-Stonic-Token": ""}
    assert client.request(method, path, headers=bare, json={} if method != "GET" else None).status_code == 401
    assert client.request(method, path, headers={"Origin": "https://attacker.invalid"}, json={} if method != "GET" else None).status_code == 403


def test_status_starts_off_and_says_what_is_missing(client):
    status = client.get("/api/voice/status").json()
    assert status["state"] == "off" and status["running"] is False
    assert status["consent"] is False and status["credential_configured"] is False
    assert status["model"] == "gemini-3.8-live" and status["barge_in"] == "off"


def test_a_text_only_install_looks_exactly_as_before(client):
    data = client.get("/api/status").json()
    assert "voice" not in data and not any(check["id"] == "voice" for check in data["checks"])
    assert not any(check["id"] in {"stt", "tts", "vad"} for check in data["checks"])


def test_voice_settings_are_in_the_schema_with_sensible_defaults(client):
    config = client.get("/api/config").json()
    props, values = config["schema"]["properties"], config["values"]
    assert props["voice_cloud_consent"]["category"] == "Privacy" and values["voice_cloud_consent"] is False
    for key in ("voice_autostart", "voice_name", "voice_live_model", "voice_input_device", "voice_output_device",
                "voice_push_to_talk", "voice_barge_in", "voice_end_of_speech_ms", "voice_idle_sleep_minutes"):
        assert props[key]["category"] == "Voice", key
    assert values["voice_autostart"] is False and values["voice_push_to_talk"] == "off" and values["voice_barge_in"] == "off"
    assert "voice_language" not in props        # the retired local-pipeline settings stay retired


@pytest.mark.parametrize("change", [{"voice_name": "Robot"}, {"voice_live_model": "bad model!"}, {"voice_live_model": ""},
                                    {"voice_end_of_speech_ms": 50}, {"voice_end_of_speech_ms": 99999}, {"voice_barge_in": "always"},
                                    {"voice_push_to_talk": "a"}, {"voice_idle_sleep_minutes": -1}, {"voice_unknown": 1}])
def test_invalid_voice_settings_are_rejected_and_change_nothing(client, change):
    before = client.get("/api/config").json()["values"]
    assert client.patch("/api/config", json=change).status_code == 422
    assert client.get("/api/config").json()["values"] == before


def test_valid_voice_settings_persist(client):
    changes = {"voice_name": "Kore", "voice_live_model": " gemini-3.1-flash-live-preview ", "voice_push_to_talk": "f9",
               "voice_barge_in": "guarded", "voice_end_of_speech_ms": 800, "voice_input_device": "  USB Mic ", "voice_idle_sleep_minutes": 15}
    values = client.patch("/api/config", json=changes).json()
    assert values["voice_live_model"] == "gemini-3.1-flash-live-preview" and values["voice_input_device"] == "USB Mic"
    assert client.get("/api/config").json()["values"]["voice_name"] == "Kore"


def test_start_refuses_without_consent_and_without_a_key_and_says_how_to_fix_it(client):
    voice, devices, connector = wire_fakes(client)
    response = client.post("/api/voice/start", json={})
    assert response.status_code == 409 and "Privacy" in response.json()["detail"]
    client.patch("/api/config", json={"voice_cloud_consent": True})
    response = client.post("/api/voice/start", json={})
    assert response.status_code == 409 and "Gemini API key" in response.json()["detail"]
    assert devices.opened == [] and connector.keys == []


def test_the_key_is_saved_encrypted_never_echoed_and_never_logged(client, tmp_path):
    assert client.put("/api/voice/credential", json={"key": GEMINI_KEY, "extra": 1}).status_code == 422
    assert client.put("/api/voice/credential", json={"key": "short"}).status_code == 422
    assert client.put("/api/voice/credential", json={"key": GEMINI_KEY}).json() == {"credential_configured": True}
    assert client.get("/api/voice/status").json()["credential_configured"] is True
    for payload in (client.get("/api/voice/status").text, client.get("/api/config").text, client.get("/api/logs").text):
        assert GEMINI_KEY not in payload
    assert GEMINI_KEY.encode() not in (tmp_path / "credentials.dpapi").read_bytes()
    assert client.delete("/api/voice/credential").status_code == 400
    assert client.delete("/api/voice/credential", headers={"X-Stonic-Confirm": "delete"}).json() == {"credential_configured": False}


def test_the_provider_key_and_the_voice_key_never_cross(client):
    client.put("/api/provider/credential", json={"key": "xkiro-key-0123456789"})
    assert client.get("/api/voice/status").json()["credential_configured"] is False
    client.put("/api/voice/credential", json={"key": GEMINI_KEY})
    assert client.get("/api/config").json()["credential_configured"] is True      # provider state untouched
    client.delete("/api/voice/credential", headers={"X-Stonic-Confirm": "delete"})
    assert client.get("/api/config").json()["credential_configured"] is True


def test_voice_appears_in_diagnostics_once_the_user_engages_with_it(client):
    client.patch("/api/config", json={"voice_cloud_consent": True})
    check = next(c for c in client.get("/api/status").json()["checks"] if c["id"] == "voice")
    assert check["status"] == "unconfigured" and "Gemini API key" in check["detail"]
    client.put("/api/voice/credential", json={"key": GEMINI_KEY})
    check = next(c for c in client.get("/api/status").json()["checks"] if c["id"] == "voice")
    assert check["status"] == "ready" and "off" in check["detail"].lower()


def test_start_mute_ptt_interrupt_and_stop_over_http(client):
    voice, devices, connector = wire_fakes(client)
    client.patch("/api/config", json={"voice_cloud_consent": True})
    client.put("/api/voice/credential", json={"key": GEMINI_KEY})
    started = client.post("/api/voice/start", json={"session_id": "voice-1"}).json()
    assert started["running"] is True and started["session_id"] == "voice-1"
    assert [kind for kind, _ in devices.opened] == ["speaker", "mic"]
    assert client.post("/api/voice/start", json={"session_id": "bad id!"}).status_code == 422
    assert client.post("/api/voice/mute", json={"muted": "yes"}).status_code == 422
    assert client.post("/api/voice/mute", json={"muted": True}).json()["state"] == "muted"
    assert client.post("/api/voice/mute", json={"muted": False}).json()["muted"] is False
    assert client.post("/api/voice/ptt", json={"held": True}).json()["push_to_talk_held"] is True
    assert client.post("/api/voice/ptt", json={"held": "x"}).status_code == 422
    assert client.post("/api/voice/interrupt").status_code == 200
    assert client.put("/api/voice/session", json={"session_id": "voice-2"}).json()["session_id"] == "voice-2"
    assert client.put("/api/voice/session", json={"session_id": "no spaces"}).status_code == 422
    stopped = client.post("/api/voice/stop").json()
    assert stopped["running"] is False and devices.mic.closed and devices.speaker.closed
    assert client.post("/api/voice/stop").status_code == 200        # stopping twice is harmless


def test_autostart_without_consent_does_nothing_and_says_why(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", GEMINI_KEY)
    import json
    from stonic.storage.database import Database
    from stonic.config.settings import Configuration
    db = Database(tmp_path / "stonic.db")
    Configuration(db).update({"voice_autostart": True})      # consent deliberately left off
    db.close()
    with TestClient(create_app(tmp_path, TOKEN), headers={"X-Stonic-Token": TOKEN}) as c:
        import time
        for _ in range(40):
            logs = c.get("/api/logs").json()
            if any("did not start automatically" in row["message"] for row in logs):
                break
            time.sleep(0.05)
        assert any("did not start automatically" in row["message"] for row in logs)
        assert c.get("/api/voice/status").json()["running"] is False
