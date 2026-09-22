import asyncio
import json
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stonic.providers.llm import OpenAICompatibleProvider
from stonic.config.settings import Settings
from stonic.security.secrets import SecretStore

async def main():
    provider = OpenAICompatibleProvider(SecretStore(Path("data")))
    settings = Settings()
    try:
        response = await provider.client.post(f"{settings.llm_base_url}/chat/completions", headers=provider.headers(settings), json={
            "model": settings.llm_model, "messages": [{"role": "user", "content": "Search the web for official xKiro structured-output documentation."}],
            "tools": [{"type": "browser_search"}], "tool_choice": "required", "reasoning_effort": "low"})
        print("HTTP", response.status_code)
        data = response.json()
        if response.is_error:
            print(re.sub(r"gsk_[A-Za-z0-9_]+", "[redacted]", json.dumps(data.get("error", {})))[:1200])
        else:
            message = data["choices"][0]["message"]
            print("Message fields:", list(message))
            for tool in message.get("executed_tools") or []:
                print("Tool fields:", list(tool))
                print("Search result fields:", list(tool.get("search_results") or {}))
    finally:
        await provider.close()

asyncio.run(main())
