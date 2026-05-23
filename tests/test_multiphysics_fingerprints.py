"""v5 multi-physics fingerprint regression tests.

Background — why this file exists
---------------------------------
The quad-SIMP fingerprints (``test_fingerprints.py``) and the triangle
fingerprints (``test_triangle_fingerprints.py``) each re-run their solver
and compare the result against a committed ``tests/fingerprints/*.json``.

The v5 multi-physics fingerprints (modal eigenvalues, thermal compliance,
geometric-nonlinear load-displacement, stochastic UQ / worst-case) carry a
*different* schema — they record physics-specific fields (e.g.
``omega_squared_sha256``, ``displacements_sha256``) and a ``rubric_version``
key, and they have **no** ``input_hash`` / ``scalar_sha256``.

They were committed in Waves Y / CC / DD as fingerprint fixtures, but no
test ever validated them: ``test_fingerprints.py`` globbed them in and
raised ``KeyError: 'input_hash'`` at runtime (the ``test_agent`` rubric
only ``--collect-only``-counts the files, so it never saw the crash). This
module closes that gap: it re-runs the correct solver with the parameters
stored in each fingerprint and compares.

Two-tier comparison (mirrors ``test_fingerprints.py`` + D011 rationale):
- Always: human-readable values compared with ``rtol = atol = 1e-9``.
- Strict bit-exact SHA-256 of the recorded full array is asserted only
  when ``REQUIRE_BIT_EXACT_FINGERPRINT=1`` (the canonical per-OS CI cell
  where last-bit reproducibility is achievable).

Reproduction recipes below were verified bit-exact on the dev host
(Apple Silicon + scipy) — these fingerprints are deterministic; the v5
stochastic ones pin ``rng_seed`` so they reproduce given the same seed.

To regenerate after an intentional behaviour change, re-run the solver
recipe in ``_rerun`` and re-commit the JSON (there is no standalone
generator script for these yet — a follow-up).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh

FINGERPRINT_DIR = Path(__file__).parent / "fingerprints"
TOLERANCE = 1e-9


def _multiphysics_fingerprints() -> list[Path]:
    """v5 physics fingerprints are the ones carrying a ``rubric_version`` key.

    Quad (``input_hash`` schema) and triangle (``triangle_*`` name) fixtures
    do not, so this discriminator keeps the three test modules disjoint.
    """
    out: list[Path] = []
    for path in sorted(FINGERPRINT_DIR.glob("*.json")):
        try:
            rec = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict) and "rubric_version" in rec:
            out.append(path)
    return out


def _sha256(arr: np.ndarray) -> str:
    """SHA-256 of float64 little-endian bytes — same convention as the
    quad / triangle generators (``np.ascontiguousarray(arr, '<f8')``)."""
    return "sha256:" + hashlib.sha256(np.ascontiguousarray(arr, dtype="<f8").tobytes()).hexdigest()


def _classify(rec: dict) -> str:
    """Return the physics kind. Most fingerprints carry an explicit ``kind``;
    the thermal one predates that field and is identified structurally."""
    kind = rec.get("kind")
    if kind:
        return kind
    if "final_thermal_compliance" in rec:
        return "thermal_simp"
    raise AssertionError(f"unrecognised v5 fingerprint schema: keys={sorted(rec)}")


def _rerun(rec: dict) -> tuple[np.ndarray, tuple[str, str], list[tuple[str, object, object]]]:
    """Re-run the recorded physics and return the comparison material.

    Returns ``(full_array, (sha_field_name, stored_sha), scalar_checks)`` where
    ``scalar_checks`` is a list of ``(name, stored, actual)`` compared tolerantly
    and ``full_array``'s SHA-256 is checked strictly under
    ``REQUIRE_BIT_EXACT_FINGERPRINT=1``.
    """
    kind = _classify(rec)
    bench = rec["benchmark"]
    preset = rec.get("preset")

    if kind == "modal_eigenvalues":
        from structure_optimizer.core.modal import solve_modal

        config = load_benchmark(bench, preset=preset)
        mesh = create_structured_mesh(config)
        densities = np.full(mesh.elements.shape[0], 1.0)
        r = solve_modal(config, mesh, densities, n_modes=rec["n_modes"], mass_type=rec["mass_type"])
        checks = [
            ("omega_squared", rec["omega_squared"], r.omega_squared),
            ("frequencies_hz", rec["frequencies_hz"], r.frequencies_hz),
        ]
        return np.asarray(r.omega_squared), ("omega_squared_sha256", rec["omega_squared_sha256"]), checks

    if kind == "thermal_simp":
        from structure_optimizer.core.thermal_simp import load_thermal_benchmark, run_thermal_simp

        config, k, sources, bcs = load_thermal_benchmark(bench, preset=preset)
        mesh = create_structured_mesh(config)
        r = run_thermal_simp(config, mesh, k, sources, bcs)
        checks = [
            ("final_thermal_compliance", rec["final_thermal_compliance"], r.final_result.thermal_compliance),
            ("final_max_temperature", rec["final_max_temperature"], r.final_result.max_temperature),
            ("final_volume_fraction", rec["final_volume_fraction"], r.metrics[-1].volume_fraction),
            ("iteration_count", rec["iteration_count"], len(r.metrics)),
            ("densities_first_8", [float(x) for x in rec["densities_first_8"]], r.densities[:8]),
        ]
        return np.asarray(r.densities), ("density_sha256", rec["density_sha256"]), checks

    if kind == "geometric_nonlinear_fem":
        from structure_optimizer.core.nonlinear_fem import solve_geometric_nonlinear

        config = load_benchmark(bench, preset=preset)
        mesh = create_structured_mesh(config)
        densities = np.full(mesh.elements.shape[0], 1.0)
        r = solve_geometric_nonlinear(config, mesh, densities, n_load_steps=rec["n_load_steps"])
        checks = [
            ("load_steps", rec["load_steps"], r.load_steps),
            ("max_disp_per_step", rec["max_disp_per_step"], r.max_displacements),
            ("max_displacement", rec["max_displacement"], float(r.max_displacements[-1])),
            ("n_newton_iters", rec["n_newton_iters"], r.n_newton_iters),
            ("converged", rec["converged"], r.converged),
        ]
        return np.asarray(r.displacements), ("displacements_sha256", rec["displacements_sha256"]), checks

    if kind == "monte_carlo_uq":
        from structure_optimizer.core.stochastic import UncertaintySpec, monte_carlo_uq

        config = load_benchmark(bench, preset=preset)
        mesh = create_structured_mesh(config)
        densities = np.full(mesh.elements.shape[0], 0.5)
        spec = UncertaintySpec(
            load_magnitude_std=rec["uncertainty"]["load_magnitude_std"],
            load_angle_std=rec["uncertainty"]["load_angle_std"],
        )
        r = monte_carlo_uq(
            config, mesh, densities, rng_seed=rec["rng_seed"], n_samples=rec["n_samples"], uncertainty=spec
        )
        checks = [
            ("mean", rec["mean"], r.mean),
            ("std", rec["std"], r.std),
            ("p95", rec["p95"], r.p95),
            ("max", rec["max"], r.max),
            ("samples_first_8", [float(x) for x in rec["samples_first_8"]], r.samples[:8]),
        ]
        return np.asarray(r.samples), ("samples_sha256", rec["samples_sha256"]), checks

    if kind == "worst_case_simp":
        from structure_optimizer.core.reliability import worst_case_simp

        config = load_benchmark(bench, preset=preset)
        mesh = create_structured_mesh(config)
        r = worst_case_simp(config, mesh, rng_seed=rec["rng_seed"], n_scenarios=rec["n_scenarios"])
        checks = [
            ("final_worst_compliance", rec["final_worst_compliance"], r.final_worst_compliance),
            ("final_mean_compliance", rec["final_mean_compliance"], r.final_mean_compliance),
            ("iteration_count", rec["iteration_count"], len(r.metrics)),
            ("densities_first_8", [float(x) for x in rec["densities_first_8"]], r.densities[:8]),
        ]
        return np.asarray(r.densities), ("density_sha256", rec["density_sha256"]), checks

    raise AssertionError(f"no rerun recipe for kind={kind!r} ({rec['benchmark']})")


@pytest.mark.parametrize("fp_path", _multiphysics_fingerprints(), ids=lambda p: p.stem)
def test_multiphysics_fingerprint_matches(fp_path):
    record = json.loads(fp_path.read_text())
    full_array, (sha_field, stored_sha), checks = _rerun(record)

    # Tolerant tier — always on. Catches algorithm regressions cross-platform.
    for name, stored, actual in checks:
        if isinstance(stored, bool):
            assert stored == actual, f"{fp_path.name}: {name} differs (stored={stored}, actual={actual})"
        else:
            np.testing.assert_allclose(
                np.asarray(actual, dtype=float),
                np.asarray(stored, dtype=float),
                rtol=TOLERANCE,
                atol=TOLERANCE,
                err_msg=f"{fp_path.name}: {name} differs above tolerance",
            )

    # Strict bit-exact tier — only on the canonical CI cell.
    if os.environ.get("REQUIRE_BIT_EXACT_FINGERPRINT") == "1":
        assert _sha256(full_array) == stored_sha, (
            f"{fp_path.name}: {sha_field} drifted (REQUIRE_BIT_EXACT_FINGERPRINT=1)"
        )


def test_multiphysics_fingerprint_set_present():
    """Guard the v5 multi-physics fixture set so a future glob/schema change
    can't silently drop them (they were unvalidated dead files before)."""
    stems = {p.stem for p in _multiphysics_fingerprints()}
    expected = {
        "vibrating_beam__smoke_modal",
        "heat_sink__smoke",
        "nonlinear_cantilever__smoke",
        "stochastic_uq_smoke",
        "stochastic_worst_case_smoke",
    }
    missing = expected - stems
    assert not missing, f"missing v5 multi-physics fingerprints: {sorted(missing)}"
