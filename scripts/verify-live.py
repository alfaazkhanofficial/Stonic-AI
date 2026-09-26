"""Bounded live acceptance using the configured key; prints no credentials or private content."""
import asyncio
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stonic.config.settings import Configuration, Settings
from stonic.core.models import Activity, ChatInput
from stonic.core.service import CoreService
from stonic.diagnostics.health import Diagnostics
from stonic.events.bus import EventBus
from stonic.providers.llm import OpenAICompatibleProvider
from stonic.providers.web import ResearchRequest
from stonic.security.secrets import SecretStore
from stonic.storage.database import Database


async def main():
    root = Path(__file__).resolve().parents[1]
    (root / ".runtime").mkdir(parents=True, exist_ok=True)
    provider = OpenAICompatibleProvider(SecretStore(root / "data"))
    with tempfile.TemporaryDirectory(prefix="live-", dir=root / ".runtime") as temporary:
        directory = Path(temporary)
        db = Database(directory / "acceptance.db")
        try:
            config = Configuration(db)
            core = CoreService(db, config, Diagnostics(directory), EventBus(db), provider)
            core.state.transition(Activity.IDLE)
            check = await provider.check(config.values)
            if check.status == "unconfigured":
                print(f"SKIP: live acceptance requires provider setup. {check.detail}", flush=True)
                return
            if check.status != "ready":
                raise RuntimeError(check.detail)
            print("PASS: xKiro connection and configured model", flush=True)
            result = await core.chat(ChatInput(session_id="acceptance", content="Create a workspace file named acceptance.txt containing exactly STONIC_VERIFIED. This is an isolated acceptance test. Use the file tool."))
            jobs = core.tasks.list()
            assert jobs and jobs[0]["status"] == "waiting_approval", "Expected a real planned action paused for approval"
            job = jobs[0]
            assert job["approval"]["action"] == "files.write"
            assert Path(job["approval"]["arguments"]["path"]).resolve() == directory / "documents" / "acceptance.txt"
            assert not (directory / "documents" / "acceptance.txt").exists()
            completed = await core.tasks.decide(job["id"], job["approval"]["id"], True)
            assert completed["status"] == "completed"
            assert (directory / "documents" / "acceptance.txt").read_text().strip() == "STONIC_VERIFIED"
            print("PASS: xKiro plan -> exact review -> approved file action -> disk verification", flush=True)
            research = await core.web.research(ResearchRequest(query="Find the official xKiro documentation for structured output and summarize the supported JSON response mode.", domains=["docs.xkiro.com"]))
            if not research.success:
                raise ValueError(f"Web acceptance failed: {research.message} ({research.error})")
            assert research.data["sources"]
            print(f"PASS: Live web research returned {len(research.data['sources'])} source URLs", flush=True)
            visible = core.computer.windows()
            assert visible.success
            print(f"PASS: Native Windows adapter inspected {len(visible.data['windows'])} visible windows", flush=True)
        finally:
            await provider.close()
            db.close()


if __name__ == "__main__":
    asyncio.run(main())
