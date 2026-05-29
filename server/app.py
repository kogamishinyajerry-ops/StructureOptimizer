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
from structure_optimizer.core.config import ConfigError
from structure_optimizer.core.run_store import load_density, load_metrics, read_json

from server.export import EXPORT_FORMATS, export_geometry
from server.frames import encode_density
from server.overrides import (
    ELEMENTS_MAX,
    MAX_ITERATIONS_MAX,
    NELX_MAX,
    NELY_MAX,
    VALID_SELECTORS,
)
from server.runner import SENTINEL, RunManager
from server.schemas import (
    BenchmarkConfigEditable,
    BenchmarkSummary,
    EditableLimits,
    EditableLoad,
    MeshOverride,
    MetricPoint,
    OptimizationOverride,
    RunListItem,
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


@app.get("/api/benchmarks/{benchmark_id}/config", response_model=BenchmarkConfigEditable)
def get_benchmark_config(benchmark_id: str) -> BenchmarkConfigEditable:
    """Return the editable problem-definition state for the editor's initial form."""
    if benchmark_id in _EXCLUDED or benchmark_id not in available_benchmarks():
        raise HTTPException(status_code=404, detail=f"Unknown benchmark '{benchmark_id}'")
    cfg = load_benchmark(benchmark_id)
    loads_editable = not cfg.load_cases
    loads = (
        [EditableLoad(selector=ld["selector"], fx=float(ld.get("fx", 0.0)), fy=float(ld.get("fy", 0.0))) for ld in cfg.loads]
        if loads_editable
        else []
    )
    return BenchmarkConfigEditable(
        benchmark_id=benchmark_id,
        optimization=OptimizationOverride(
            volume_fraction=cfg.optimization.volume_fraction,
            penalty=cfg.optimization.penalty,
            filter_radius=cfg.optimization.filter_radius,
            max_iterations=cfg.optimization.max_iterations,
        ),
        mesh=MeshOverride(nelx=cfg.mesh.nelx, nely=cfg.mesh.nely),
        loads=loads,
        loads_editable=loads_editable,
        selectors=list(VALID_SELECTORS),
        limits=EditableLimits(
            nelx_max=NELX_MAX,
            nely_max=NELY_MAX,
            elements_max=ELEMENTS_MAX,
            max_iterations_max=MAX_ITERATIONS_MAX,
        ),
    )


@app.get("/api/runs", response_model=list[RunListItem])
def list_runs() -> list[RunListItem]:
    """List in-memory runs, newest first, for the history panel."""
    items: list[RunListItem] = []
    for state in manager.list():
        compliance: float | None = None
        verified: bool | None = None
        iterations: int | None = None
        if state.status == "done" and state.run_dir is not None:
            # Safe reads: a missing/partial artifact leaves the field None.
            try:
                summary = read_json(state.run_dir / "summary.json")
                compliance = float(summary["optimized"]["compliance"])
                iterations = int(summary.get("iterations", 0))
            except Exception:
                pass
            try:
                verification = read_json(state.run_dir / "verification.json")
                verified = verification.get("status") == "passed"
            except Exception:
                pass
        items.append(
            RunListItem(
                run_id=state.run_id,
                benchmark_id=state.benchmark_id,
                label=_label(state.benchmark_id),
                nelx=state.nelx,
                nely=state.nely,
                status=state.status,
                compliance=compliance,
                verified=verified,
                iterations=iterations,
            )
        )
    return items


@app.post("/api/runs", response_model=StartRunResponse)
def start_run(req: StartRunRequest) -> StartRunResponse:
    """Start an optimization run in a worker thread; returns its id immediately."""
    if req.benchmark_id in _EXCLUDED or req.benchmark_id not in available_benchmarks():
        raise HTTPException(status_code=404, detail=f"Unknown benchmark '{req.benchmark_id}'")
    overrides = req.overrides.model_dump(exclude_none=True) if req.overrides is not None else None
    try:
        state = manager.start(req.benchmark_id, req.preset, overrides)
    except (ValueError, ConfigError) as exc:
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

    # A run's frame queue is a single destructive stream with one SENTINEL, so it
    # supports exactly one consumer. Reject a second concurrent consumer (two tabs,
    # a StrictMode double-mount, a reconnect race) or a late one connecting after
    # the stream finished — either would otherwise steal frames or block forever on
    # the missing SENTINEL, leaking a thread + socket. The check/set pair has no
    # await between it, so it is atomic on the event loop.
    if state.streaming or state.stream_done:
        await websocket.send_json(
            {"type": "error", "message": "Run stream is unavailable; fetch the result via GET /api/runs/{id}"}
        )
        await websocket.close()
        return
    state.streaming = True

    try:
        while True:
            frame = await asyncio.to_thread(state.frames.get)
            if frame is SENTINEL:
                state.stream_done = True
                break
            await websocket.send_json(frame)
    except WebSocketDisconnect:
        return
    finally:
        state.streaming = False
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

    # summary.json + density.npy are the essential artifacts; a partially-written
    # or pruned run dir that lacks them is "incomplete" -> a deliberate 409 rather
    # than an unhandled 500 with a stack trace.
    try:
        summary: dict[str, Any] = read_json(state.run_dir / "summary.json")
        density = load_density(state.run_dir)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="Run artifacts are incomplete") from exc
    shape, density_b64 = encode_density(density, state.nelx, state.nely)
    # verification + metrics are optional: a reopened run with a missing/partial
    # file degrades to {}/[] rather than failing the whole panel.
    try:
        verification = read_json(state.run_dir / "verification.json")
    except (FileNotFoundError, ValueError):
        verification = {}
    try:
        metrics = [MetricPoint(**row) for row in load_metrics(state.run_dir)]
    except (TypeError, ValueError):
        metrics = []
    return RunResult(
        run_id=state.run_id,
        benchmark_id=state.benchmark_id,
        status=state.status,
        summary=summary,
        verification=verification,
        shape=shape,
        density_b64=density_b64,
        metrics=metrics,
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
