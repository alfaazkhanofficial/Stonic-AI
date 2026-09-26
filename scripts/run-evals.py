"""Print the V3 evaluation report (JSON). Usage: python scripts/run-evals.py [--fail-on-failed]"""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.evals.harness import run_scenario, summarize  # noqa: E402
from tests.evals.scenarios import SCENARIOS  # noqa: E402


async def main() -> int:
    base = Path(tempfile.mkdtemp(prefix="stonic-evals-"))
    results = [await run_scenario(s, base / s.id) for s in SCENARIOS]
    report = summarize(results)
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))
    for r in report["results"]:
        print(f"{r['status']:8} {r['workstream']} {r['id']:44} {r['reason']}")
    return 1 if "--fail-on-failed" in sys.argv and report["failed"] else 0


raise SystemExit(asyncio.run(main()))
