"""Wire-level contract for the live ``iteration`` and ``done`` frames.

``tests/test_stage_frame_wire_contract.py`` proves the agent-rail ``stage``
frames match the on-disk trace, but it only validates ``StageFrame`` — when it
reaches the terminal ``done`` frame it simply breaks. That left the two frame
types the React client *actually* consumes for live telemetry — the per-iteration
optimizer-progress frame and the completion frame — with a published Pydantic
contract (``IterationFrame`` / ``DoneFrame`` in ``server/schemas.py``) that no
test validates against the dicts the runner emits.

This drives the REAL server path — ``POST /api/runs`` → drain
``WS /api/runs/{id}/stream`` → collect ``iteration`` + ``done`` frames — and
proves (a) every frame validates against its published model, (b) ordering
(iterations precede done, iteration index is non-decreasing), and (c) the done
frame agrees with the persisted ``summary.json``. A future ``server/runner.py``
refactor that drifts the wire dict from the schema, or from disk, is then caught.

Uses FastAPI's in-process ``TestClient`` (no real port bound), matching
``server/_smoke.py`` and the sibling server tests.
"""

from __future__ import annotations

import pytest

# The server wire layer lives in the optional ``[web]`` extra. Skip gracefully in
# the engine-only env (matches the repo's importorskip convention).
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from server.app import app, manager
from server.schemas import DoneFrame, IterationFrame
from structure_optimizer.core.run_store import read_json


def test_ws_iteration_and_done_frames_match_contract_and_disk() -> None:
    client = TestClient(app)

    start = client.post("/api/runs", json={"benchmark_id": "simple_bracket", "preset": "smoke"}).json()
    run_id = start["run_id"]

    iteration_frames: list[dict] = []
    done_frame: dict | None = None
    with client.websocket_connect(f"/api/runs/{run_id}/stream") as ws:
        while True:
            frame = ws.receive_json()
            ftype = frame["type"]
            if ftype == "iteration":
                iteration_frames.append(frame)
            elif ftype == "done":
                done_frame = frame
                break
            elif ftype == "error":
                pytest.fail(f"unexpected error frame over the wire: {frame['message']}")
            # ``stage`` frames (the agent rail) are validated by the sibling test;
            # ignore them here.

    # (a) the terminal frame arrived and at least one progress frame preceded it.
    assert done_frame is not None, "stream ended without a done frame"
    assert iteration_frames, "no iteration frames arrived over the WebSocket"

    # (b) every frame validates against its published wire model — raises on
    #     contract drift, exactly as StageFrame(**frame) does for the stage rail.
    for frame in iteration_frames:
        model = IterationFrame(**frame)  # raises on contract drift
        assert isinstance(model.shape, list) and len(model.shape) == 2  # [nely, nelx]
        assert model.density_b64
    done = DoneFrame(**done_frame)  # raises on contract drift

    # (c) ordering: the iteration index is non-decreasing across the stream.
    indices = [f["iteration"] for f in iteration_frames]
    assert indices == sorted(indices), f"iteration indices not monotonic: {indices}"

    # (d) the done frame agrees with the persisted summary.json (run_dir is set
    #     before the done frame is emitted), so a runner that drifts the wire
    #     payload from disk is caught.
    state = manager.get(run_id)
    assert state is not None and state.run_dir is not None
    summary = read_json(state.run_dir / "summary.json")
    assert done.stop_reason == summary["stop_reason"]
    assert done.iterations == int(summary["iterations"])
    assert done.run_id == run_id
