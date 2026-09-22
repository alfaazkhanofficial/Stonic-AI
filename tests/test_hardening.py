import asyncio
import json
from datetime import datetime, timedelta, timezone
import httpx
import pytest
from stonic.config.settings import Configuration, Settings
from stonic.core.models import ChatInput, PermissionLevel
from stonic.core.service import CoreService
from stonic.diagnostics.health import Diagnostics
from stonic.events.bus import EventBus
from stonic.events.productivity import Productivity
from stonic.events.scheduler import ReminderCreate, Scheduler
from stonic.providers.llm import OpenAICompatibleProvider, ProviderError
from stonic.storage.database import Database
from stonic.tasks.contracts import Decision


def test_calendar_escapes_injection_and_folds_utf8(tmp_path):
    db=Database(tmp_path/'db.sqlite')
    try:
        scheduler=Scheduler(db,EventBus(db),Configuration(db),Diagnostics(tmp_path))
        title='नमस्ते, meeting; '+('界'*30)+'\r\nBEGIN:VEVENT'
        scheduler.create(ReminderCreate(title=title,due_at=datetime.now(timezone.utc)+timedelta(hours=1),interval_seconds=86400))
        product=Productivity(db)
        text=product.calendar()
        assert all(len(line.encode('utf8'))<=75 for line in text.split('\r\n'))
        unfolded=text.replace('\r\n ','')
        assert unfolded.count('\r\nBEGIN:VEVENT\r\n')==1
        assert '\\, meeting\\;' in unfolded and '\\nBEGIN:VEVENT' in unfolded
        assert 'RRULE:FREQ=SECONDLY;INTERVAL=86400' in unfolded
        task=db.create_record('tasks','Real pending task','')
        summary=product.briefing().data
        assert summary['open_task_count']==1 and summary['open_tasks'][0]['id']==task['id']
        assert len(summary['reminders'])==1
        product.viewed()
        assert Productivity(db).briefing().data['viewed_at']
    finally:db.close()


async def test_stream_only_emits_content_and_empty_stream_fails():
    provider=OpenAICompatibleProvider()
    await provider.client.aclose()
    response='data: '+json.dumps({'choices':[{'delta':{'reasoning':'private reasoning'}}]})+'\n\ndata: '+json.dumps({'choices':[{'delta':{'content':'Hello '}}]})+'\n\ndata: '+json.dumps({'choices':[{'delta':{'content':'there.'}}]})+'\n\ndata: [DONE]\n\n'
    provider.client=httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,text=response)))
    assert ''.join([p async for p in provider.stream(Settings(),[])])=='Hello there.'
    await provider.close()
    provider.client=httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,text='data: [DONE]\n\n')))
    with pytest.raises(ValueError,match='no streamed text'):
        _=[p async for p in provider.stream(Settings(),[])]
    await provider.close()



async def test_provider_retries_documented_transient_status(monkeypatch):
    attempts = 0
    def handle(_request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, json={"error":{"message":"temporary upstream"}})
        return httpx.Response(200, json={"choices":[{"message":{"content":"Recovered"}}]})
    provider = OpenAICompatibleProvider()
    await provider.client.aclose()
    provider.client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(provider, "_retry_delay", lambda *_: 0.0)
    assert await provider.complete(Settings(llm_model="test-model"), []) == "Recovered"
    assert attempts == 2
    await provider.close()


async def test_provider_transient_failure_does_not_claim_missing_credentials(monkeypatch):
    provider = OpenAICompatibleProvider()
    await provider.client.aclose()
    provider.client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(500, json={"error":{"message":"upstream unavailable"}})))
    monkeypatch.setattr(provider, "_retry_delay", lambda *_: 0.0)
    with pytest.raises(ProviderError) as captured:
        await provider.complete(Settings(llm_model="test-model"), [])
    message = str(captured.value).lower()
    assert "temporarily unavailable" in message
    assert "missing" not in message and "not configured" not in message
    await provider.close()



