"""Deterministic contract-driven pipeline orchestration (the "six artisans").

This module makes the *previously-implicit* ``run_config`` pipeline explicit:
the eleven sequential statements of the old ``workflow.run_config`` become six
named, gate-checkable **deterministic pipeline agents** (+ one internal
persistence step) executed by a plain for-loop orchestrator.

HONESTY — read this before the word "agent" misleads you:

    A ``PipelineAgent`` here is a *pure-Python wrapper around an existing core
    function*. It calls **no language model, makes no network call, draws no
    randomness, and adds zero nondeterminism**. "Agent" denotes a
    contract-bearing pipeline stage (precondition / run / postcondition /
    declared_tools), **not** an autonomous or LLM-backed agent.

Why this exists (and is load-bearing, not ceremony):

  * ``run_config`` now has exactly ONE code path — it *delegates* to
    ``PipelineOrchestrator`` (the orchestrator IS the implementation; there is
    no parallel "real" pipeline). Removing this layer removes the only path
    that produces a run directory.
  * Each stage carries an explicit, testable **gate** (config fingerprint,
    OptimizationResult shape, convergence ``stop_reason``, ``summary.json``
    schema, verification status) so invariants that used to be buried in a
    function body are now first-class and individually assertable.
  * The orchestrator writes ``agents_trace.json`` on every run. It records, per
    stage, the real wrapped function, the gate verdict, and the
    *orchestrator-measured* set of files the stage wrote (a stage cannot lie
    about what it produced). The guided web walkthrough reads this trace, so its
    "六小匠" depiction is generated FROM the real run instead of being scripted.

REPRODUCIBILITY: every agent calls the identical seam function with identical
arguments in the identical order as the old ``run_config`` body, so every
artifact is byte-identical by construction. ``agents_trace.json`` is the only
new file; its sole non-deterministic field is ``wall_ms`` (a perf_counter
measurement), which never enters ``summary.json`` / ``density.npy`` /
``metrics.csv`` / ``verification.json``. Set ``SO_TRACE_DETERMINISTIC=1`` to
zero all ``wall_ms`` for whole-directory-hash stability.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any

from structure_optimizer.core.config import effective_load_cases
from structure_optimizer.core.lineage import LineageRecord, write_lineage
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.reporting import generate_report
from structure_optimizer.core.run_store import (
    create_run_dir,
    input_hash,
    read_json,
    save_density,
    save_input,
    save_metrics,
    write_json,
)
from structure_optimizer.core.verification import verify_run
from structure_optimizer.visualization import (
    write_baseline_png,
    write_convergence_png,
    write_density_gif,
    write_density_png,
    write_loadcase_png,
)

TRACE_FILENAME = "agents_trace.json"
TRACE_SCHEMA_VERSION = 1
PIPELINE_LABEL = "deterministic-six-agent"
"""Honest, machine-readable label: the UI asserts non-LLM determinism on this."""

# stop reasons that are a legitimate convergence outcome (a PASS at the gate).
_CONVERGED_STOP_REASONS = frozenset({"change_tolerance", "max_iterations"})


class PipelineGateError(RuntimeError):
    """Raised when a structural gate fails (corruption / contract regression).

    A gate raising aborts the run and re-propagates unchanged, preserving the
    old ``run_config`` all-or-nothing behaviour. An *engineering* negative
    (e.g. ``verification.json`` status ``connectivity_failed``) is NOT a gate
    error — it is a legitimate terminal state recorded into the trace.
    """


@dataclass(frozen=True)
class GateVerdict:
    """A stage's explicit gate outcome.

    ``ok`` is the structural pass/fail. ``status`` carries the domain verdict
    string (``"ok"`` for most stages, the ``stop_reason`` for convergence, the
    ``verification.json`` status for verification) so the trace surfaces it.
    """

    ok: bool
    status: str = "ok"
    detail: str = ""


@dataclass
class PipelineContext:
    """Mutable carrier threaded between stages — the in-flight pipeline state.

    Holds the six ``run_config`` parameters plus progressively-filled products
    (``mesh`` -> ``result`` -> ``run_dir`` -> ``input_hash`` -> verification
    status) and the accumulating ``trace``. It is intentionally mutable (it must
    thread the in-flight mesh/result/run_dir exactly like the old local
    variables) and single-threaded; it holds no lambdas / thread-local / open
    handles, so a ``study`` worker stays picklable across ``ProcessPoolExecutor``
    (the orchestrator is built inside ``run_config`` in the child, never pickled).
    """

    config: Any
    run_dir: Path | None = None
    parent_id: str | None = None
    study_id: str | None = None
    generation: int = 0
    on_iteration: Any = None
    on_stage: Any = None  # optional observational sink (server agent-rail); None = silent
    # progressively filled:
    mesh: Any = None
    result: Any = None
    input_hash: str | None = None
    verification_status: str | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)


class PipelineAgent(ABC):
    """A deterministic, non-LLM pipeline stage wrapping one existing core function.

    Subclasses set the class attributes and implement ``run``. ``precondition``
    fails-closed on a missing upstream product BEFORE any side effect;
    ``postcondition`` returns the explicit :class:`GateVerdict`.
    """

    name: str = "abstract"
    role: str = ""
    tool: str = ""
    gate_name: str = ""
    declared_tools: tuple[str, ...] = ()
    domain_agent: bool = True  # one of the six; False for the persistence step

    def precondition(self, ctx: PipelineContext) -> None:  # noqa: B027 - optional hook
        """Raise :class:`PipelineGateError` if an upstream product is missing."""

    @abstractmethod
    def run(self, ctx: PipelineContext) -> None:
        """Do the wrapped deterministic work, mutating ``ctx`` in place."""

    def postcondition(self, ctx: PipelineContext) -> GateVerdict:
        """Return this stage's gate verdict (default: structural OK)."""
        return GateVerdict(ok=True)

    def trace_detail(self, ctx: PipelineContext) -> dict[str, Any]:
        """Stage-specific structured detail for the trace (default: none)."""
        return {}


