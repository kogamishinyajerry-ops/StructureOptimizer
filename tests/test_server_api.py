"""HTTP coverage for the previously-untested read-only server REST endpoints.

``test_server_reconnect_and_trace.py`` covers POST /runs, the WS stream, and
GET /trace (happy + unknown-run 404); ``test_server_export.py`` covers
GET /export. That left the rest of the REST surface untested:

  * GET /api/health
  * GET /api/benchmarks                  (list shape + membership + ordering)
  * GET /api/benchmarks/{id}/config      (200 + 404 unknown + 404 excluded)
  * GET /api/runs                        (history list, finished run visible)
  * GET /api/runs/{id}                   (200 / 404 / 409 not-finished / 500 error)
  * GET /api/runs/{id}/trace             (409 not-finished — complements the 404)

Happy paths drive a single real ``simple_bracket`` ``smoke`` run end-to-end
(NumPy/stdlib only, so this passes in every CI matrix cell). The 409/500 error
branches inject a synthetic ``RunState`` into the app-global ``manager`` instead
of racing to catch a live run mid-flight: a fresh ``RunState`` is
``status="running"`` with ``run_dir=None`` (the exact "not finished"
precondition), and ``status="error"`` drives the 500 path in both of its real
shapes — ``run_dir=None`` (run_config raised) and ``run_dir`` set (post-read
failed) — since the handler checks error BEFORE not-finished. Each injected id is
removed in a ``finally`` block so the singleton is not polluted across tests.

In-process ``TestClient`` (no real port), matching the sibling server tests.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from server.app import app, manager
from server.runner import RunState

# Auto-discovered from configs/*.json this session — must surface in the picker.
NEW_BENCHMARKS = {"bridge", "turbine_blade", "wing_spar"}
# Heavy meshes the workbench hides from the interactive list (server/app.py _EXCLUDED).
EXCLUDED = {"large_cantilever", "xlarge_cantilever"}


def _start(client: TestClient) -> str:
    resp = client.post("/api/runs", json={"benchmark_id": "simple_bracket", "preset": "smoke"})
    assert resp.status_code == 200, resp.text
    return resp.json()["run_id"]


def _drain(client: TestClient, run_id: str) -> None:
    """Drain the single destructive frame stream to completion (one consumer)."""
    with client.websocket_connect(f"/api/runs/{run_id}/stream") as ws:
        while ws.receive_json()["type"] not in ("done", "error"):
            pass


@contextlib.contextmanager
def _injected(state: RunState) -> Iterator[RunState]:
    """Register a synthetic run state in the app-global manager, then remove it."""
    with manager._lock:
        manager._runs[state.run_id] = state
        manager._order.append(state.run_id)
    try:
        yield state
    finally:
        with manager._lock:
            manager._runs.pop(state.run_id, None)
            if state.run_id in manager._order:
                manager._order.remove(state.run_id)


@pytest.fixture(scope="module")
def finished_run_id() -> str:
    """One real smoke run, drained to ``done`` — visible to any TestClient(app)."""
    client = TestClient(app)
    run_id = _start(client)
    _drain(client, run_id)
    state = manager.get(run_id)
    assert state is not None and state.status == "done", "smoke run did not finish"
    return run_id


# --- GET /api/health -------------------------------------------------------- #


def test_health_ok() -> None:
    resp = TestClient(app).get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# --- GET /api/benchmarks ---------------------------------------------------- #


def test_list_benchmarks_shape_membership_ordering() -> None:
    resp = TestClient(app).get("/api/benchmarks")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert isinstance(items, list) and items, "benchmark list is empty"

    sample = items[0]
    for field in ("id", "label", "nelx", "nely", "volume_fraction", "max_iterations", "presets", "recommended"):
        assert field in sample, f"BenchmarkSummary missing '{field}'"
    assert isinstance(sample["presets"], list)
    assert isinstance(sample["recommended"], bool)

    ids = {it["id"] for it in items}
    assert ids >= NEW_BENCHMARKS, f"missing new benchmarks: {NEW_BENCHMARKS - ids}"
    assert not (EXCLUDED & ids), f"excluded benchmarks leaked: {EXCLUDED & ids}"

    # app.py sorts on (not recommended, id) -> recommended entries come first.
    flags = [it["recommended"] for it in items]
    assert flags == sorted(flags, reverse=True), "recommended benchmarks not sorted first"


# --- GET /api/benchmarks/{id}/config ---------------------------------------- #


def test_benchmark_config_200() -> None:
    resp = TestClient(app).get("/api/benchmarks/simple_bracket/config")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["benchmark_id"] == "simple_bracket"
    assert {"volume_fraction", "penalty", "filter_radius", "max_iterations"} <= body["optimization"].keys()
    assert {"nelx", "nely"} <= body["mesh"].keys()
    assert isinstance(body["loads_editable"], bool)
    assert isinstance(body["selectors"], list) and body["selectors"]
    assert {"nelx_max", "nely_max", "elements_max", "max_iterations_max"} <= body["limits"].keys()


def test_benchmark_config_unknown_404() -> None:
    resp = TestClient(app).get("/api/benchmarks/does-not-exist/config")
    assert resp.status_code == 404


def test_benchmark_config_excluded_404() -> None:
    # Discoverable by the registry but hidden by the workbench -> treated as unknown.
    resp = TestClient(app).get("/api/benchmarks/large_cantilever/config")
    assert resp.status_code == 404


# --- GET /api/runs ---------------------------------------------------------- #


def test_list_runs_includes_finished(finished_run_id: str) -> None:
    resp = TestClient(app).get("/api/runs")
    assert resp.status_code == 200, resp.text
    runs = {r["run_id"]: r for r in resp.json()}
    assert finished_run_id in runs, "finished run missing from history list"
    item = runs[finished_run_id]
    assert item["status"] == "done"
    assert item["benchmark_id"] == "simple_bracket"
    assert isinstance(item["verified"], bool)  # done run -> verified resolved to a bool


# --- GET /api/runs/{id} ----------------------------------------------------- #


def test_get_run_200(finished_run_id: str) -> None:
    resp = TestClient(app).get(f"/api/runs/{finished_run_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run_id"] == finished_run_id
    assert body["status"] == "done"
    assert body["summary"] and body["verification"]
    assert len(body["shape"]) == 2 and body["density_b64"]


def test_get_run_unknown_404() -> None:
    resp = TestClient(app).get("/api/runs/does-not-exist")
    assert resp.status_code == 404


def test_get_run_not_finished_409() -> None:
    state = RunState(run_id="synthetic-running", benchmark_id="simple_bracket", nelx=4, nely=4)
    # default: status="running", run_dir=None -> the "not finished" precondition
    with _injected(state):
        resp = TestClient(app).get(f"/api/runs/{state.run_id}")
    assert resp.status_code == 409


def test_get_run_errored_no_rundir_500(tmp_path: Path) -> None:
    # The REAL worker-error shape: run_config() raised, so the runner's except
    # clause set status="error" while run_dir was NEVER assigned (stays None).
    # The handler must check error BEFORE not-finished, else this is masked as a
    # misleading 409 and the engine message is dropped (regression guard).
    state = RunState(run_id="synthetic-real-error", benchmark_id="simple_bracket", nelx=4, nely=4)
    state.status = "error"
    state.error = "engine boom"  # run_dir intentionally left None
    with _injected(state):
        resp = TestClient(app).get(f"/api/runs/{state.run_id}")
    assert resp.status_code == 500
    assert "engine boom" in resp.json()["detail"]  # diagnostic surfaced, not discarded


def test_get_run_errored_with_rundir_500(tmp_path: Path) -> None:
    # The rarer error shape: run_config() succeeded but post-read failed, so
    # status="error" WITH run_dir set. Must also be 500 (not silently served).
    state = RunState(run_id="synthetic-error", benchmark_id="simple_bracket", nelx=4, nely=4)
    state.status = "error"
    state.run_dir = tmp_path
    state.error = "synthetic boom"
    with _injected(state):
        resp = TestClient(app).get(f"/api/runs/{state.run_id}")
    assert resp.status_code == 500


# --- GET /api/runs/{id}/trace (409 complements the existing 404) ------------ #


def test_get_trace_not_finished_409() -> None:
    state = RunState(run_id="synthetic-running-trace", benchmark_id="simple_bracket", nelx=4, nely=4)
    with _injected(state):  # run_dir is None -> "not finished"
        resp = TestClient(app).get(f"/api/runs/{state.run_id}/trace")
    assert resp.status_code == 409
