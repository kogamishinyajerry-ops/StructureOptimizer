"""Tests for the deterministic contract-driven pipeline orchestration.

Net-additive: exercises the explicit agents/gates/trace introduced in
``structure_optimizer/core/pipeline.py`` without touching the existing suite.
The byte-identity of every legacy artifact is covered by the existing
reproducibility tests; here we cover the NEW observable surface (gates + trace)
and the fail-closed semantics.
"""

from __future__ import annotations

import json

import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.pipeline import (
    GateVerdict,
    PipelineContext,
    PipelineGateError,
    PipelineOrchestrator,
    VerificationAgent,
)
from structure_optimizer.core.verification import FAILURE_STATUSES, PASS_STATUS
from structure_optimizer.core.workflow import run_benchmark

LEGACY_ARTIFACTS = [
    "input.json",
    "metrics.csv",
    "density.npy",
    "lineage.json",
    "baseline.png",
    "loadcase.png",
    "density.png",
    "convergence.png",
    "optimization.gif",
    "summary.json",
    "verification.json",
    "manufacturability.json",
    "report.md",
]

EXPECTED_STAGE_ORDER = [
    "problem_definition",
    "mesh",
    "optimizer",
    "convergence_gate",
    "persistence",
    "verification",
    "export_report",
]


@pytest.fixture(scope="module")
def smoke_run_dir():
    """One real smoke run, reused across assertions to keep the suite fast."""
    return run_benchmark("mbb_beam", preset="smoke")


@pytest.fixture(scope="module")
def trace(smoke_run_dir):
    return json.loads((smoke_run_dir / "agents_trace.json").read_text())


# --------------------------------------------------------------------------- #
# e2e: orchestrator is load-bearing — produces every legacy artifact + trace   #
# --------------------------------------------------------------------------- #


def test_run_produces_all_legacy_artifacts_plus_trace(smoke_run_dir):
    for name in LEGACY_ARTIFACTS:
        path = smoke_run_dir / name
        assert path.exists() and path.stat().st_size > 0, name
    trace_path = smoke_run_dir / "agents_trace.json"
    assert trace_path.exists() and trace_path.stat().st_size > 0


def test_summary_status_completed_regardless_of_verification(smoke_run_dir):
    summary = json.loads((smoke_run_dir / "summary.json").read_text())
    assert summary["status"] == "completed"
    assert summary["input_hash"].startswith("sha256:")


# --------------------------------------------------------------------------- #
# trace schema                                                                 #
# --------------------------------------------------------------------------- #


def test_trace_top_level_schema(trace):
    assert trace["schema_version"] == 1
    assert trace["pipeline"] == "deterministic-six-agent"
    assert trace["terminal_status"] == "completed"
    assert "run_id" in trace


def test_trace_stage_order_and_record_shape(trace):
    names = [a["name"] for a in trace["agents"]]
    assert names == EXPECTED_STAGE_ORDER
    for record in trace["agents"]:
        assert {
            "name",
            "role",
            "tool",
            "declared_tools",
            "domain_agent",
            "status",
            "gate",
            "artifacts",
            "detail",
            "wall_ms",
        } <= set(record)
        assert {"name", "ok", "verdict_status", "detail"} <= set(record["gate"])


def test_exactly_six_domain_agents(trace):
    domain = [a["name"] for a in trace["agents"] if a["domain_agent"]]
    assert len(domain) == 6
    assert "persistence" not in domain


def test_all_gates_ok_on_passing_run(trace):
    assert all(a["status"] == "ok" for a in trace["agents"])


def test_artifacts_are_measured_not_self_reported(trace):
    by_name = {a["name"]: a for a in trace["agents"]}
    # the orchestrator measures the filesystem diff; pre-persistence stages
    # wrote nothing, persistence wrote the data files, verification the json.
    assert by_name["problem_definition"]["artifacts"] == []
    assert by_name["mesh"]["artifacts"] == []
    assert "summary.json" in by_name["persistence"]["artifacts"]
    assert "verification.json" in by_name["verification"]["artifacts"]
    assert "report.md" in by_name["export_report"]["artifacts"]


def test_convergence_gate_records_stop_reason(trace):
    conv = next(a for a in trace["agents"] if a["name"] == "convergence_gate")
    assert conv["detail"]["stop_reason"] in {"change_tolerance", "max_iterations"}
    assert isinstance(conv["detail"]["converged"], bool)
    assert conv["gate"]["verdict_status"] == conv["detail"]["stop_reason"]


def test_verification_status_surfaced_in_trace(trace):
    ver = next(a for a in trace["agents"] if a["name"] == "verification")
    assert ver["detail"]["verification_status"] in {PASS_STATUS, *FAILURE_STATUSES}
    assert ver["gate"]["verdict_status"] == ver["detail"]["verification_status"]


