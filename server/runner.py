"""Run lifecycle: drive the synchronous numpy engine in a worker thread and
stream per-iteration frames to consumers via a thread-safe queue.

Design (deliberately minimal for Milestone 1 — "good enough" reliability):
- One ``RunManager`` keeps the last ``max_runs`` runs in memory.
- Each run executes ``workflow.run_config`` in a daemon thread. The engine's
  ``on_iteration`` callback pushes an iteration frame onto the run's queue. When
  the engine returns, the thread reads the persisted artifacts (summary.json,
  verification.json, density.npy) and pushes a ``done`` frame; on exception it
  pushes an ``error`` frame.
- The WebSocket handler drains the queue. ``SENTINEL`` marks end-of-stream.

No Redis/Celery/asyncio-in-engine: the loop is CPU-bound numpy, so a thread +
queue is the simplest thing that keeps the event loop responsive.
"""

from __future__ import annotations

import queue
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.run_store import load_density, read_json
from structure_optimizer.core.workflow import run_config

from server.frames import encode_density
from server.overrides import apply_overrides

SENTINEL = object()
"""Pushed onto a run's queue to signal the stream is closed."""


@dataclass
class RunState:
    run_id: str
    benchmark_id: str
    nelx: int
    nely: int
    frames: queue.Queue = field(default_factory=queue.Queue)
    status: str = "running"  # running | done | error
    run_dir: Path | None = None
    error: str | None = None
    thread: threading.Thread | None = None


class RunManager:
    """In-memory registry of runs. Keeps the last ``max_runs`` for lookup."""

    def __init__(self, max_runs: int = 16) -> None:
        self._runs: dict[str, RunState] = {}
        self._order: list[str] = []
        self._max_runs = max_runs
        self._lock = threading.Lock()

    def get(self, run_id: str) -> RunState | None:
        with self._lock:
            return self._runs.get(run_id)

    def start(
        self,
        benchmark_id: str,
        preset: str | None,
        overrides: dict[str, Any] | None = None,
    ) -> RunState:
        # Apply overrides synchronously so ConfigError/ValueError propagate to
        # the caller (HTTP 400) instead of surfacing late as a run error frame.
        config = apply_overrides(load_benchmark(benchmark_id, preset=preset), overrides)
        run_id = uuid.uuid4().hex[:12]
        state = RunState(
            run_id=run_id,
            benchmark_id=benchmark_id,
            nelx=config.mesh.nelx,
            nely=config.mesh.nely,
        )
        with self._lock:
            self._runs[run_id] = state
            self._order.append(run_id)
            self._evict_locked()

        thread = threading.Thread(
            target=self._execute,
            args=(state, config),
            name=f"run-{run_id}",
            daemon=True,
        )
        state.thread = thread
        thread.start()
        return state

    def _evict_locked(self) -> None:
        while len(self._order) > self._max_runs:
            oldest = self._order.pop(0)
            self._runs.pop(oldest, None)

    def _execute(self, state: RunState, config: Any) -> None:
        nelx, nely = state.nelx, state.nely

        def on_iteration(iteration: int, metric: Any, densities: Any) -> None:
            shape, density_b64 = encode_density(densities, nelx, nely)
            state.frames.put(
                {
                    "type": "iteration",
                    "iteration": iteration,
                    "compliance": float(metric.compliance),
                    "volume_fraction": float(metric.volume_fraction),
                    "change": float(metric.change),
                    "max_displacement": float(metric.max_displacement),
                    "mass": float(metric.mass),
                    "shape": shape,
                    "density_b64": density_b64,
                }
            )

        try:
            run_dir = run_config(config, on_iteration=on_iteration)
            state.run_dir = run_dir
            summary = read_json(run_dir / "summary.json")
            verification = _safe_read_json(run_dir / "verification.json")
            shape, density_b64 = encode_density(load_density(run_dir), nelx, nely)
            state.status = "done"
            state.frames.put(
                {
                    "type": "done",
                    "run_id": state.run_id,
                    "iterations": int(summary.get("iterations", 0)),
                    "stop_reason": summary.get("stop_reason", ""),
                    "summary": summary,
                    "verification": verification,
                    "shape": shape,
                    "density_b64": density_b64,
                }
            )
        except Exception as exc:  # surface any engine failure to the client as an error frame
            state.status = "error"
            state.error = str(exc)
            state.frames.put({"type": "error", "message": str(exc)})
        finally:
            state.frames.put(SENTINEL)


def _safe_read_json(path: Path) -> dict[str, Any]:
    try:
        return read_json(path)
    except Exception:
        return {}
