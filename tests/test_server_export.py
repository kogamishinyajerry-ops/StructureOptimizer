"""HTTP coverage for ``GET /api/runs/{run_id}/export`` — the workbench's
"download geometry" button (SVG / DXF / STL).

The CLI ``export`` path is smoke-tested in CI, but the HTTP endpoint had zero
coverage. This drives each format end-to-end through a real (in-process) run and
asserts the attachment response, plus the deterministic error paths (bad format,
unknown run, out-of-range query params).

``server/export.py`` writes SVG/DXF/STL with NumPy/stdlib only (no meshio/scipy),
so these pass in every CI matrix cell — including the NumPy-only ``vanilla``
cells. In-process ``TestClient`` (no real port), matching
``test_server_reconnect_and_trace.py``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from server.app import app, manager
from server.export import EXPORT_FORMATS

# format -> (filename extension, content-type prefix)
_EXT_MIME = {
    "svg": ("svg", "image/svg+xml"),
    "dxf": ("dxf", "application/dxf"),
    "stl": ("stl", "model/stl"),
}


@pytest.fixture(scope="module")
def finished_run_id() -> str:
    """Start one real ``simple_bracket`` smoke run, drain it to completion, and
    return its id. The manager is an app-global singleton, so the finished run is
    visible to any ``TestClient(app)`` the tests construct."""
    client = TestClient(app)
    run_id = client.post("/api/runs", json={"benchmark_id": "simple_bracket", "preset": "smoke"}).json()["run_id"]
    with client.websocket_connect(f"/api/runs/{run_id}/stream") as ws:
        while ws.receive_json()["type"] not in ("done", "error"):
            pass
    return run_id


@pytest.mark.parametrize("fmt", sorted(EXPORT_FORMATS))
def test_export_format_downloads_attachment(fmt: str, finished_run_id: str) -> None:
    client = TestClient(app)
    resp = client.get(f"/api/runs/{finished_run_id}/export", params={"format": fmt})
    assert resp.status_code == 200, resp.text
    assert resp.content, "export body is empty"
    disposition = resp.headers["content-disposition"]
    ext, mime = _EXT_MIME[fmt]
    assert "attachment" in disposition
    assert disposition.endswith(f'.{ext}"'), disposition
    assert resp.headers["content-type"].startswith(mime)


def test_export_defaults_to_svg(finished_run_id: str) -> None:
    """No ``format`` query param defaults to SVG (endpoint default)."""
    client = TestClient(app)
    resp = client.get(f"/api/runs/{finished_run_id}/export")
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].endswith('.svg"')


def test_export_unknown_format_400() -> None:
    """``format`` is validated before the run lookup, so a bad format is a 400
    even for an otherwise-unknown run."""
    client = TestClient(app)
    resp = client.get("/api/runs/whatever/export", params={"format": "png"})
    assert resp.status_code == 400
    assert "png" in resp.json()["detail"]


def test_export_unknown_run_404() -> None:
    client = TestClient(app)
    resp = client.get("/api/runs/does-not-exist/export", params={"format": "svg"})
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "params",
    [
        {"format": "svg", "threshold": "1.5"},  # threshold le=1.0
        {"format": "svg", "threshold": "-0.1"},  # threshold ge=0.0
        {"format": "svg", "extrusion_depth": "0"},  # extrusion_depth gt=0.0
    ],
)
def test_export_out_of_range_query_params_422(params: dict[str, str]) -> None:
    """FastAPI ``Query`` bounds reject out-of-range params with 422 before the
    handler runs (so an unknown run still yields 422, not 404)."""
    client = TestClient(app)
    resp = client.get("/api/runs/does-not-exist/export", params=params)
    assert resp.status_code == 422


def test_export_corrupt_artifacts_409() -> None:
    """A finished run whose on-disk artifacts are corrupt/truncated (here a
    half-written input.json) degrades to 409 'Run artifacts are incomplete' —
    matching get_run / get_run_trace — instead of a raw 500 with a stack trace.

    Uses a dedicated run (not the shared ``finished_run_id`` fixture) so the
    corruption does not leak into the other tests.
    """
    client = TestClient(app)
    run_id = client.post("/api/runs", json={"benchmark_id": "simple_bracket", "preset": "smoke"}).json()["run_id"]
    with client.websocket_connect(f"/api/runs/{run_id}/stream") as ws:
        while ws.receive_json()["type"] not in ("done", "error"):
            pass
    state = manager.get(run_id)
    assert state is not None and state.run_dir is not None
    (state.run_dir / "input.json").write_text("{ truncated")  # JSONDecodeError(ValueError)

    resp = client.get(f"/api/runs/{run_id}/export", params={"format": "svg"})
    assert resp.status_code == 409, resp.text
    assert "incomplete" in resp.json()["detail"].lower()
