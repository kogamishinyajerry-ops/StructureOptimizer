"""Wave O: DOE sampling + design lineage tracking tests.

Pins:

- ``lhs_samples`` covers each marginal uniformly + each row in ``[0, 1)``
- ``sobol_samples`` deterministic given seed; raises if scipy missing
- ``map_samples_to_grid`` returns valid override dicts
- ``LineageRecord`` JSON roundtrip
- ``build_lineage_tree`` collects nodes + reconstructs parent edges
- Study with sampling="lhs" runs n_samples candidates and writes lineage_tree.json
- Study with sampling="grid" still writes lineage_tree.json (tree of root nodes)
- Workflow.run_config writes lineage.json with parent/study/generation
- Sobol study integrates with scipy and produces n_samples candidates
- StudyConfig schema preserves new sampling/n_samples/seed fields in to_dict
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.lineage import (
    LineageRecord,
    build_lineage_tree,
    read_lineage,
    write_lineage,
)
from structure_optimizer.core.sampling import (
    lhs_samples,
    map_samples_to_grid,
    sobol_samples,
)
from structure_optimizer.core.study import StudyConfig, run_study

# --- LHS samples -------------------------------------------------------


def test_lhs_samples_shape_and_range():
    rng = np.random.default_rng(42)
    samples = lhs_samples(20, 3, rng)
    assert samples.shape == (20, 3)
    assert (samples >= 0.0).all() and (samples < 1.0).all()


def test_lhs_samples_per_dim_marginal_uniform():
    """Each dimension must place exactly one sample in each of n_samples
    bins partitioning [0, 1). This is the defining property of LHS."""
    rng = np.random.default_rng(0)
    n = 16
    samples = lhs_samples(n, 4, rng)
    for dim in range(4):
        bin_idx = np.floor(samples[:, dim] * n).astype(int)
        # 0..n-1 each appear exactly once
        assert sorted(bin_idx) == list(range(n)), f"dim {dim} bins {sorted(bin_idx)} != {list(range(n))}"


def test_lhs_samples_seed_determinism():
    rng_a = np.random.default_rng(123)
    rng_b = np.random.default_rng(123)
    a = lhs_samples(10, 2, rng_a)
    b = lhs_samples(10, 2, rng_b)
    np.testing.assert_array_equal(a, b)


def test_lhs_samples_rejects_zero_or_negative():
    rng = np.random.default_rng()
    with pytest.raises(ValueError, match="n_samples"):
        lhs_samples(0, 2, rng)
    with pytest.raises(ValueError, match="n_dims"):
        lhs_samples(5, 0, rng)


# --- Sobol samples -----------------------------------------------------


def test_sobol_samples_shape_and_range():
    pytest.importorskip("scipy")
    rng = np.random.default_rng(7)
    samples = sobol_samples(8, 3, rng)
    assert samples.shape == (8, 3)
    assert (samples >= 0.0).all() and (samples < 1.0).all()


def test_sobol_samples_seed_determinism():
    pytest.importorskip("scipy")
    rng_a = np.random.default_rng(999)
    rng_b = np.random.default_rng(999)
    a = sobol_samples(8, 2, rng_a)
    b = sobol_samples(8, 2, rng_b)
    np.testing.assert_array_equal(a, b)


# --- map_samples_to_grid ----------------------------------------------


def test_map_samples_to_grid_returns_valid_overrides():
    parameters = {"volume_fraction": [0.3, 0.4, 0.5], "filter_radius": [1.0, 2.0]}
    samples = np.array([[0.1, 0.6], [0.5, 0.99], [0.9, 0.0]])
    overrides = map_samples_to_grid(samples, parameters)
    assert len(overrides) == 3
    for o in overrides:
        assert o["volume_fraction"] in [0.3, 0.4, 0.5]
        assert o["filter_radius"] in [1.0, 2.0]
    # spot check: row [0.1, 0.6] → vol=0.3 (idx 0), radius=2.0 (idx 1)
    assert overrides[0] == {"volume_fraction": 0.3, "filter_radius": 2.0}
    # row [0.9, 0.0] → vol=0.5 (idx 2), radius=1.0 (idx 0)
    assert overrides[2] == {"volume_fraction": 0.5, "filter_radius": 1.0}


def test_map_samples_to_grid_dim_mismatch_raises():
    samples = np.array([[0.5, 0.5]])
    parameters = {"only_one": [1, 2]}
    with pytest.raises(ValueError, match="dims"):
        map_samples_to_grid(samples, parameters)


# --- Lineage roundtrip ------------------------------------------------


def test_lineage_record_roundtrip(tmp_path):
    record = LineageRecord(
        run_id="20260516-123456-789012",
        parent_id="20260516-120000-000000",
        study_id="cantilever_test",
        generation=2,
    )
    write_lineage(tmp_path, record)
    loaded = read_lineage(tmp_path)
    assert loaded == record


def test_lineage_record_no_parent_roundtrip(tmp_path):
    record = LineageRecord(run_id="run_001")
    write_lineage(tmp_path, record)
    loaded = read_lineage(tmp_path)
    assert loaded is not None
    assert loaded.run_id == "run_001"
    assert loaded.parent_id is None
    assert loaded.study_id is None
    assert loaded.generation == 0


def test_read_lineage_returns_none_when_missing(tmp_path):
    assert read_lineage(tmp_path) is None


# --- Tree builder ------------------------------------------------------


def test_build_lineage_tree_root_nodes_only(tmp_path):
    """Tree of 3 root candidates (no parents) → 3 nodes, 0 edges."""
    for i in range(1, 4):
        sub = tmp_path / f"candidate_{i:03d}"
        sub.mkdir()
        write_lineage(sub, LineageRecord(run_id=f"run_{i:03d}", study_id=tmp_path.name))
    tree = build_lineage_tree(tmp_path)
    assert tree["study_id"] == tmp_path.name
    assert len(tree["nodes"]) == 3
    assert tree["edges"] == []


def test_build_lineage_tree_with_parent_edges(tmp_path):
    """candidate_002 derived from candidate_001's run_id → 1 edge."""
    sub1 = tmp_path / "candidate_001"
    sub1.mkdir()
    write_lineage(sub1, LineageRecord(run_id="run_a", study_id=tmp_path.name, generation=0))
    sub2 = tmp_path / "candidate_002"
    sub2.mkdir()
    write_lineage(
        sub2,
        LineageRecord(run_id="run_b", parent_id="run_a", study_id=tmp_path.name, generation=1),
    )
    tree = build_lineage_tree(tmp_path)
    assert len(tree["nodes"]) == 2
    assert tree["edges"] == [{"from": "candidate_001", "to": "candidate_002"}]