# --------------------------------------------------------------------------- #
# The six deterministic agents + one internal persistence step                #
# Each ``run`` mirrors the corresponding statement(s) of the old run_config.   #
# --------------------------------------------------------------------------- #


class ProblemDefinitionAgent(PipelineAgent):
    name = "problem_definition"
    role = "Fingerprint the validated config into a provenance input_hash"
    tool = "core.run_store.input_hash"
    gate_name = "GATE-CONFIG"
    declared_tools = ("core.run_store.input_hash",)

    def run(self, ctx: PipelineContext) -> None:
        # input_hash is computed once here and carried in ctx; summary.json uses
        # the same value, so its bytes are identical to the old inline call.
        ctx.input_hash = input_hash(ctx.config)

    def postcondition(self, ctx: PipelineContext) -> GateVerdict:
        if not (ctx.input_hash and ctx.input_hash.startswith("sha256:")):
            raise PipelineGateError("input_hash was not computed as a sha256 digest")
        if not getattr(ctx.config, "name", ""):
            raise PipelineGateError("config.name is empty")
        return GateVerdict(ok=True)

    def trace_detail(self, ctx: PipelineContext) -> dict[str, Any]:
        return {"input_hash": ctx.input_hash}


class MeshAgent(PipelineAgent):
    name = "mesh"
    role = "Discretise the design domain into a structured quad mesh + masks"
    tool = "core.mesh.create_structured_mesh"
    gate_name = "GATE-MESH"
    declared_tools = ("core.mesh.create_structured_mesh",)

    def run(self, ctx: PipelineContext) -> None:
        ctx.mesh = create_structured_mesh(ctx.config)

    def postcondition(self, ctx: PipelineContext) -> GateVerdict:
        if ctx.mesh is None or not hasattr(ctx.mesh, "elements"):
            raise PipelineGateError("mesh was not constructed")
        return GateVerdict(ok=True)

    def trace_detail(self, ctx: PipelineContext) -> dict[str, Any]:
        mesh = ctx.mesh
        return {
            "nelx": getattr(mesh, "nelx", None),
            "nely": getattr(mesh, "nely", None),
            "element_count": len(mesh.elements) if getattr(mesh, "elements", None) is not None else None,
        }


