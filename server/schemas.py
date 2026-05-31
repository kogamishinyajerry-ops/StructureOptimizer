"""Pydantic models = the JSON/WS contract between FastAPI and the React client.

Single source of truth for the wire format; the frontend's TypeScript types
mirror these one-to-one.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class BenchmarkSummary(BaseModel):
    """One entry in ``GET /api/benchmarks`` — enough for the picker UI."""

    id: str
    label: str
    nelx: int
    nely: int
    volume_fraction: float
    max_iterations: int
    presets: list[str] = Field(default_factory=list)
    description: str | None = None
    recommended: bool = False


class EditableLoad(BaseModel):
    """One point load the editor can tweak (selector + 2D force components)."""

    selector: str
    fx: float
    fy: float


class OptimizationOverride(BaseModel):
    volume_fraction: float
    penalty: float
    filter_radius: float
    max_iterations: int
    # M7 algorithm selector (SIMP ↔ BESO). Optional + ``None`` is dropped on the
    # wire (``model_dump(exclude_none=True)``), so existing 4-field payloads are
    # unchanged. A plain ``str`` (not a ``Literal``) keeps the engine registry's
    # ``available_algorithms()`` the single source of truth: an unknown value is
    # rejected at the override layer (HTTP 400), not at parse time (422).
    algorithm: str | None = None


class MeshOverride(BaseModel):
    nelx: int
    nely: int


class RunOverrides(BaseModel):
    """Optional edits applied on top of a benchmark before a run (M3)."""

    optimization: OptimizationOverride | None = None
    mesh: MeshOverride | None = None
    loads: list[EditableLoad] | None = None


class StartRunRequest(BaseModel):
    benchmark_id: str
    preset: str | None = None
    overrides: RunOverrides | None = None


class StartRunResponse(BaseModel):
    run_id: str
    benchmark_id: str
    nelx: int
    nely: int


class EditableLimits(BaseModel):
    nelx_max: int
    nely_max: int
    elements_max: int
    max_iterations_max: int


class BenchmarkConfigEditable(BaseModel):
    """``GET /api/benchmarks/{id}/config`` — the editor's initial form state."""

    benchmark_id: str
    optimization: OptimizationOverride
    mesh: MeshOverride
    loads: list[EditableLoad] = Field(default_factory=list)
    loads_editable: bool
    selectors: list[str]
    limits: EditableLimits


# ---- WebSocket frame envelopes (discriminated on ``type``) -------------------


class IterationFrame(BaseModel):
    type: Literal["iteration"] = "iteration"
    iteration: int
    compliance: float
    volume_fraction: float
    change: float
    max_displacement: float
    mass: float
    shape: list[int]  # [nely, nelx]
    density_b64: str  # row-major uint8, base64


class DoneFrame(BaseModel):
    type: Literal["done"] = "done"
    run_id: str
    iterations: int
    stop_reason: str
    summary: dict[str, Any]
    verification: dict[str, Any]
    shape: list[int]
    density_b64: str


class ErrorFrame(BaseModel):
    type: Literal["error"] = "error"
    message: str


class MetricPoint(BaseModel):
    """One ``metrics.csv`` row — the convergence series for a finished run."""

    iteration: int
    compliance: float
    volume_fraction: float
    change: float
    max_displacement: float
    mass: float


class RunListItem(BaseModel):
    """One entry in ``GET /api/runs`` — enough for the history panel."""

    run_id: str
    benchmark_id: str
    label: str
    nelx: int
    nely: int
    status: str
    compliance: float | None = None
    verified: bool | None = None
    iterations: int | None = None


class RunResult(BaseModel):
    run_id: str
    benchmark_id: str
    status: str
    summary: dict[str, Any]
    verification: dict[str, Any]
    shape: list[int]
    density_b64: str
    metrics: list[MetricPoint] = Field(default_factory=list)
