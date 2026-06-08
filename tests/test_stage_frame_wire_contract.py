"""Wire-level contract for the live agent-rail ``stage`` frames.

The engine-level "live == disk" guarantee is covered by
``tests/test_on_stage_byte_repro.py::test_live_stage_records_equal_on_disk_trace``.
This test closes the gap one layer up: it drives the REAL server path —
``POST /api/runs`` → drain ``WS /api/runs/{id}/stream`` → collect ``stage``
frames — and proves the frames that actually travel over the WebSocket equal the
run's on-disk ``agents_trace.json`` (each minus the nondeterministic ``wall_ms``),
so a future ``server/`` refactor cannot silently break the wire contract.

Uses FastAPI's in-process ``TestClient`` (no real port bound), matching
``server/_smoke.py``.
"""

from __future__ import annotations

import pytest

# The server wire layer lives in the optional ``[web]`` extra. Skip gracefully in
# the engine-only env (matches the repo's importorskip convention).
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from server.app import app, manager
from server.schemas import StageFrame
from structure_optimizer.core.run_store import read_json

# Canonical pipeline order (the six domain agents + the internal persistence step),
# exactly as PipelineOrchestrator._stages runs them.
EXPECTED_AGENT_ORDER = [
    "problem_definition",
    "mesh",
    "optimizer",
    "convergence_gate",
    "persistence",
    "verification",
    "export_report",
]


def _strip_wall_ms(record: dict) -> dict:
    return {k: v for k, v in record.items() if k != "wall_ms"}


def test_ws_stage_frames_match_on_disk_trace() -> None:
    client = TestClient(app)

    start = client.post("/api/runs", json={"benchmark_id": "simple_bracket", "preset": "smoke"}).json()
    run_id = start["run_id"]

    stage_frames: list[dict] = []
    saw_done = False
    with client.websocket_connect(f"/api/runs/{run_id}/stream") as ws:
        while True:
            frame = ws.receive_json()
            if frame["type"] == "stage":
                stage_frames.append(frame)
            elif frame["type"] == "done":
                saw_done = True
                break
            elif frame["type"] == "error":
                pytest.fail(f"unexpected error frame over the wire: {frame['message']}")

    assert saw_done, "stream ended without a done frame"
    assert stage_frames, "no stage frames arrived over the WebSocket"

    # (a) every stage frame validates against the published wire model, and
    #     declared_tools round-trips as a list (not a tuple/str).
    for frame in stage_frames:
        model = StageFrame(**frame)  # raises on contract drift
        assert model.phase in ("start", "end", "error")
        if model.record is not None:
            assert isinstance(model.record.declared_tools, list)

    starts = [f for f in stage_frames if f["phase"] == "start"]
    ends = [f for f in stage_frames if f["phase"] == "end"]
    assert [f["agent"] for f in starts] == EXPECTED_AGENT_ORDER
    assert [f["agent"] for f in ends] == EXPECTED_AGENT_ORDER
    assert not [f for f in stage_frames if f["phase"] == "error"]

    # (b) the ordered end records (over the wire) equal the on-disk trace, modulo
    #     the nondeterministic wall_ms. run_dir is set before the done frame.
    state = manager.get(run_id)
    assert state is not None and state.run_dir is not None
    disk_agents = read_json(state.run_dir / "agents_trace.json")["agents"]

    wire_end_records = [f["record"] for f in ends]
    assert [_strip_wall_ms(r) for r in wire_end_records] == [_strip_wall_ms(r) for r in disk_agents]