class OptimizerAgent(PipelineAgent):
    name = "optimizer"
    role = "Dispatch to SIMP/BESO and run the iterative optimization"
    tool = "adapters.algorithm_base.get_algorithm + TopologyAlgorithm.run"
    gate_name = "GATE-RESULT-SHAPE"
    declared_tools = ("adapters.algorithm_base.get_algorithm",)

    def precondition(self, ctx: PipelineContext) -> None:
        if ctx.mesh is None:
            raise PipelineGateError("optimizer requires a mesh from the upstream stage")

    def run(self, ctx: PipelineContext) -> None:
        # Lazy import keeps pipeline import light + avoids any import cycle.
        from structure_optimizer.adapters.algorithm_base import get_algorithm

        algorithm = get_algorithm(ctx.config.optimization.algorithm)
        ctx.result = algorithm.run(ctx.config, ctx.mesh, on_iteration=ctx.on_iteration)

    def postcondition(self, ctx: PipelineContext) -> GateVerdict:
        result = ctx.result
        required = ("densities", "metrics", "baseline", "final_analysis", "stop_reason", "density_history")
        missing = [f for f in required if not hasattr(result, f)]
        if missing:
            raise PipelineGateError(f"OptimizationResult missing fields: {missing}")
        return GateVerdict(ok=True)

    def trace_detail(self, ctx: PipelineContext) -> dict[str, Any]:
        return {
            "algorithm": (ctx.config.optimization.algorithm or "simp"),
            "iterations": len(ctx.result.metrics),
            "stop_reason": ctx.result.stop_reason,
        }


class ConvergenceGateAgent(PipelineAgent):
    name = "convergence_gate"
    role = "Surface the algorithm's implicit stop_reason as an explicit gate"
    tool = "(pure gate over OptimizationResult.stop_reason)"
    gate_name = "GATE-CONVERGENCE"
    declared_tools = ()

    def precondition(self, ctx: PipelineContext) -> None:
        if ctx.result is None:
            raise PipelineGateError("convergence gate requires an optimization result")

    def run(self, ctx: PipelineContext) -> None:
        # Pure gate: no recompute, no mutation, no side effect — byte outputs
        # are unchanged and summary.status stays 'completed' regardless.
        return

    def postcondition(self, ctx: PipelineContext) -> GateVerdict:
        stop_reason = ctx.result.stop_reason
        if stop_reason not in _CONVERGED_STOP_REASONS:
            raise PipelineGateError(f"unexpected stop_reason {stop_reason!r}; algorithm contract drift")
        if len(ctx.result.metrics) < 1:
            raise PipelineGateError("optimization produced zero iteration metrics")
        # 'max_iterations' is a legal pass (converged-by-budget).
        return GateVerdict(ok=True, status=stop_reason)

    def trace_detail(self, ctx: PipelineContext) -> dict[str, Any]:
        return {
            "stop_reason": ctx.result.stop_reason,
            "converged": ctx.result.stop_reason == "change_tolerance",
            "iterations": len(ctx.result.metrics),
        }


