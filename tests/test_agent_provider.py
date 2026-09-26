import json

import httpx
import pytest
from pydantic import BaseModel, Field

from stonic.agent.router import ModelRouter
from stonic.config.settings import Settings
from stonic.providers.llm import OpenAICompatibleProvider, ProviderError, simplify_schema, tool_name, wire_name


class Inner(BaseModel):
    kind: str = Field(pattern="^[a-z]+$", max_length=10)


class Args(BaseModel):
    path: str = Field(min_length=1, description="Where")
    inner: Inner
    limit: int | None = Field(default=None, ge=1, le=9)
    mode: str = "a"


def provider_with(handler):
    provider = OpenAICompatibleProvider()
    provider.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return provider


def test_wire_names_round_trip():
    assert wire_name("files.recovery.list") == "files__recovery__list"
    assert tool_name("files__recovery__list") == "files.recovery.list"


def test_schema_is_flattened_for_openai_compatible_endpoints():
    schema = simplify_schema(Args.model_json_schema())
    text = json.dumps(schema)
    assert "$ref" not in text and "$defs" not in text and "anyOf" not in text and "title" not in text
    assert schema["properties"]["inner"]["properties"]["kind"]["type"] == "string"
    assert schema["properties"]["limit"]["type"] == "integer"
    assert schema["required"] == ["path", "inner"]


@pytest.mark.asyncio
async def test_act_sends_native_tools_and_parses_calls_keeping_provider_fields():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers.get("authorization"), json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [
            {"id": "c1", "type": "function", "extra_content": {"google": {"thought_signature": "sig"}},
             "function": {"name": "files__read", "arguments": "{\"path\": \"a.txt\"}"}},
            {"function": {"name": "system__status", "arguments": "not json"}}]}}],
            "usage": {"prompt_tokens": 30, "completion_tokens": 5}})

    provider = provider_with(handler)
    provider.resolvers["https://generativelanguage.googleapis.com/v1beta/openai"] = lambda: "gem-key"
    settings = Settings(llm_base_url="https://generativelanguage.googleapis.com/v1beta/openai", llm_model="gemini-3.5-flash-lite")
    result = await provider.act(settings, [{"role": "user", "content": "hi"}],
                                [{"name": "files.read", "description": "Read", "arguments": Args.model_json_schema()}], reasoning="low")
    body = seen["body"]
    assert seen["auth"] == "Bearer gem-key" and seen["url"].endswith("/openai/chat/completions")
    assert body["tools"][0]["function"]["name"] == "files__read" and body["reasoning_effort"] == "low"
    assert "temperature" not in body                      # Gemini deprecated sampling parameters
    assert result["tool_calls"][0] == {"id": "c1", "name": "files.read", "arguments": {"path": "a.txt"}}
    assert result["tool_calls"][1]["arguments"] is None and result["tool_calls"][1]["id"]
    assert result["assistant_message"]["tool_calls"][0]["extra_content"]["google"]["thought_signature"] == "sig"
    assert result["usage"]["total_tokens"] == 35
    await provider.close()


@pytest.mark.asyncio
async def test_act_retries_without_reasoning_effort_when_rejected():
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append("reasoning_effort" in body)
        if "reasoning_effort" in body:
            return httpx.Response(400, json={"error": {"message": "unknown field reasoning_effort"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "done"}}], "usage": {"total_tokens": 4}})

    provider = provider_with(handler)
    provider.resolvers["https://generativelanguage.googleapis.com/v1beta/openai"] = lambda: "k"
    settings = Settings(llm_base_url="https://generativelanguage.googleapis.com/v1beta/openai", llm_model="gemini-3.5-flash-lite")
    result = await provider.act(settings, [{"role": "user", "content": "x"}], [], reasoning="medium")
    assert calls == [True, False] and result["content"] == "done" and not result["tool_calls"]
    await provider.close()


@pytest.mark.asyncio
async def test_act_reports_invalid_contract():
    provider = provider_with(lambda r: httpx.Response(200, json={"nope": 1}))
    with pytest.raises(ProviderError):
        await provider.act(Settings(llm_base_url="http://127.0.0.1:1/v1", llm_model="local-model"), [], [])
    await provider.close()


def make_router(monkeypatch, *, key="gem", consent=True, xkiro=False):
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "XKIRO_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    if key:
        monkeypatch.setenv("GEMINI_API_KEY", key)
    if xkiro:
        monkeypatch.setenv("XKIRO_API_KEY", "xk-secret-key")
    return ModelRouter(OpenAICompatibleProvider()), Settings(agent_fast_consent=consent)


@pytest.mark.asyncio
async def test_router_uses_fast_for_steps_strong_for_recovery_and_registers_credentials(monkeypatch):
    router, settings = make_router(monkeypatch)
    step, reflect = router.route(settings, "step"), router.route(settings, "reflect")
    assert (step.profile, step.settings.llm_model, step.reasoning) == ("fast", "gemini-3.5-flash-lite", "low")
    assert (reflect.profile, reflect.settings.llm_model, reflect.reasoning) == ("strong", "gemini-3.6-flash", "medium")
    assert router.provider._credential(step.settings) == "gem"
    await router.provider.close()


@pytest.mark.asyncio
async def test_router_fallback_chain_and_consent_gate(monkeypatch):
    router, settings = make_router(monkeypatch, xkiro=True)
    assert router.route(settings, "step", skip=frozenset({"fast"})).profile == "strong"
    assert router.route(settings, "step", skip=frozenset({"fast", "strong"})).profile == "main"
    assert router.route(settings, "step", skip=frozenset({"fast", "strong", "main"})) is None
    no_consent = settings.model_copy(update={"agent_fast_consent": False})
    assert router.route(no_consent, "step").profile == "main"      # nothing leaves for Gemini without consent
    assert router.usable(no_consent)
    await router.provider.close()


@pytest.mark.asyncio
async def test_router_without_any_credentials_is_unusable(monkeypatch):
    router, settings = make_router(monkeypatch, key="", consent=True)
    assert router.route(settings, "step") is None and not router.usable(settings)
    await router.provider.close()