def test_build_lineage_tree_skips_subdirs_without_lineage(tmp_path):
    sub_with = tmp_path / "candidate_001"
    sub_with.mkdir()
    write_lineage(sub_with, LineageRecord(run_id="run_a"))
    sub_without = tmp_path / "candidate_002"
    sub_without.mkdir()  # no lineage.json
    sub_unrelated = tmp_path / "not_a_candidate"
    sub_unrelated.mkdir()
    write_lineage(sub_unrelated, LineageRecord(run_id="run_unrelated"))  # not candidate_*

    tree = build_lineage_tree(tmp_path)
    candidate_ids = [n["candidate_id"] for n in tree["nodes"]]
    assert candidate_ids == ["candidate_001"]


# --- workflow.run_config writes lineage.json ---------------------------


def test_run_config_writes_lineage_json(tmp_path):
    from structure_optimizer.core.workflow import run_config

    config = load_benchmark("mbb_beam", preset="smoke")
    run_dir = tmp_path / "run"
    run_config(config, run_dir=run_dir, parent_id="parent_xyz", study_id="study_abc", generation=3)
    record = read_lineage(run_dir)
    assert record is not None
    assert record.parent_id == "parent_xyz"
    assert record.study_id == "study_abc"
    assert record.generation == 3
    assert record.run_id == "run"


def test_run_config_lineage_defaults_when_unspecified(tmp_path):
    from structure_optimizer.core.workflow import run_config

    config = load_benchmark("mbb_beam", preset="smoke")
    run_dir = tmp_path / "run"
    run_config(config, run_dir=run_dir)
    record = read_lineage(run_dir)
    assert record is not None
    assert record.parent_id is None
    assert record.study_id is None
    assert record.generation == 0


# --- DOE study integration --------------------------------------------


def _make_lhs_study(tmp_dir: Path, n_samples: int = 3) -> Path:
    cfg = {
        "benchmark": "cantilever",
        "preset": "smoke",
        "parameters": {"volume_fraction": [0.30, 0.40, 0.50, 0.60]},
        "sampling": "lhs",
        "n_samples": n_samples,
        "seed": 7,
        "max_candidates": n_samples + 2,
        "ranking": ["mass", "compliance"],
        "objectives": [
            {"name": "mass", "direction": "minimize"},
            {"name": "compliance", "direction": "minimize"},
        ],
    }
    path = tmp_dir / "study.json"
    path.write_text(json.dumps(cfg))
    return path


def test_run_study_lhs_produces_n_candidates_and_lineage_tree(tmp_path):
    cfg_path = _make_lhs_study(tmp_path, n_samples=3)
    html_path = run_study(cfg_path)
    study_dir = html_path.parent
    # 3 candidate dirs expected
    candidate_dirs = sorted(p.name for p in study_dir.iterdir() if p.name.startswith("candidate_"))
    assert candidate_dirs == ["candidate_001", "candidate_002", "candidate_003"]
    # lineage_tree.json exists with 3 nodes, 0 edges (LHS = root candidates)
    tree = json.loads((study_dir / "lineage_tree.json").read_text())
    assert len(tree["nodes"]) == 3
    assert tree["edges"] == []
    # all lineage.json files have study_id matching the study dir name
    for d in candidate_dirs:
        record = read_lineage(study_dir / d)
        assert record is not None
        assert record.study_id == study_dir.name


