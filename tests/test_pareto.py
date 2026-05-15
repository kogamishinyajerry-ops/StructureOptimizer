"""Tests for v0.7 Pareto-front non-dominated sorting in study runner.

These tests exercise _assign_pareto_ranks directly with synthetic candidate
rows so we can construct unambiguous dominance scenarios without running
SIMP. Integration is covered indirectly by test_study.py.
"""

from __future__ import annotations

import json

import pytest
from structure_optimizer.core.study import (
    DEFAULT_OBJECTIVES,
    _assign_pareto_ranks,
    _dominates,
    _normalize_objectives,
    load_study_config,
)


def _row(candidate_id: str, mass: float, compliance: float, status: str = "passed") -> dict:
    return {
        "candidate_id": candidate_id,
        "mass": mass,
        "compliance": compliance,
        "verification_status": status,
    }


def test_pareto_front_two_objectives_known_solution():
    """Three candidates: A=(1,2), B=(2,1), C=(2,3). A and B are non-dominated;
    C is dominated by A."""
    rows = [
        _row("A", 1.0, 2.0),
        _row("B", 2.0, 1.0),
        _row("C", 2.0, 3.0),
    ]
    _assign_pareto_ranks(rows, DEFAULT_OBJECTIVES)
    by_id = {r["candidate_id"]: r["pareto_rank"] for r in rows}
    assert by_id["A"] == 1
    assert by_id["B"] == 1
    assert by_id["C"] == 2


def test_pareto_front_excludes_failed_candidates():
    rows = [
        _row("A", 1.0, 2.0, status="passed"),
        _row("B", 0.5, 0.5, status="connectivity_failed"),  # would dominate A if eligible
    ]
    _assign_pareto_ranks(rows, DEFAULT_OBJECTIVES)
    by_id = {r["candidate_id"]: r["pareto_rank"] for r in rows}
    assert by_id["A"] == 1
    assert by_id["B"] == ""  # excluded


def test_pareto_with_all_failed_assigns_no_rank():
    rows = [
        _row("A", 1.0, 2.0, status="connectivity_failed"),
        _row("B", 2.0, 1.0, status="solver_failed"),
    ]
    _assign_pareto_ranks(rows, DEFAULT_OBJECTIVES)
    assert all(r["pareto_rank"] == "" for r in rows)


def test_pareto_with_single_candidate_is_rank_1():
    rows = [_row("only", 1.0, 1.0)]
    _assign_pareto_ranks(rows, DEFAULT_OBJECTIVES)
    assert rows[0]["pareto_rank"] == 1


def test_pareto_with_maximize_direction_flips_sense():
    """If we're maximizing both objectives, A=(1,2) is dominated by B=(2,3)."""
    rows = [_row("A", 1.0, 2.0), _row("B", 2.0, 3.0)]
    objectives = [
        {"name": "mass", "direction": "maximize"},
        {"name": "compliance", "direction": "maximize"},
    ]
    _assign_pareto_ranks(rows, objectives)
    assert rows[0]["pareto_rank"] == 2
    assert rows[1]["pareto_rank"] == 1


def test_dominates_strict_inequality_required():
    objectives = [{"name": "x", "direction": "minimize"}]
    # equal points: neither dominates the other
    assert not _dominates([1.0], [1.0], objectives)
    # strict better in one
    assert _dominates([1.0], [2.0], objectives)
    # strict worse in one
    assert not _dominates([3.0], [2.0], objectives)


def test_dominates_with_mixed_directions():
    objectives = [
        {"name": "x", "direction": "minimize"},
        {"name": "y", "direction": "maximize"},
    ]
    # A=(1, 5), B=(2, 4): A dominates B (lower x and higher y)
    assert _dominates([1.0, 5.0], [2.0, 4.0], objectives)
    # A=(1, 5), B=(1, 6): B has higher y so dominates A
    assert _dominates([1.0, 6.0], [1.0, 5.0], objectives)


def test_normalize_objectives_uses_default_when_missing(tmp_path):
    config_path = tmp_path / "no_objectives.json"
    config_path.write_text(
        json.dumps(
            {
                "benchmark": "simple_bracket",
                "preset": "smoke",
                "parameters": {"volume_fraction": [0.4, 0.5]},
            }
        )
    )
    study = load_study_config(config_path)
    assert study.objectives == DEFAULT_OBJECTIVES


def test_normalize_objectives_rejects_bad_direction():
    with pytest.raises(ValueError, match="direction"):
        _normalize_objectives([{"name": "mass", "direction": "minimise"}])  # British spelling


def test_normalize_objectives_rejects_empty_list():
    with pytest.raises(ValueError, match="non-empty"):
        _normalize_objectives([])


def test_normalize_objectives_rejects_missing_name():
    with pytest.raises(ValueError, match="name"):
        _normalize_objectives([{"direction": "minimize"}])


def test_pareto_handles_numerical_ties_gracefully():
    """If multiple candidates are exactly equal on all objectives, neither
    dominates the other, so they share the same Pareto rank."""
    rows = [_row("A", 1.0, 2.0), _row("B", 1.0, 2.0), _row("C", 2.0, 3.0)]
    _assign_pareto_ranks(rows, DEFAULT_OBJECTIVES)
    by_id = {r["candidate_id"]: r["pareto_rank"] for r in rows}
    assert by_id["A"] == 1
    assert by_id["B"] == 1
    assert by_id["C"] == 2


def test_pareto_chain_assigns_increasing_ranks():
    """A dominates B dominates C — three distinct ranks."""
    rows = [_row("A", 1.0, 1.0), _row("B", 2.0, 2.0), _row("C", 3.0, 3.0)]
    _assign_pareto_ranks(rows, DEFAULT_OBJECTIVES)
    by_id = {r["candidate_id"]: r["pareto_rank"] for r in rows}
    assert by_id["A"] == 1
    assert by_id["B"] == 2
    assert by_id["C"] == 3