class _RunStorePersistenceStep(PipelineAgent):
    """Internal persistence step (NOT one of the six domain agents).

    Groups the five ``run_store`` writes + ``summary.json`` at the exact point
    they occur today: AFTER mesh + optimize (so a pre-persistence crash leaves
    NO orphan run directory, identical to the old behaviour), BEFORE export.
    """

    name = "persistence"
    role = "Create the run directory and persist input / metrics / density / lineage / summary"
    tool = "core.run_store.{create_run_dir,save_input,save_metrics,save_density,write_json} + lineage.write_lineage"
    gate_name = "GATE-RUNDIR"
    declared_tools = (
        "core.run_store.create_run_dir",
        "core.run_store.save_input",
        "core.run_store.save_metrics",
        "core.run_store.save_density",
        "core.run_store.write_json",
        "core.lineage.write_lineage",
    )
    domain_agent = False

    def run(self, ctx: PipelineContext) -> None:
        config, result = ctx.config, ctx.result
        # PRESERVES real order: dir created AFTER mesh+optimize (workflow.py:71-75).
        if ctx.run_dir is None:
            ctx.run_dir = create_run_dir(config)
        else:
            ctx.run_dir = Path(ctx.run_dir)
            ctx.run_dir.mkdir(parents=True, exist_ok=False)  # exist_ok=False is immutable

        save_input(ctx.run_dir, config)
        save_metrics(ctx.run_dir, result.metrics)
        save_density(ctx.run_dir, result.densities)
        write_lineage(
            ctx.run_dir,
            LineageRecord(
                run_id=ctx.run_dir.name,
                parent_id=ctx.parent_id,
                study_id=ctx.study_id,
                generation=ctx.generation,
            ),
        )
        write_json(
            ctx.run_dir / "summary.json",
            {
                "benchmark": config.name,
                "input_hash": ctx.input_hash,
                "status": "completed",
                "stop_reason": result.stop_reason,
                "iterations": len(result.metrics),
                "baseline": {
                    "mass": result.baseline.mass,
                    "compliance": result.baseline.compliance,
                    "max_displacement": result.baseline.max_displacement,
                    "max_stress": result.baseline.max_stress,
                },
                "optimized": {
                    "mass": result.final_analysis.mass,
                    "compliance": result.final_analysis.compliance,
                    "max_displacement": result.final_analysis.max_displacement,
                    "max_stress": result.final_analysis.max_stress,
                },
            },
        )

    def postcondition(self, ctx: PipelineContext) -> GateVerdict:
        if ctx.run_dir is None or not (ctx.run_dir / "summary.json").exists():
            raise PipelineGateError("persistence did not produce summary.json")
        return GateVerdict(ok=True)


class VerificationAgent(PipelineAgent):
    name = "verification"
    role = "Independently re-solve and verify every constraint (fail-soft verdict)"
    tool = "core.verification.verify_run"
    gate_name = "GATE-VERIFICATION"
    declared_tools = ("core.verification.verify_run",)

    def precondition(self, ctx: PipelineContext) -> None:
        if ctx.run_dir is None or not (ctx.run_dir / "input.json").exists():
            raise PipelineGateError("verification requires persisted input.json + density.npy")

    def run(self, ctx: PipelineContext) -> None:
        assert ctx.run_dir is not None  # precondition() raises if run_dir is None
        verify_run(ctx.run_dir)
        verification = read_json(ctx.run_dir / "verification.json")
        ctx.verification_status = verification.get("status")

    def postcondition(self, ctx: PipelineContext) -> GateVerdict:
        # FAIL-CLOSED on file+schema, NOT on engineering status: verify_run is
        # contractually no-raise; an engineering FAILURE_STATUS (e.g.
        # connectivity_failed) is a legitimate terminal state, surfaced (ok=False)
        # but NOT aborting the run (summary.status stays 'completed', CLI exits 0).
        from structure_optimizer.core.verification import FAILURE_STATUSES, PASS_STATUS

        status = ctx.verification_status
        known = {PASS_STATUS, *FAILURE_STATUSES}
        if status is None or status not in known:
            raise PipelineGateError(f"verification produced an unknown status: {status!r}")
        return GateVerdict(ok=(status == PASS_STATUS), status=status)

    def trace_detail(self, ctx: PipelineContext) -> dict[str, Any]:
        return {"verification_status": ctx.verification_status}


