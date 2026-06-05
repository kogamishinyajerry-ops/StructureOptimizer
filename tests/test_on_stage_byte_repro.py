"""Byte-reproducibility guard for the ``on_stage`` observational seam.

The agent-rail UI attaches an ``on_stage`` callback (server path only). This is
the load-bearing proof that attaching it perturbs NOTHING the engine writes
except the new ``agents_trace.json``: a run with ``on_stage=None`` (CLI/study
default) and a run with a no-op ``on_stage`` callback produce byte-identical
stable artifacts. If a future change ever lets ``on_stage`` leak into engine
state, this test fails — and no ``on_stage`` code should merge while it is red.

Also pins the Codex C2 "live == disk" contract: each ``"end"`` event's
``record`` equals the corresponding ``agents_trace.json`` entry once the
nondeterministic ``wall_ms`` is dropped.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.run_store import read_json
from structure_optimizer.core.workflow import run_config

# Every stable on-disk artifact. ``agents_trace.json`` is the ONE new file and
# carries the only nondeterministic field (``wall_ms``); it is excluded here and
# zeroed under SO_TRACE_DETERMINISTIC=1 (see pipeline._write_trace).
STABLE_ARTIFACTS = (
    "input.json",
    "density.npy",
    "metrics.csv",
    "summary.json",
    "verification.json",
    "lineage.json",
    "manufacturability.json",
)


def _hashes(run_dir: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in STABLE_ARTIFACTS:
        p = run_dir / name
        assert p.exists(), f"expected stable artifact missing: {name}"
        out[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@pytest.fixture(autouse=True)
def _deterministic_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    # Zero wall_ms so even agents_trace.json is stable (not compared here, but
    # keeps the run fully deterministic).
    monkeypatch.setenv("SO_TRACE_DETERMINISTIC", "1")


def test_on_stage_none_vs_noop_is_byte_identical(tmp_path: Path) -> None:
    config = load_benchmark("simple_bracket", preset="smoke")

    # Run both into the SAME absolute run dir (deleting between) so the ONLY
    # variable is the callback. (summary.json legitimately embeds the absolute
    # report.md path, so two different dirs would differ on that field alone —
    # a pre-existing, on_stage-independent fact.)
    run_dir = tmp_path / "r"
    none_dir = run_config(config, run_dir=run_dir)
    none_hashes = _hashes(none_dir)

    shutil.rmtree(run_dir)

    events: list[dict] = []
    noop_dir = run_config(config, run_dir=run_dir, on_stage=events.append)

    assert _hashes(noop_dir) == none_hashes, "on_stage callback perturbed a stable artifact"


def test_on_stage_callback_actually_fires(tmp_path: Path) -> None:
    """The seam must be live, not dead: one start + one end per stage (7 stages)."""
    config = load_benchmark("simple_bracket", preset="smoke")
    events: list[dict] = []
    run_config(config, run_dir=tmp_path / "r", on_stage=events.append)

    assert events, "on_stage callback was never invoked"
    phases = [e["phase"] for e in events]
    assert phases.count("start") == 7, phases
    assert phases.count("end") == 7, phases
    assert "error" not in phases
    # start events carry no record; end events do.
    assert all(e["record"] is None for e in events if e["phase"] == "start")
    assert all(e["record"] is not None for e in events if e["phase"] == "end")


def test_live_stage_records_equal_on_disk_trace(tmp_path: Path) -> None:
    """Codex C2: the live ``end`` records == on-disk agents_trace.json (minus wall_ms)."""
    config = load_benchmark("simple_bracket", preset="smoke")
    events: list[dict] = []
    run_dir = run_config(config, run_dir=tmp_path / "r", on_stage=events.append)

    disk = read_json(run_dir / "agents_trace.json")["agents"]
    end_records = [e["record"] for e in events if e["phase"] == "end"]

    def _strip(rec: dict) -> dict:
        return {k: v for k, v in rec.items() if k != "wall_ms"}

    assert [_strip(r) for r in end_records] == [_strip(r) for r in disk]


def test_gate_failure_reraises_original_and_emits_stage_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Codex C1 regression: a PipelineGateError must propagate UNCHANGED (not the
    bogus ``RuntimeError('No active exception to reraise')`` the prior bare-raise
    produced), and the failing stage must emit exactly one ``stage_error`` event.
    """
    from structure_optimizer.core import pipeline as pl

    config = load_benchmark("simple_bracket", preset="smoke")
    # Force the mesh stage's gate to fail (its postcondition rejects a mesh with
    # no ``.elements``). run_dir is still None here, exercising the early-failure
    # path that the old bare-raise mangled.
    monkeypatch.setattr(pl, "create_structured_mesh", lambda cfg: None)

    events: list[dict] = []
    with pytest.raises(pl.PipelineGateError, match="mesh was not constructed"):
        run_config(config, run_dir=tmp_path / "r", on_stage=events.append)

    errors = [e for e in events if e["phase"] == "error"]
    assert len(errors) == 1
    assert errors[0]["agent"] == "mesh"
    assert errors[0]["record"]["status"] == "error"
    assert errors[0]["record"]["gate"]["ok"] is False