def test_run_study_grid_writes_lineage_tree(tmp_path):
    cfg = {
        "benchmark": "cantilever",
        "preset": "smoke",
        "parameters": {"volume_fraction": [0.30, 0.50]},
        "max_candidates": 6,
    }
    cfg_path = tmp_path / "study.json"
    cfg_path.write_text(json.dumps(cfg))
    html_path = run_study(cfg_path)
    tree = json.loads((html_path.parent / "lineage_tree.json").read_text())
    assert len(tree["nodes"]) == 2
    assert tree["edges"] == []  # grid samples are roots


def test_run_study_sobol_produces_n_candidates(tmp_path):
    pytest.importorskip("scipy")
    cfg = {
        "benchmark": "cantilever",
        "preset": "smoke",
        "parameters": {"volume_fraction": [0.30, 0.40, 0.50, 0.60]},
        "sampling": "sobol",
        "n_samples": 4,
        "seed": 13,
        "max_candidates": 8,
    }
    cfg_path = tmp_path / "study.json"
    cfg_path.write_text(json.dumps(cfg))
    html_path = run_study(cfg_path)
    candidate_dirs = sorted(p.name for p in html_path.parent.iterdir() if p.name.startswith("candidate_"))
    assert len(candidate_dirs) == 4


def test_run_study_lhs_seed_reproducibility(tmp_path):
    """Two LHS runs with same seed must produce identical candidate
    parameter sequences (the Pareto ranking column should match)."""
    a_dir = tmp_path / "a"
    a_dir.mkdir()
    b_dir = tmp_path / "b"
    b_dir.mkdir()

    cfg_template = {
        "benchmark": "cantilever",
        "preset": "smoke",
        "parameters": {"volume_fraction": [0.30, 0.40, 0.50, 0.60]},
        "sampling": "lhs",
        "n_samples": 3,
        "seed": 42,
        "max_candidates": 6,
    }
    (a_dir / "study.json").write_text(json.dumps(cfg_template))
    (b_dir / "study.json").write_text(json.dumps(cfg_template))

    html_a = run_study(a_dir / "study.json")
    html_b = run_study(b_dir / "study.json")

    # extract the parameters_json column from each candidates.csv
    def _params(csv_path: Path) -> list[str]:
        rows = csv_path.read_text().strip().split("\n")
        header = rows[0].split(",")
        idx = header.index("parameters_json")
        # sort to make order-independent (different study runs may schedule differently)
        return sorted(row.split(",", maxsplit=len(header))[idx] for row in rows[1:])

    assert _params(html_a.parent / "candidates.csv") == _params(html_b.parent / "candidates.csv")


# --- StudyConfig schema preservation -----------------------------------


def test_study_config_grid_default_omits_sampling_in_dict():
    cfg = StudyConfig(
        benchmark="cantilever",
        preset=None,
        parameters={"volume_fraction": [0.3]},
        ranking=["mass"],
        objectives=[{"name": "mass", "direction": "minimize"}],
    )
    d = cfg.to_dict()
    # default grid → no sampling field
    assert "sampling" not in d
    assert "n_samples" not in d
    assert "seed" not in d


def test_study_config_lhs_round_trip_includes_sampling_fields():
    cfg = StudyConfig(
        benchmark="cantilever",
        preset=None,
        parameters={"volume_fraction": [0.3, 0.5]},
        ranking=["mass"],
        objectives=[{"name": "mass", "direction": "minimize"}],
        sampling="lhs",
        n_samples=4,
        seed=99,
    )
    d = cfg.to_dict()
    assert d["sampling"] == "lhs"
    assert d["n_samples"] == 4
    assert d["seed"] == 99


def test_study_config_sampling_validation_rejects_bad_method(tmp_path):
    from structure_optimizer.core.study import load_study_config

    cfg = {
        "benchmark": "cantilever",
        "preset": "smoke",
        "parameters": {"volume_fraction": [0.3]},
        "sampling": "halton",  # not in {grid, lhs, sobol}
    }
    cfg_path = tmp_path / "study.json"
    cfg_path.write_text(json.dumps(cfg))
    with pytest.raises(ValueError, match="sampling"):
        load_study_config(cfg_path)


def test_study_config_lhs_requires_n_samples(tmp_path):
    from structure_optimizer.core.study import load_study_config

    cfg = {
        "benchmark": "cantilever",
        "preset": "smoke",
        "parameters": {"volume_fraction": [0.3]},
        "sampling": "lhs",
    }
    cfg_path = tmp_path / "study.json"
    cfg_path.write_text(json.dumps(cfg))
    with pytest.raises(ValueError, match="n_samples"):
        load_study_config(cfg_path)