class ExportReportAgent(PipelineAgent):
    name = "export_report"
    role = "Render all visual artifacts (PNGs / frames / GIF) and the markdown report"
    tool = "structure_optimizer.visualization.* + core.reporting.generate_report"
    gate_name = "GATE-EXPORT"
    declared_tools = (
        "visualization.write_baseline_png",
        "visualization.write_loadcase_png",
        "visualization.write_density_png",
        "visualization.write_convergence_png",
        "visualization.write_density_gif",
        "core.reporting.generate_report",
    )

    _EXPECTED = (
        "baseline.png",
        "loadcase.png",
        "density.png",
        "convergence.png",
        "optimization.gif",
        "report.md",
    )

    def precondition(self, ctx: PipelineContext) -> None:
        if ctx.run_dir is None or ctx.mesh is None or ctx.result is None:
            raise PipelineGateError("export requires run_dir + mesh + result")

    def run(self, ctx: PipelineContext) -> None:
        # Helpers stay in workflow.py (zero external importers); lazy import
        # avoids a circular dependency (workflow -> pipeline at call time).
        from structure_optimizer.core.workflow import (
            _select_animation_frames,
            _write_optimization_frames,
        )

        run_dir, mesh, result, config = ctx.run_dir, ctx.mesh, ctx.result, ctx.config
        # precondition() raises unless run_dir + mesh + result are all set
        assert run_dir is not None and mesh is not None and result is not None
        write_baseline_png(run_dir / "baseline.png", mesh)
        display_loads = [load for load_case in effective_load_cases(config) for load in load_case.loads]
        write_loadcase_png(run_dir / "loadcase.png", mesh, config.boundary_conditions, display_loads)
        write_density_png(run_dir / "density.png", mesh, result.densities)
        write_convergence_png(run_dir / "convergence.png", result.metrics)
        _write_optimization_frames(run_dir, mesh, result.density_history)
        write_density_gif(run_dir / "optimization.gif", mesh, _select_animation_frames(result.density_history))
        generate_report(run_dir)

    def postcondition(self, ctx: PipelineContext) -> GateVerdict:
        assert ctx.run_dir is not None  # run()/precondition() guarantee this
        missing = [f for f in self._EXPECTED if not (ctx.run_dir / f).exists()]
        if missing:
            raise PipelineGateError(f"export did not produce expected artifacts: {missing}")
        return GateVerdict(ok=True)


# --------------------------------------------------------------------------- #
# Orchestrator                                                                 #
# --------------------------------------------------------------------------- #


def _snapshot(run_dir: Path | str | None) -> set[str]:
    """The set of file names currently in ``run_dir`` (recursive), or empty.

    Accepts ``str`` too: callers may pass ``run_dir`` as a string and the
    persistence step only normalises it to ``Path`` mid-pipeline, so this
    helper coerces defensively (matching the old ``run_config`` which did
    ``Path(run_dir)`` immediately).
    """
    if run_dir is None:
        return set()
    run_dir = Path(run_dir)
    if not run_dir.exists():
        return set()
    return {str(p.relative_to(run_dir)) for p in run_dir.rglob("*") if p.is_file()}


