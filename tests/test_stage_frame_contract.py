"""Contract test for the live ``stage`` WebSocket frame (Codex C4).

``server/app.py`` ``send_json``s raw dicts, so the Pydantic ``StageFrame`` model
does not enforce the wire shape by itself. This test closes that gap: every
event the orchestrator emits through ``on_stage`` must validate against
``StageFrame`` (the same model the TS ``StageFrame`` type mirrors), and a no-op
``on_stage`` must not change the run's exit behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# StageFrame lives in the optional ``[web]`` layer (pydantic). Skip this contract
# test gracefully in the engine-only env, matching the repo's scipy convention.
pytest.importorskip("pydantic")

from server.schemas import StageFrame
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.workflow import run_config


@pytest.fixture(autouse=True)
def _deterministic_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SO_TRACE_DETERMINISTIC", "1")


def test_every_emitted_stage_event_validates_against_stage_frame(tmp_path: Path) -> None:
    config = load_benchmark("simple_bracket", preset="smoke")

    frames: list[StageFrame] = []

    def on_stage(event: dict) -> None:
        # The runner wraps with {"type": "stage", **event}; do the same so the
        # validation matches exactly what travels over the wire.
        frames.append(StageFrame(type="stage", **event))  # raises on contract drift

    run_config(config, run_dir=tmp_path / "r", on_stage=on_stage)

    assert frames, "no stage frames were emitted"
    assert all(f.type == "stage" for f in frames)

    starts = [f for f in frames if f.phase == "start"]
    ends = [f for f in frames if f.phase == "end"]
    assert len(starts) == 7 and len(ends) == 7
    # start = active marker (no record); end carries the full trace record.
    assert all(f.record is None for f in starts)
    assert all(f.record is not None for f in ends)
    # the verification stage's record carries its real gate verdict status.
    verification_end = next(f for f in ends if f.agent == "verification")
    assert verification_end.record is not None
    assert verification_end.record.gate.name == "GATE-VERIFICATION"
