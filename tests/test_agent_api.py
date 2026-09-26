"""API smoke tests for the new V3 agent endpoints: goals, lessons, skills, kill switch."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stonic.app.api import create_app

TOKEN = "agent-api-token"


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Path(tmp_path), TOKEN), headers={"X-Stonic-Token": TOKEN}) as c:
        yield c


def test_agent_goals_list_and_missing_goal_404(client):
    assert client.get("/api/agent/goals").json() == []
    assert client.get("/api/agent/goals/does-not-exist").status_code == 404


def test_agent_lessons_lifecycle(client):
    core = client.app.state.core
    saved = core.agent_memory.save_lesson("Always check disk space first.", source="agent", status="pending")
    assert client.get("/api/agent/lessons", params={"status": "pending"}).json()[0]["id"] == saved["id"]
    response = client.post(f"/api/agent/lessons/{saved['id']}/decision", json={"approved": True})
    assert response.status_code == 200
    assert client.get("/api/agent/lessons", params={"status": "active"}).json()[0]["id"] == saved["id"]
    assert client.delete(f"/api/agent/lessons/{saved['id']}").status_code == 200
    assert client.delete(f"/api/agent/lessons/{saved['id']}").status_code == 404


def test_agent_skills_propose_needs_a_real_goal(client):
    response = client.post("/api/agent/skills/propose", json={"goal_id": "nope", "name": "test skill"})
    assert response.status_code == 404


def test_agent_skills_propose_from_a_real_goal_then_approve(client):
    core = client.app.state.core
    core.agent_store.save_goal("g1", None, "s1", "back up notes", "completed", "ask_on_risk",
                               {"messages": [], "steps": [{"tool": "files.write", "arguments": {"path": "a.txt", "content": "x"}, "status": "completed"}]})
    proposed = client.post("/api/agent/skills/propose", json={"goal_id": "g1", "name": "backup notes"})
    assert proposed.status_code == 200 and proposed.json()["status"] == "pending"
    identifier = proposed.json()["id"]
    assert client.post(f"/api/agent/skills/{identifier}/decision", json={"approved": True}).status_code == 200
    assert client.get("/api/agent/skills", params={"status": "active"}).json()[0]["id"] == identifier
    assert client.delete(f"/api/agent/skills/{identifier}").status_code == 200


def test_agent_stop_marks_running_and_waiting_goals_stopped(client):
    core = client.app.state.core
    core.agent_store.save_goal("g1", None, "s1", "goal one", "running", "ask_on_risk", {"messages": [], "steps": [], "pending_calls": []})
    core.agent_store.save_goal("g2", None, "s1", "goal two", "waiting_approval", "ask_on_risk", {"messages": [], "steps": [], "pending_calls": [{"id": "c1"}]})
    core.agent_store.save_goal("g3", None, "s1", "goal three", "completed", "ask_on_risk", {"messages": [], "steps": []})
    response = client.post("/api/agent/stop")
    assert response.status_code == 200
    assert set(response.json()["stopped_goals"]) == {"g1", "g2"}
    assert core.agent_store.load_goal("g1")["status"] == "stopped"
    assert core.agent_store.load_goal("g2")["payload"]["pending_calls"] == []
    assert core.agent_store.load_goal("g3")["status"] == "completed"


def test_agent_goal_decision_requires_boolean(client):
    response = client.post("/api/agent/goals/whatever/decision", json={"approved": "yes"})
    assert response.status_code == 422


def test_agent_goal_detail_includes_confirm_preview_when_waiting(client):
    core = client.app.state.core
    core.agent_store.save_goal("g1", None, "s1", "write hi", "waiting_approval", "ask_on_risk",
                               {"messages": [{"role": "system", "content": "x"}, {"role": "user", "content": "write hi"}],
                                "steps": [], "pending_calls": [{"id": "c1", "name": "files.write", "arguments": {"path": "a.txt", "content": "hi"}}]})
    detail = client.get("/api/agent/goals/g1").json()
    assert detail["confirm"][0]["tool"] == "files.write"