class PipelineOrchestrator:
    """Run the ordered deterministic stages, enforce gates, write the trace.

    The "DAG" is strictly linear (each stage depends on the prior), so it is a
    plain ordered list executed by a for-loop — no graph engine, no scheduler,
    no parallelism (parallelism would reorder floating-point work and break
    byte-reproducibility).
    """

    def __init__(self) -> None:
        self._stages: list[PipelineAgent] = [
            ProblemDefinitionAgent(),
            MeshAgent(),
            OptimizerAgent(),
            ConvergenceGateAgent(),
            _RunStorePersistenceStep(),
            VerificationAgent(),
            ExportReportAgent(),
        ]

    def run(self, ctx: PipelineContext) -> Path:
        for stage in self._stages:
            before = _snapshot(ctx.run_dir)
            t0 = perf_counter()
            _emit_stage(ctx, {"phase": "start", "agent": stage.name, "record": None})
            try:
                stage.precondition(ctx)
                stage.run(ctx)
                verdict = stage.postcondition(ctx)
                status = "ok" if verdict.ok else "gate_failed"
                detail = stage.trace_detail(ctx)
            except PipelineGateError as exc:
                # Structural gate failure / contract regression. Record the failing
                # stage, emit a ``stage_error`` event, persist a partial trace, then
                # re-raise the ORIGINAL exception unchanged (all-or-nothing). The
                # bare ``raise`` MUST live inside this ``except`` block: a bare raise
                # AFTER the except clause re-raises "No active exception" instead of
                # the gate error (the prior bug; precondition was also outside the
                # try, so a precondition failure recorded nothing).
                wall_ms = (perf_counter() - t0) * 1000.0
                new_files = sorted(_snapshot(ctx.run_dir) - before)
                record = _record(
                    stage, GateVerdict(ok=False, status="error", detail=str(exc)), "error", wall_ms, new_files, {}
                )
                ctx.trace.append(record)
                _emit_stage(ctx, {"phase": "error", "agent": stage.name, "record": record})
                # Persist a partial trace only if the run dir already exists. A
                # caller-provided run_dir (study path) is set on ctx from the
                # start, but the directory is not created until the persistence
                # stage — so an early-stage failure must not write into a
                # nonexistent dir.
                if ctx.run_dir is not None and ctx.run_dir.exists():
                    self._write_trace(ctx.run_dir, ctx.trace)  # partial trace for inspectability
                raise

            wall_ms = (perf_counter() - t0) * 1000.0
            new_files = sorted(_snapshot(ctx.run_dir) - before)
            record = _record(stage, verdict, status, wall_ms, new_files, detail)
            ctx.trace.append(record)
            _emit_stage(ctx, {"phase": "end", "agent": stage.name, "record": record})

        assert ctx.run_dir is not None  # persistence step guarantees this
        self._write_trace(ctx.run_dir, ctx.trace)
        return ctx.run_dir

    @staticmethod
    def _write_trace(run_dir: Path, trace: list[dict[str, Any]]) -> None:
        records = trace
        if os.getenv("SO_TRACE_DETERMINISTIC") == "1":
            records = [{**r, "wall_ms": 0.0} for r in trace]
        write_json(
            run_dir / TRACE_FILENAME,
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "pipeline": PIPELINE_LABEL,
                "run_id": run_dir.name,
                "agents": records,
                "terminal_status": "completed" if all(r["status"] != "error" for r in records) else "error",
            },
        )


def _emit_stage(ctx: PipelineContext, event: dict[str, Any]) -> None:
    """Forward a stage-lifecycle event to ``ctx.on_stage`` if a sink is attached.

    Purely observational and None-guarded exactly like ``on_iteration``
    (``simp.py``): the default CLI/study path (``on_stage is None``) emits
    nothing and is byte-identical. The ``"end"``/``"error"`` event's ``record``
    IS the exact dict appended to ``agents_trace.json`` (one source of truth), so
    the live stream and the on-disk trace are equal once the nondeterministic
    ``wall_ms`` is dropped. ``"start"`` carries ``record=None`` (active marker
    only). The event payload is metadata only — it never carries the density
    array (live density flows exclusively through ``on_iteration``).
    """
    cb = ctx.on_stage
    if cb is not None:
        cb(event)


def _record(
    stage: PipelineAgent,
    verdict: GateVerdict,
    status: str,
    wall_ms: float,
    new_files: list[str],
    detail: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": stage.name,
        "role": stage.role,
        "tool": stage.tool,
        "declared_tools": list(stage.declared_tools),
        "domain_agent": stage.domain_agent,
        "status": status,
        "gate": {
            "name": stage.gate_name,
            "ok": verdict.ok,
            "verdict_status": verdict.status,
            "detail": verdict.detail,
        },
        "artifacts": new_files,  # measured by the orchestrator, not self-reported
        "detail": detail,
        "wall_ms": wall_ms,
    }