async def test_provider_check_validates_key_and_reports_free_usage():
    class Secrets:
        def key(self, _endpoint): return "sk-xt-test-key-never-real"
    def handle(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data":[{"id":"minimax/minimax-m3:free"}]})
        if request.url.path.endswith("/usage"):
            assert request.headers.get("Authorization") == "Bearer sk-xt-test-key-never-real"
            return httpx.Response(200, json={"free_tokens":{"used_today":250,"limit_per_day":1000,"remaining":750},"windows":[],"wallet":None})
        return httpx.Response(404)
    provider=OpenAICompatibleProvider(Secrets())
    await provider.client.aclose()
    provider.client=httpx.AsyncClient(transport=httpx.MockTransport(handle))
    check=await provider.check(Settings(llm_model="minimax/minimax-m3:free"))
    assert check.status=="ready" and "750" in check.detail
    await provider.close()


async def test_provider_check_reports_exhausted_free_allowance_without_blaming_key():
    class Secrets:
        def key(self, _endpoint): return "sk-xt-test-key-never-real"
    def handle(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data":[{"id":"minimax/minimax-m3:free"}]})
        if request.url.path.endswith("/usage"):
            return httpx.Response(200, json={"free_tokens":{"used_today":1000,"limit_per_day":1000,"remaining":0}})
        return httpx.Response(404)
    provider=OpenAICompatibleProvider(Secrets())
    await provider.client.aclose()
    provider.client=httpx.AsyncClient(transport=httpx.MockTransport(handle))
    check=await provider.check(Settings(llm_model="minimax/minimax-m3:free"))
    assert check.status=="degraded"
    assert "allowance is exhausted" in check.detail.lower()
    assert "api key" not in check.detail.lower()
    await provider.close()


async def test_stream_surfaces_midstream_error_instead_of_silent_truncation():
    provider = OpenAICompatibleProvider()
    await provider.client.aclose()
    payload = (
        'data: ' + json.dumps({'choices':[{'delta':{'content':'Partial '}}]}) + '\n\n'
        + 'data: ' + json.dumps({'error':{'message':'Upstream provider is unavailable. Please retry.','type':'api_error','code':'upstream_error'}}) + '\n\n'
        + 'data: [DONE]\n\n'
    )
    provider.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=payload)))
    pieces = []
    with pytest.raises(ProviderError, match='Upstream provider is unavailable'):
        async for piece in provider.stream(Settings(), []):
            pieces.append(piece)
    assert ''.join(pieces) == 'Partial '
    await provider.close()


