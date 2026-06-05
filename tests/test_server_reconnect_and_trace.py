"""Server reconnect safety (C5) + agent-rail history replay route (C7).

C5: a run's frame queue is a single destructive stream, so once a consumer has
started draining, a reconnect (e.g. after a mid-stream disconnect) must be
REJECTED rather than draining the residual queue and showing a partial view.

C7: GET /api/runs/{id}/trace serves the on-disk agents_trace.json ``agents``
list verbatim so a reopened run can rebuild the rail without re-running.

In-process TestClient (no real port), matching server/_smoke.py.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from server.app import app, manager
from structure_optimizer.core.run_store import read_json

EXPECTED_AGENT_ORDER = [
    "problem_definition",
    "mesh",
    "optimizer",
    "convergence_gate",
    "persistence",
    "verification",
    "export_report",
]


def _start(client: TestClient) -> str:
    return client.post("/api/runs", json={"benchmark_id": "simple_bracket", "preset": "smoke"}).json()["run_id"]


def _drain(client: TestClient, run_id: str) -> None:
    with client.websocket_connect(f"/api/runs/{run_id}/stream") as ws:
        while True:
            frame = ws.receive_json()
            if frame["type"] in ("done", "error"):
                return


def test_reconnect_after_disconnect_is_rejected() -> None:
    """C5: a second consumer (reconnect after a mid-stream disconnect) is rejected
    and pointed at the REST endpoints — it does NOT drain the residual queue."""
    client = TestClient(app)
    run_id = _start(client)

    # First consumer takes one frame, then disconnects (context exit).
    with client.websocket_connect(f"/api/runs/{run_id}/stream") as ws:
        first = ws.receive_json()
        assert first["type"] in ("stage", "iteration", "done")

    # Reconnect: must be rejected (consumed latched), not a partial residual drain.
    with client.websocket_connect(f"/api/runs/{run_id}/stream") as ws2:
        rejected = ws2.receive_json()
    assert rejected["type"] == "error"
    assert "consumed" in rejected["message"].lower()


def test_late_consumer_after_finish_is_rejected() -> None:
    """C5: connecting after the stream finished is also rejected (not re-drained)."""
    client = TestClient(app)
    run_id = _start(client)
    _drain(client, run_id)
    with client.websocket_connect(f"/api/runs/{run_id}/stream") as ws:
        rejected = ws.receive_json()
    assert rejected["type"] == "error"


def test_trace_route_matches_on_disk_agents_trace() -> None:
    """C7: GET /trace returns the on-disk agents[] verbatim, in pipeline order."""
    client = TestClient(app)
    run_id = _start(client)
    _drain(client, run_id)

    resp = client.get(f"/api/runs/{run_id}/trace")
    assert resp.status_code == 200, resp.text
    agents = resp.json()
    assert [a["name"] for a in agents] == EXPECTED_AGENT_ORDER

    state = manager.get(run_id)
    assert state is not None and state.run_dir is not None
    disk = read_json(state.run_dir / "agents_trace.json")["agents"]
    assert agents == disk  # served verbatim


def test_trace_route_unknown_run_404() -> None:
    client = TestClient(app)
    assert client.get("/api/runs/does-not-exist/trace").status_code == 404
