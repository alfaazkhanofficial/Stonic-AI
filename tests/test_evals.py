import pytest

from tests.evals.harness import run_scenario, summarize
from tests.evals.scenarios import BASELINE, SCENARIOS


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", BASELINE, ids=lambda s: s.id)
async def test_baseline_scenario_passes(scenario, tmp_path):
    result = await run_scenario(scenario, tmp_path)
    assert result.status == "passed", result.reason


@pytest.mark.asyncio
async def test_pending_scenarios_are_reported_not_faked(tmp_path):
    results = [await run_scenario(s, tmp_path / s.id) for s in SCENARIOS]
    report = summarize(results)
    assert report["failed"] == 0
    assert report["pending"] == len(SCENARIOS) - len(BASELINE)
    assert all(r["status"] == "pending" and r["reason"].startswith("needs V3-P") for r in report["results"] if r["required_phase"] != "baseline")


@pytest.mark.asyncio
async def test_harness_detects_failures(tmp_path):
    from dataclasses import replace
    broken = replace(BASELINE[0], check=lambda _c, _r: "forced failure")
    assert (await run_scenario(broken, tmp_path / "a")).status == "failed"
    missing = replace(BASELINE[0], expect_tools=["files.delete"])
    assert (await run_scenario(missing, tmp_path / "b")).status == "failed"
    over_budget = replace(BASELINE[0], max_decisions=1)
    assert (await run_scenario(over_budget, tmp_path / "c")).status == "failed"