# --------------------------------------------------------------------------- #
# gate semantics (unit — fast, no e2e run)                                      #
# --------------------------------------------------------------------------- #


def _ctx_with_status(status):
    ctx = PipelineContext(config=None)
    ctx.verification_status = status
    return ctx


def test_verification_gate_records_failure_without_raising():
    """A real engineering FAILURE_STATUS is a legitimate terminal state."""
    failure = next(iter(FAILURE_STATUSES))
    verdict = VerificationAgent().postcondition(_ctx_with_status(failure))
    assert isinstance(verdict, GateVerdict)
    assert verdict.ok is False
    assert verdict.status == failure


def test_verification_gate_passes_on_passed_status():
    verdict = VerificationAgent().postcondition(_ctx_with_status(PASS_STATUS))
    assert verdict.ok is True
    assert verdict.status == PASS_STATUS


def test_verification_gate_raises_on_unknown_status():
    with pytest.raises(PipelineGateError):
        VerificationAgent().postcondition(_ctx_with_status("not_a_real_status"))


# --------------------------------------------------------------------------- #
# fail-closed: run_dir + no-orphan-on-crash                                      #
# --------------------------------------------------------------------------- #


def test_existing_run_dir_raises_file_exists(tmp_path):
    target = tmp_path / "already_here"
    target.mkdir()
    config = load_benchmark("mbb_beam", preset="smoke")
    from structure_optimizer.core.workflow import run_config

    with pytest.raises(FileExistsError):
        run_config(config, run_dir=target)


def test_pre_persistence_failure_leaves_no_run_dir(tmp_path, monkeypatch):
    """A crash before the persistence stage must leave NO run directory."""
    import structure_optimizer.core.pipeline as pipeline

    def boom(_config):
        raise RuntimeError("mesh exploded")

    monkeypatch.setattr(pipeline, "create_structured_mesh", boom)
    target = tmp_path / "should_not_exist"
    config = load_benchmark("mbb_beam", preset="smoke")

    with pytest.raises(RuntimeError, match="mesh exploded"):
        pipeline.PipelineOrchestrator().run(PipelineContext(config=config, run_dir=target))
    assert not target.exists()


def test_post_persistence_gate_failure_writes_partial_error_trace(tmp_path, monkeypatch):
    """A gate failure AFTER the persistence stage (run_dir already on disk) must
    still leave an inspectable agents_trace.json with terminal_status='error' and
    the failing stage recorded — the debuggability contract (pipeline.py:517-518).
    The existing failure tests all crash at the MESH stage (run_dir still None),
    so this on-disk partial-trace branch was never asserted."""
    import structure_optimizer.core.pipeline as pipeline

    real_read_json = pipeline.read_json

    def fake_read_json(path):
        # read_json is used ONLY by VerificationAgent.run; inject an unknown
        # verification status so postcondition raises PipelineGateError — but
        # only AFTER the persistence stage already created run_dir on disk.
        if getattr(path, "name", "") == "verification.json":
            return {"status": "not_a_real_status"}
        return real_read_json(path)

    monkeypatch.setattr(pipeline, "read_json", fake_read_json)
    run_dir = tmp_path / "post_persist_fail"
    config = load_benchmark("mbb_beam", preset="smoke")

    with pytest.raises(PipelineGateError):
        pipeline.PipelineOrchestrator().run(PipelineContext(config=config, run_dir=run_dir))

    trace_path = run_dir / "agents_trace.json"
    assert trace_path.exists(), "post-persistence failure must persist a partial trace"
    trace = json.loads(trace_path.read_text())
    assert trace["terminal_status"] == "error"
    statuses = {a["name"]: a["status"] for a in trace["agents"]}
    assert statuses.get("verification") == "error"  # the failing stage, recorded
    assert statuses.get("persistence") == "ok"  # ran successfully before the failure
    assert "export_report" not in statuses  # never reached


# --------------------------------------------------------------------------- #
# determinism flag                                                              #
# --------------------------------------------------------------------------- #


def test_deterministic_trace_flag_zeroes_wall_ms(tmp_path, monkeypatch):
    monkeypatch.setenv("SO_TRACE_DETERMINISTIC", "1")
    config = load_benchmark("mbb_beam", preset="smoke")
    run_dir = PipelineOrchestrator().run(PipelineContext(config=config, run_dir=tmp_path / "det"))
    trace = json.loads((run_dir / "agents_trace.json").read_text())
    assert all(a["wall_ms"] == 0.0 for a in trace["agents"])
