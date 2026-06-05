"""Unhappy-path agent-rail coverage: a verification gate that FAILS but does
NOT abort the run (the "record-not-abort" tier of the 3-tier gate model).

The happy path is covered by test_stage_frame_contract.py (7 start + 7 end
frames, every gate ok). The structural-abort path (a stage raising
PipelineGateError -> phase=='error' frame + run aborts) is covered by
test_on_stage_byte_repro.py. The MIDDLE tier — the agent-rail's core honesty
claim — was untested: a stage whose ``gate.ok`` is False must still travel
start->end AND the run must run on to completion (verification records a veto,
it does not abort).

Deterministic failure recipe (verified against live code): ``stress_penalty``
defaults to 0.0, so the optimizer minimises plain compliance and ignores the
stress field; overriding the verification stress ``limit`` to an impossible
1e-9 therefore guarantees the post-run check fails ->
``verification.json`` status ``stress_constraint_failed`` ->
``VerificationAgent.postcondition`` returns ``GateVerdict(ok=False)``
(structure_optimizer/core/pipeline.py:383) WITHOUT raising -> the orchestrator
records ``status='gate_failed'`` and runs on through ``export_report``.
"""

from __future__ import annotations

import dataclasses
import json

import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.workflow import run_config


def _failing_stress_config():
    """stress_limited_bracket (smoke) with an impossible stress limit so its
    post-run verification deterministically fails."""
    cfg = load_benchmark("stress_limited_bracket", preset="smoke")
    sc = dataclasses.replace(cfg.stress_constraint, limit=1e-9)
    return dataclasses.replace(cfg, stress_constraint=sc)


@pytest.fixture(scope="module")
def failed_gate_run(tmp_path_factory):
    """Run the failing config once; share the captured frames + run_dir."""
    frames: list[dict] = []
    # run_config's persistence stage mkdir(exist_ok=False)s run_dir, so it must
    # NOT already exist — point at a fresh subdir of the (existing) temp dir.
    run_dir = run_config(
        _failing_stress_config(),
        run_dir=tmp_path_factory.mktemp("failed_gate") / "run",
        on_stage=frames.append,
    )
    return frames, run_dir


def test_failed_verification_gate_surfaces_and_does_not_abort(failed_gate_run) -> None:
    frames, run_dir = failed_gate_run

    # Deterministic failure. Canary: if stress ever becomes a hard optimizer
    # constraint, this status flips and the test fails loudly (by design).
    verification = json.loads((run_dir / "verification.json").read_text())
    assert verification["status"] == "stress_constraint_failed"

    # The verification stage's END frame carries the FAILED gate verdict.
    ends = [f for f in frames if f["agent"] == "verification" and f["phase"] == "end"]
    assert len(ends) == 1
    gate = ends[0]["record"]["gate"]
    assert gate["ok"] is False
    assert gate["verdict_status"] == "stress_constraint_failed"
    assert ends[0]["record"]["status"] == "gate_failed"

    # Record-not-abort: the run continued PAST the failed gate to completion.
    agents = [a["name"] for a in json.loads((run_dir / "agents_trace.json").read_text())["agents"]]
    assert agents.index("export_report") > agents.index("verification")
    # A failed gate is NOT a structural error: no phase=='error' frame was emitted.
    assert not [f for f in frames if f["phase"] == "error"]


def test_failed_gate_frame_validates_on_the_wire(failed_gate_run) -> None:
    """The failed gate (gate.ok=False) must satisfy the same StageFrame contract
    as a happy frame, so the unhappy path travels the WebSocket wire intact."""
    pytest.importorskip("pydantic")
    from server.schemas import StageFrame

    frames, _ = failed_gate_run
    # The runner wraps each event with {"type": "stage", **event}; mirror that.
    validated = [StageFrame(type="stage", **f) for f in frames]
    verification_end = next(f for f in validated if f.agent == "verification" and f.phase == "end")
    assert verification_end.record is not None
    assert verification_end.record.gate.ok is False
    assert verification_end.record.gate.verdict_status == "stress_constraint_failed"