async def test_stream_retries_xkiro_midstream_error_before_visible_text(monkeypatch):
    attempts = 0
    def handle(_request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            payload = 'data: ' + json.dumps({'error':{'message':'Temporary upstream failure','type':'api_error','code':'upstream_error'}}) + '\n\ndata: [DONE]\n\n'
            return httpx.Response(200, text=payload)
        payload = 'data: ' + json.dumps({'choices':[{'delta':{'content':'Recovered'}}]}) + '\n\ndata: [DONE]\n\n'
        return httpx.Response(200, text=payload)
    provider = OpenAICompatibleProvider()
    await provider.client.aclose()
    provider.client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(provider, '_retry_delay', lambda *_: 0.0)
    assert ''.join([piece async for piece in provider.stream(Settings(), [])]) == 'Recovered'
    assert attempts == 2
    await provider.close()


async def test_free_allowance_429_is_reported_as_usage_not_missing_key(monkeypatch):
    class Secrets:
        def key(self, _endpoint): return 'sk-xt-test-key-never-real'
    chat_attempts = 0
    def handle(request):
        nonlocal chat_attempts
        if request.url.path.endswith('/usage'):
            return httpx.Response(200, json={'free_tokens':{'used_today':1000,'limit_per_day':1000,'remaining':0}})
        if request.url.path.endswith('/chat/completions'):
            chat_attempts += 1
            return httpx.Response(429, headers={'Retry-After':'60'}, json={'error':{'message':'Rate limit exceeded','type':'rate_limit_error','code':'rate_limit_exceeded'}})
        return httpx.Response(404)
    provider = OpenAICompatibleProvider(Secrets())
    await provider.client.aclose()
    provider.client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(provider, '_retry_delay', lambda *_: 0.0)
    with pytest.raises(ProviderError) as captured:
        await provider.complete(Settings(llm_model='minimax/minimax-m3:free'), [])
    message = str(captured.value).lower()
    assert 'saved key' in message and 'allowance is exhausted' in message
    assert 'not configured' not in message and chat_attempts == 1
    await provider.close()


def test_secret_store_hot_cache_survives_later_file_read_failure(tmp_path, monkeypatch):
    from stonic.security.secrets import SecretStore
    store = SecretStore(tmp_path)
    store.path.write_bytes(b'encrypted-placeholder')
    monkeypatch.setattr(SecretStore, '_crypt', staticmethod(lambda raw, decrypt=False: b'sk-xt-cached-test-key'))
    endpoint = 'https://api.xkiro.com/v1'
    assert store.key(endpoint) == 'sk-xt-cached-test-key'
    store.path.unlink()
    assert store.key(endpoint) == 'sk-xt-cached-test-key'


def test_minimax_free_uses_only_supported_reasoning_values():
    provider = OpenAICompatibleProvider()
    settings = Settings(llm_model='minimax/minimax-m3:free')
    assert provider._latency_fields(settings) == {'reasoning_effort':'disabled'}
    assert provider._latency_fields(settings, planning=True) == {'reasoning_effort':'adaptive'}


def test_local_voice_pipeline_stays_retired_and_live_voice_is_authenticated(tmp_path):
    from fastapi.testclient import TestClient
    from stonic.app.api import create_app
    from stonic.config.settings import Configuration, Settings
    # The old local STT/TTS/VAD pipeline is still gone: none of its settings exist...
    assert not any(name in Configuration.RETIRED_SETTINGS or name.startswith('audio_') for name in Settings.model_fields)
    app = create_app(tmp_path, token='test-token')
    # ...while live voice is present and sits behind the same token as the rest of the API.
    assert any(getattr(route, 'path', '') == '/api/voice/status' for route in app.routes)
    with TestClient(app) as client:
        assert client.get('/api/voice/status').status_code == 401
        assert client.get('/api/voice/status', headers={'X-Stonic-Token': 'test-token'}).status_code == 200


async def test_staged_file_change_requires_new_approval_and_keeps_original_goal(tmp_path):
    from stonic.tools.workspace import FilePath
    class Planner:
        def __init__(self):self.calls=0
        def available(self,_):return True
        async def complete(self,*_):return 'Verified file change.'
        async def decide(self,settings,messages,tools,context):
            self.calls+=1
            if self.calls==1:
                return Decision(kind='plan',message='Inspect the requested file',steps=[{'id':'read','title':'Inspect file','tool':'files.read','arguments_json':json.dumps({'path':'note.txt'}),'depends_on':[]}])
            if self.calls==2:
                observed=core.workspace.read(FilePath(path='note.txt')).data
                return Decision(kind='plan',message='Apply the requested correction',steps=[{'id':'edit','title':'Correct file','tool':'files.write','arguments_json':json.dumps({'path':'note.txt','expected_sha256':observed['sha256'],'content':'after'}),'depends_on':[]}])
            return Decision(kind='answer',message='The requested file now contains after.',steps=[])
    db=Database(tmp_path/'db.sqlite')
    try:
        provider=Planner();core=CoreService(db,Configuration(db),Diagnostics(tmp_path),EventBus(db),provider)
        core.state.transition(__import__('stonic.core.models',fromlist=['Activity']).Activity.IDLE)
        target=core.workspace.root/'note.txt';target.write_text('before')
        await core.chat(ChatInput(content='Change note.txt to after.'))
        waiting=next(j for j in core.tasks.list() if j['status']=='waiting_approval')
        assert target.read_text()=='before' and waiting['stage']==2
        job=await core.tasks.decide(waiting['id'],waiting['approval']['id'],True)
        report=await core.advance(job)
        assert 'after' in report and target.read_text()=='after'
        assert len(core.tasks.list())==2
    finally:db.close()


def test_database_migrates_legacy_columns_and_recovers_corruption(tmp_path):
    import sqlite3
    from pathlib import Path
    db_path = tmp_path / "stonic.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE records (id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open')")
    conn.execute("INSERT INTO records VALUES ('legacy','notes','Legacy','kept','open')")
    conn.execute("PRAGMA user_version=2")
    conn.commit(); conn.close()
    db = Database(db_path)
    try:
        row = db.query("SELECT * FROM records WHERE id='legacy'")[0]
        assert row["created_at"] and row["updated_at"]
        assert db.query("PRAGMA user_version")[0]["user_version"] == 4
    finally:
        db.close()
    db_path.write_bytes(b"not a sqlite database")
    recovered = Database(db_path)
    try:
        assert recovered.recovery and Path(recovered.recovery["quarantined"]).is_file()
        assert recovered.query("PRAGMA user_version")[0]["user_version"] == 4
    finally:
        recovered.close()


