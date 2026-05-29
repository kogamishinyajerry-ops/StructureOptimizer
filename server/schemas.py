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


class StartRunRequest(BaseModel):
    benchmark_id: str
    preset: str | None = None


class StartRunResponse(BaseModel):
    run_id: str
    benchmark_id: str
    nelx: int
    nely: int


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


class RunResult(BaseModel):
    run_id: str
    benchmark_id: str
    status: str
    summary: dict[str, Any]
    verification: dict[str, Any]
    shape: list[int]
    density_b64: str
