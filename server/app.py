"""FastAPI app: benchmark listing, run start, live WS stream, final result.

Run locally::

    .venv/bin/python -m uvicorn server.app:app --reload --port 8000

The React dev server (Vite, port 5173) proxies ``/api`` here; CORS is also
enabled for direct cross-origin use during development.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from structure_optimizer.benchmarks.registry import (
    available_benchmarks,
    config_path,
    load_benchmark,
)
from structure_optimizer.core.run_store import load_density, read_json

from server.export import EXPORT_FORMATS, export_geometry
from server.frames import encode_density
from server.runner import SENTINEL, RunManager
from server.schemas import (
    BenchmarkSummary,
    RunResult,
    StartRunRequest,
    StartRunResponse,
)

app = FastAPI(title="StructureOptimizer Workbench API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = RunManager()

# Curated set that runs fast + renders cleanly as a compliance topology — shown
# first / flagged in the UI. Everything else is still listed.
_RECOMMENDED = {"mbb_beam", "cantilever", "l_bracket", "loaded_hook", "simple_bracket"}
# Large meshes excluded from the interactive workbench (too slow for live view).
_EXCLUDED = {"large_cantilever", "xlarge_cantilever"}

# Short human blurbs (engine configs carry no description field).
_BLURBS = {
    "mbb_beam": "Classic MBB beam — the canonical SIMP topology-optimization benchmark.",
    "cantilever": "End-loaded cantilever — load path and boundary conditions.",
    "l_bracket": "L-bracket — stress concentration and geometric sensitivity.",
    "loaded_hook": "Loaded hook — non-rectangular design domain.",
    "simple_bracket": "2.5D bracket — frozen/void selectors and multiple load cases.",
    "multi_load_cantilever": "Cantilever under multiple load cases (weighted / worst-case).",
    "stress_limited_bracket": "Bracket with a stress constraint (p-norm / KS + adjoint).",
    "stress_multi_load_bracket": "Stress constraint plus multiple load cases.",
    "heat_sink": "2D heat-conduction SIMP (Poisson).",
    "vibrating_beam": "Modal / frequency-response benchmark.",
    "nonlinear_cantilever": "Geometric-nonlinear cantilever (simplified TL).",
    "bimaterial_beam": "Multi-material SIMP beam.",
    "uncertain_load_bracket": "Reliability / Monte-Carlo robust SIMP.",
}


def _label(benchmark_id: str) -> str:
    return benchmark_id.replace("_", " ").title()


def _presets(benchmark_id: str) -> list[str]:
    """Preset names live under the raw JSON's ``presets`` key (popped during
    parse, so not present on ``BenchmarkConfig``). Read them straight from disk.
    """
    import json

    raw = json.loads(config_path(benchmark_id).read_text())
    return sorted(raw.get("presets", {}).keys())


@app.get("/api/benchmarks", response_model=list[BenchmarkSummary])
def list_benchmarks() -> list[BenchmarkSummary]:
    """List built-in benchmarks the workbench can run, recommended first."""
    summaries: list[BenchmarkSummary] = []
    for name in available_benchmarks():
        if name in _EXCLUDED:
            continue
        cfg = load_benchmark(name)
        summaries.append(
            BenchmarkSummary(
                id=name,
                label=_label(name),
                nelx=cfg.mesh.nelx,
                nely=cfg.mesh.nely,
                volume_fraction=cfg.optimization.volume_fraction,
                max_iterations=cfg.optimization.max_iterations,
                presets=_presets(name),
                description=_BLURBS.get(name),
                recommended=name in _RECOMMENDED,
            )
        )
    summaries.sort(key=lambda s: (not s.recommended, s.id))
    return summaries


@app.post("/api/runs", response_model=StartRunResponse)
def start_run(req: StartRunRequest) -> StartRunResponse:
    """Start an optimization run in a worker thread; returns its id immediately."""
    if req.benchmark_id in _EXCLUDED or req.benchmark_id not in available_benchmarks():
        raise HTTPException(status_code=404, detail=f"Unknown benchmark '{req.benchmark_id}'")
    try:
        state = manager.start(req.benchmark_id, req.preset)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StartRunResponse(
        run_id=state.run_id,
        benchmark_id=state.benchmark_id,
        nelx=state.nelx,
        nely=state.nely,
    )


@app.websocket("/api/runs/{run_id}/stream")
async def stream_run(websocket: WebSocket, run_id: str) -> None:
    """Stream iteration frames until a ``done``/``error`` frame, then close."""
    await websocket.accept()
    state = manager.get(run_id)
    if state is None:
        await websocket.send_json({"type": "error", "message": f"Unknown run '{run_id}'"})
        await websocket.close()
        return

    try:
        while True:
            frame = await asyncio.to_thread(state.frames.get)
            if frame is SENTINEL:
                break
            await websocket.send_json(frame)
    except WebSocketDisconnect:
        return
    finally:
        with contextlib.suppress(RuntimeError):
            await websocket.close()


@app.get("/api/runs/{run_id}", response_model=RunResult)
def get_run(run_id: str) -> RunResult:
    """Return the final summary + verification + density for a completed run."""
    state = manager.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Unknown run '{run_id}'")
    if state.status == "running" or state.run_dir is None:
        raise HTTPException(status_code=409, detail="Run not finished")
    if state.status == "error":
        raise HTTPException(status_code=500, detail=state.error or "Run failed")

    summary: dict[str, Any] = read_json(state.run_dir / "summary.json")
    verification = read_json(state.run_dir / "verification.json")
    shape, density_b64 = encode_density(load_density(state.run_dir), state.nelx, state.nely)
    return RunResult(
        run_id=state.run_id,
        benchmark_id=state.benchmark_id,
        status=state.status,
        summary=summary,
        verification=verification,
        shape=shape,
        density_b64=density_b64,
    )


@app.get("/api/runs/{run_id}/export")
def export_run(
    run_id: str,
    fmt: str = Query("svg", alias="format"),
    threshold: float = Query(0.5, ge=0.0, le=1.0),
    extrusion_depth: float = Query(1.0, gt=0.0),
) -> Response:
    """Download the run's optimized geometry as SVG / DXF / STL (attachment)."""
    if fmt not in EXPORT_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unknown format '{fmt}' (choose svg/dxf/stl)")
    state = manager.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Unknown run '{run_id}'")
    if state.status != "done" or state.run_dir is None:
        raise HTTPException(status_code=409, detail="Run not finished")

    try:
        data, filename, mime = export_geometry(state.run_dir, fmt, threshold, extrusion_depth)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return Response(
        content=data,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