def test_malformed_current_settings_fall_back_to_previous(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    try:
        valid = Settings().model_dump()
        db.execute("INSERT INTO settings(id,current,previous) VALUES(1,?,?)", ("{broken", json.dumps(valid)))
        config = Configuration(db)
        assert config.recovered is True
        assert config.values.llm_model == valid["llm_model"]
        assert json.loads(db.settings_rows()["current"])["llm_model"] == valid["llm_model"]
    finally:
        db.close()


def test_planner_routing_avoids_browser_noun_false_positive():
    assert CoreService.needs_planner("Explain browser architecture") is False
    assert CoreService.needs_planner("Open Chrome") is True
    assert CoreService.needs_planner("Chrome kholo") is True
    assert CoreService.is_live_web_request("Who is president of India?") is True


@pytest.mark.asyncio
async def test_normal_browser_question_uses_one_stream_path(tmp_path):
    class Provider:
        def __init__(self): self.decide_calls = 0; self.stream_calls = 0
        def available(self, _): return True
        async def decide(self, *args): self.decide_calls += 1; raise AssertionError("planner must not run for a normal browser question")
        async def stream(self, *_):
            self.stream_calls += 1
            yield "Browser architecture is a layered design."
    db = Database(tmp_path / "db.sqlite")
    provider = Provider()
    try:
        core = CoreService(db, Configuration(db), Diagnostics(tmp_path), EventBus(db), provider)
        core.state.transition(__import__('stonic.core.models', fromlist=['Activity']).Activity.IDLE)
        result = await core.chat(ChatInput(content="Explain browser architecture"))
        assert "layered design" in result["content"]
        assert provider.decide_calls == 0
        assert provider.stream_calls == 1
    finally:
        db.close()


def test_gif_is_normalized_for_vision(tmp_path):
    import base64, io
    from PIL import Image
    from stonic.providers.vision import Vision
    output = io.BytesIO()
    Image.new("RGBA", (2, 2), (255, 0, 0, 255)).save(output, format="GIF")
    encoded = "data:image/gif;base64," + base64.b64encode(output.getvalue()).decode()
    raw, fmt = Vision(None, tmp_path).decode(encoded)
    assert fmt == "GIF"
    with Image.open(io.BytesIO(raw)) as image:
        assert image.format == "PNG"


def test_steam_vdf_parser_handles_nested_libraries_and_escaped_paths():
    from stonic.tools.gaming import parse_vdf
    text = '''
    "libraryfolders"
    {
      "0" { "path" "C:\\\\Program Files (x86)\\\\Steam" }
      "1" { "path" "D:\\\\Games" "label" "Main Library" }
    }
    '''
    parsed = parse_vdf(text)
    assert parsed["libraryfolders"]["0"]["path"] == r"C:\Program Files (x86)\Steam"
    assert parsed["libraryfolders"]["1"]["label"] == "Main Library"


def test_windows_package_uses_correct_python_path_entry():
    from pathlib import Path
    package = Path(__file__).resolve().parents[1] / "scripts" / "package-windows.py"
    text = package.read_text(encoding="utf-8")
    assert "../.." in text and "import site" in text
    assert "../../..\\nimport site" not in text
