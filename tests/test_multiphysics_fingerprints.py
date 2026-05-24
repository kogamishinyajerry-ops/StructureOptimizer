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
from structure_optimizer.core.stl_export import marching_squares_contours, polygon_area

FINGERPRINT_DIR = Path(__file__).parent / "fingerprints"
TOLERANCE = 1e-9


# --- deterministic recipes shared with scripts/generate_v6_fingerprints.py ---

def _fp_linear_limit_state(u) -> float:
    """v6 FORM fingerprint limit state g(u) = 10 − (3u₀ + 4u₁); β = 10/5 = 2."""
    u = np.asarray(u, dtype=float)
    return float(10.0 - (3.0 * u[0] + 4.0 * u[1]))


def _fp_disk_field(n: int, r: float, cx: float = 0.5, cy: float = 0.5):
    """v6 marching-squares fingerprint field: a disk level set on the unit square."""
    xs = np.linspace(0.0, 1.0, n)
    ys = np.linspace(0.0, 1.0, n)
    gx, gy = np.meshgrid(xs, ys)
    return r * r - ((gx - cx) ** 2 + (gy - cy) ** 2), xs, ys


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

    if kind == "total_lagrangian":
        from structure_optimizer.core.total_lagrangian import solve_total_lagrangian

        config = load_benchmark(bench, preset=preset)
        mesh = create_structured_mesh(config)
        densities = np.full(mesh.elements.shape[0], 1.0)
        r = solve_total_lagrangian(config, mesh, densities, n_load_steps=rec["n_load_steps"])
        checks = [
            ("load_steps", rec["load_steps"], r.load_steps),
            ("max_disp_per_step", rec["max_disp_per_step"], r.max_displacements),
            ("max_displacement", rec["max_displacement"], float(r.max_displacements[-1])),
            ("n_newton_iters", rec["n_newton_iters"], r.n_newton_iters),
            ("converged", rec["converged"], r.converged),
        ]
        return np.asarray(r.displacements), ("displacements_sha256", rec["displacements_sha256"]), checks

    if kind == "damped_frequency_response":
        from structure_optimizer.core.freq_response import solve_damped_frequency_response

        config = load_benchmark(bench, preset=preset)
        mesh = create_structured_mesh(config)
        densities = np.full(mesh.elements.shape[0], 1.0)
        r = solve_damped_frequency_response(
            config, mesh, densities, omega=rec["omega"], alpha=rec["alpha"], beta=rec["beta"]
        )
        checks = [
            ("max_magnitude", rec["max_magnitude"], r.max_magnitude),
            ("response_norm", rec["response_norm"], r.response_norm),
            ("alpha", rec["alpha"], r.alpha),
            ("beta", rec["beta"], r.beta),
        ]
        return np.asarray(r.magnitude), ("magnitude_sha256", rec["magnitude_sha256"]), checks

    if kind == "anisotropic_thermal":
        from structure_optimizer.core.thermal import conductivity_tensor, solve_thermal
        from structure_optimizer.core.thermal_simp import load_thermal_benchmark

        config, k_scalar, sources, bcs = load_thermal_benchmark(bench, preset=preset)
        mesh = create_structured_mesh(config)
        densities = np.full(mesh.elements.shape[0], 1.0)
        ktensor = conductivity_tensor(rec["kxx"], rec["kyy"], rec["kxy"])
        r = solve_thermal(config, mesh, densities, k_scalar, sources, bcs, conductivity_tensor=ktensor)
        checks = [
            ("thermal_compliance", rec["thermal_compliance"], r.thermal_compliance),
            ("max_temperature", rec["max_temperature"], r.max_temperature),
        ]
        return np.asarray(r.temperatures), ("temperatures_sha256", rec["temperatures_sha256"]), checks

    if kind == "form_reliability":
        from structure_optimizer.core.reliability import form_hlrf

        r = form_hlrf(_fp_linear_limit_state, n_vars=rec["n_vars"])
        checks = [
            ("beta", rec["beta"], r.beta),
            ("p_failure", rec["p_failure"], r.p_failure),
            ("converged", rec["converged"], r.converged),
        ]
        return np.asarray(r.mpp), ("mpp_sha256", rec["mpp_sha256"]), checks

    if kind == "marching_squares":
        field, xs, ys = _fp_disk_field(rec["grid_n"], rec["radius"])
        loops = [lp for lp in marching_squares_contours(field, xs, ys, level=0.0) if polygon_area(lp) > 1e-12]
        total_area = sum(polygon_area(lp) for lp in loops)
        pts = np.vstack([np.asarray(lp, dtype=float) for lp in loops]) if loops else np.zeros((0, 2))
        checks = [
            ("total_area", rec["total_area"], total_area),
            ("n_loops", rec["n_loops"], len(loops)),
        ]
        return pts, ("contour_sha256", rec["contour_sha256"]), checks

    if kind == "tl_adjoint":
        from structure_optimizer.core.nonlinear_simp import tl_adjoint_compliance_sensitivity

        config = load_benchmark(bench, preset=preset)
        mesh = create_structured_mesh(config)
        densities = np.full(mesh.elements.shape[0], 0.6)
        r = tl_adjoint_compliance_sensitivity(config, mesh, densities, n_load_steps=rec["n_load_steps"])
        checks = [
            ("compliance", rec["compliance"], r.compliance),
            ("converged", rec["converged"], r.converged),
        ]
        return np.asarray(r.sensitivity), ("sensitivity_sha256", rec["sensitivity_sha256"]), checks

    if kind == "nataf_correlated_form":
        from structure_optimizer.core.reliability import correlated_gaussian_reliability

        a0, a = rec["a0"], np.asarray(rec["a"])
        r = correlated_gaussian_reliability(rec["mean"], rec["std"], rec["correlation"], lambda x: a0 - a @ x)
        checks = [
            ("beta", rec["beta"], r.beta),
            ("p_failure", rec["p_failure"], r.p_failure),
            ("converged", rec["converged"], r.converged),
        ]
        return np.asarray(r.mpp), ("mpp_sha256", rec["mpp_sha256"]), checks

    if kind == "dynamic_compliance":
        from structure_optimizer.core.freq_response import dynamic_compliance_sensitivity

        config = load_benchmark(bench, preset=preset)
        mesh = create_structured_mesh(config)
        densities = np.full(mesh.elements.shape[0], 0.6)
        r = dynamic_compliance_sensitivity(config, mesh, densities, omega=rec["omega"], alpha=rec["alpha"], beta=rec["beta"])
        checks = [
            ("objective", rec["objective"], r.objective),
            ("c_real", rec["c_real"], r.dynamic_compliance.real),
            ("c_imag", rec["c_imag"], r.dynamic_compliance.imag),
        ]
        return np.asarray(r.sensitivity), ("sensitivity_sha256", rec["sensitivity_sha256"]), checks

    if kind == "anisotropic_thermal_field":
        from structure_optimizer.core.thermal import orientation_field_to_tensors, solve_thermal
        from structure_optimizer.core.thermal_simp import load_thermal_benchmark

        config, k_scalar, sources, bcs = load_thermal_benchmark(bench, preset=preset)
        mesh = create_structured_mesh(config)
        n_elem = mesh.elements.shape[0]
        densities = np.full(n_elem, 1.0)
        field = orientation_field_to_tensors(rec["kxx"], rec["kyy"], np.linspace(0.0, np.pi / 2, n_elem))
        r = solve_thermal(config, mesh, densities, k_scalar, sources, bcs, conductivity_tensor_field=field)
        checks = [
            ("thermal_compliance", rec["thermal_compliance"], r.thermal_compliance),
            ("max_temperature", rec["max_temperature"], r.max_temperature),
        ]
        return np.asarray(r.temperatures), ("temperatures_sha256", rec["temperatures_sha256"]), checks

    if kind == "earclip_polygon":
        from structure_optimizer.core.stl_export import _tri_area, triangulate_with_holes

        outer = [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (4.0, 4.0), (4.0, 10.0), (0.0, 10.0)]
        hole = [(1.0, 1.0), (3.0, 1.0), (3.0, 3.0), (1.0, 3.0)]
        pts, tris = triangulate_with_holes(outer, [hole])
        area = sum(_tri_area(pts[i], pts[j], pts[k]) for i, j, k in tris)
        checks = [
            ("n_triangles", rec["n_triangles"], len(tris)),
            ("cross_section_area", rec["cross_section_area"], area),
        ]
        return np.asarray(pts), ("vertices_sha256", rec["vertices_sha256"]), checks

    if kind == "nonlinear_oc":
        from structure_optimizer.core.nonlinear_simp import nonlinear_to_oc

        config = load_benchmark(bench, preset=preset)
        mesh = create_structured_mesh(config)
        r = nonlinear_to_oc(config, mesh, n_load_steps=rec["n_load_steps"], max_iter=rec["max_iter"])
        checks = [
            ("compliance_final", rec["compliance_final"], r.compliance_history[-1]),
            ("converged", rec["converged"], r.converged),
        ]
        return np.asarray(r.densities), ("densities_sha256", rec["densities_sha256"]), checks

    if kind == "general_nataf":
        from structure_optimizer.core.reliability import Marginal, build_nataf_general

        marginals = [Marginal("weibull", 5.0, 130.0), Marginal("gumbel", 70.0, 12.0)]
        nataf = build_nataf_general(marginals, np.asarray(rec["correlation_x"]))
        checks = [("rho_u_01", rec["rho_u_01"], nataf.correlation_u[0, 1])]
        return np.asarray(nataf.correlation_u), ("correlation_u_sha256", rec["correlation_u_sha256"]), checks

    if kind == "system_reliability":
        from structure_optimizer.core.reliability import system_reliability_series

        r = system_reliability_series(rec["betas"])
        bounds = np.array([r["p_failure_lower"], r["p_failure_upper"],
                           r["simple_lower"], r["simple_upper"]])
        checks = [
            ("p_failure_lower", rec["p_failure_lower"], r["p_failure_lower"]),
            ("p_failure_upper", rec["p_failure_upper"], r["p_failure_upper"]),
        ]
        return bounds, ("bounds_sha256", rec["bounds_sha256"]), checks

    if kind == "fibre_steering":
        from structure_optimizer.core.thermal_simp import (
            fibre_steering_thermal_to,
            load_thermal_benchmark,
        )

        config, _k, sources, bcs = load_thermal_benchmark(bench, preset=preset)
        mesh = create_structured_mesh(config)
        rho = np.full(mesh.elements.shape[0], 1.0)
        r = fibre_steering_thermal_to(config, mesh, rho, rec["kxx"], rec["kyy"],
                                      n_steps=rec["n_steps"], step=rec["step"],
                                      heat_sources=sources, thermal_bcs=bcs)
        checks = [
            ("compliance_initial", rec["compliance_initial"], r.compliance_history[0]),
            ("compliance_final", rec["compliance_final"], r.compliance_history[-1]),
        ]
        return np.asarray(r.angles), ("angles_sha256", rec["angles_sha256"]), checks

    if kind == "holed_cap":
        from structure_optimizer.core.stl_export import _tri_area, triangulate_with_holes

        outer = [(6.0, 6.0), (34.0, 6.0), (34.0, 34.0), (6.0, 34.0)]
        hole = [(15.0, 15.0), (25.0, 15.0), (25.0, 25.0), (15.0, 25.0)]
        pts, tris = triangulate_with_holes(outer, [hole])
        area = sum(_tri_area(pts[i], pts[j], pts[k]) for i, j, k in tris)
        checks = [
            ("n_triangles", rec["n_triangles"], len(tris)),
            ("cross_section_area", rec["cross_section_area"], area),
        ]
        return np.asarray(pts), ("vertices_sha256", rec["vertices_sha256"]), checks

    if kind == "mma_nonlinear":
        from structure_optimizer.core.nonlinear_simp import mma_nonlinear_to

        config = load_benchmark(bench, preset=preset)
        mesh = create_structured_mesh(config)
        r = mma_nonlinear_to(config, mesh, n_load_steps=rec["n_load_steps"], max_iter=rec["max_iter"])
        checks = [
            ("compliance_final", rec["compliance_final"], r.compliance_history[-1]),
            ("converged", rec["converged"], r.converged),
        ]
        return np.asarray(r.densities), ("densities_sha256", rec["densities_sha256"]), checks

    if kind == "band_gap":
        from structure_optimizer.core.freq_response import band_gap_sensitivity

        config = load_benchmark(bench, preset=preset)
        mesh = create_structured_mesh(config)
        densities = np.full(mesh.elements.shape[0], rec["density_fill"])
        gap, dgap = band_gap_sensitivity(config, mesh, densities, lower_mode=rec["lower_mode"])
        checks = [("gap", rec["gap"], gap)]
        return np.asarray(dgap), ("dgap_sha256", rec["dgap_sha256"]), checks

    if kind == "rosenblatt":
        from structure_optimizer.core.reliability import build_rosenblatt_normal

        rt = build_rosenblatt_normal(np.asarray(rec["mean"]), np.asarray(rec["cov"]))
        u = rt.x_to_u(np.asarray(rec["x"]))
        checks = [("u0", rec["u0"], u[0])]
        return np.asarray(u), ("u_sha256", rec["u_sha256"]), checks

    if kind == "coupled_thermal":
        from structure_optimizer.core.thermal_simp import (
            coupled_density_orientation_to,
            load_thermal_benchmark,
        )

        config, _k, sources, bcs = load_thermal_benchmark(bench, preset=preset)
        mesh = create_structured_mesh(config)
        r = coupled_density_orientation_to(
            config, mesh, rec["kxx"], rec["kyy"], n_outer=rec["n_outer"],
            n_orient_steps=rec["n_orient_steps"], heat_sources=sources, thermal_bcs=bcs)
        checks = [("compliance_final", rec["compliance_final"], r.compliance_history[-1])]
        return np.asarray(r.densities), ("densities_sha256", rec["densities_sha256"]), checks

    if kind == "slit_free":
        import tempfile
        from dataclasses import replace

        from structure_optimizer.core.stl_export import write_stl_slit_free_holes

        config = load_benchmark("cantilever", preset="smoke")
        config = replace(config, mesh=replace(config.mesh, nelx=40, nely=40, width=40.0, height=40.0))
        mesh = create_structured_mesh(config)
        rho = np.zeros(mesh.nelx * mesh.nely)
        for ey in range(mesh.nely):
            for ex in range(mesh.nelx):
                r = np.hypot(ex + 0.5 - 20.0, ey + 0.5 - 20.0)
                rho[mesh.element_index(ex, ey)] = 1.0 if 7.0 < r < 15.0 else 0.0
        info = write_stl_slit_free_holes(mesh, rho, tempfile.mktemp(suffix=".stl"))
        checks = [
            ("n_solid_cells", rec["n_solid_cells"], info["n_solid_cells"]),
            ("cross_section_area", rec["cross_section_area"], info["cross_section_area"]),
            ("is_watertight", rec["is_watertight"], info["is_watertight"]),
        ]
        return rho, ("densities_sha256", rec["densities_sha256"]), checks

    if kind == "multi_constraint":
        from structure_optimizer.core.nonlinear_simp import multi_constraint_mma

        config = load_benchmark(bench, preset=preset)
        mesh = create_structured_mesh(config)
        r = multi_constraint_mma(config, mesh, sigma_limit=rec["sigma_limit"], p=rec["p"], max_iter=rec["max_iter"])
        checks = [
            ("compliance_final", rec["compliance_final"], r.compliance_history[-1]),
            ("stress_final", rec["stress_final"], r.stress_history[-1]),
        ]
        return np.asarray(r.densities), ("densities_sha256", rec["densities_sha256"]), checks

    if kind == "target_band":
        from structure_optimizer.core.freq_response import target_band_placement
        from structure_optimizer.core.modal import solve_modal

        config = load_benchmark(bench, preset=preset)
        mesh = create_structured_mesh(config)
        rho0 = np.where(mesh.void_mask, config.optimization.min_density, config.optimization.volume_fraction)
        w1 = float(np.sqrt(solve_modal(config, mesh, rho0, n_modes=1).omega_squared[0]))
        lo, hi = rec["band_factors"]
        band = np.linspace(lo * w1, hi * w1, rec["band_n"])
        r = target_band_placement(config, mesh, band, beta=1e-4, n_steps=rec["n_steps"], p=rec["p"])
        checks = [("peak_final", rec["peak_final"], r.peak_final)]
        return np.asarray(r.densities), ("densities_sha256", rec["densities_sha256"]), checks

    if kind == "copula_rosenblatt":
        from structure_optimizer.core.reliability import Marginal, build_copula_rosenblatt, clayton_copula

        marginals = [Marginal(k, a, b) for k, a, b in rec["marginals"]]
        rb = build_copula_rosenblatt(marginals, clayton_copula(rec["theta"]))
        u = rb.x_to_u(np.asarray(rec["x"]))
        checks = [("u0", rec["u0"], u[0])]
        return np.asarray(u), ("u_sha256", rec["u_sha256"]), checks

    if kind == "simultaneous_coupled":
        from structure_optimizer.core.thermal_simp import (
            load_thermal_benchmark,
            simultaneous_density_orientation_mma,
        )

        config, _k, sources, bcs = load_thermal_benchmark(bench, preset=preset)
        mesh = create_structured_mesh(config)
        r = simultaneous_density_orientation_mma(
            config, mesh, rec["kxx"], rec["kyy"], max_iter=rec["max_iter"],
            heat_sources=sources, thermal_bcs=bcs)
        checks = [("compliance_final", rec["compliance_final"], r.compliance_history[-1])]
        return np.asarray(r.densities), ("densities_sha256", rec["densities_sha256"]), checks

    if kind == "smooth_watertight":
        import tempfile

        from structure_optimizer.core.stl_export import write_stl_smooth_watertight_holes

        n = 64
        xs = np.linspace(0.0, 1.0, n)
        ys = np.linspace(0.0, 1.0, n)
        gx, gy = np.meshgrid(xs, ys, indexing="xy")
        rr = np.sqrt((gx - 0.5) ** 2 + (gy - 0.5) ** 2)
        field = ((rr >= 0.25) & (rr <= 0.45)).astype(float)
        info = write_stl_smooth_watertight_holes(field, xs, ys, tempfile.mktemp(suffix=".stl"), n_samples=rec["n_samples"])
        checks = [
            ("n_triangles", rec["n_triangles"], info["n_triangles"]),
            ("cross_section_area", rec["cross_section_area"], info["cross_section_area"]),
            ("is_watertight", rec["is_watertight"], info["is_watertight"]),
        ]
        return field, ("field_sha256", rec["field_sha256"]), checks

    if kind == "qp_relaxed_stress":
        from structure_optimizer.core.simp import run_simp
        from structure_optimizer.core.stress import qp_relaxed_stress_pnorm_sensitivity

        config = load_benchmark(bench, preset=preset)
        mesh = create_structured_mesh(config)
        rho = run_simp(config, mesh).densities
        sigma_pn, dsdrho = qp_relaxed_stress_pnorm_sensitivity(config, mesh, rho, p=rec["p"], q=rec["q"])
        checks = [("sigma_pn", rec["sigma_pn"], sigma_pn)]
        return np.asarray(dsdrho), ("dsdrho_sha256", rec["dsdrho_sha256"]), checks

    if kind == "adaptive_band":
        from structure_optimizer.core.freq_response import adaptive_band_sample
        from structure_optimizer.core.modal import solve_modal

        config = load_benchmark(bench, preset=preset)
        mesh = create_structured_mesh(config)
        opt = config.optimization
        rho = np.where(mesh.void_mask, opt.min_density, opt.volume_fraction)
        w1 = float(np.sqrt(solve_modal(config, mesh, rho, n_modes=1).omega_squared[0]))
        lo, hi = rec["band_factors"]
        ab = adaptive_band_sample(
            config, mesh, rho, lo * w1, hi * w1, n_init=rec["n_init"], n_refine=rec["n_refine"], beta=rec["beta"]
        )
        checks = [("peak_value", rec["peak_value"], ab.peak_value), ("peak_omega", rec["peak_omega"], ab.peak_omega)]
        return np.asarray(ab.omegas), ("omegas_sha256", rec["omegas_sha256"]), checks

    if kind == "r2_indicator":
        from structure_optimizer.core.multi_objective_to import r2_indicator, reference_free_hypervolume

        front = np.asarray(rec["front"], dtype=float)
        r2 = r2_indicator(front, ideal=np.asarray(rec["ideal"], dtype=float))
        hv = reference_free_hypervolume(front, margin=rec["margin"])
        checks = [("r2", rec["r2"], r2), ("reference_free_hv", rec["reference_free_hv"], hv)]
        return np.array([r2, hv]), ("values_sha256", rec["values_sha256"]), checks

    if kind == "clayton_d_rosenblatt":
        from structure_optimizer.core.reliability import Marginal, build_clayton_rosenblatt

        marginals = [Marginal(k, a, b) for k, a, b in rec["marginals"]]
        tr = build_clayton_rosenblatt(marginals, theta=rec["theta"])
        u = tr.x_to_u(np.asarray(rec["x"]))
        checks = [("u0", rec["u0"], u[0])]
        return np.asarray(u), ("u_sha256", rec["u_sha256"]), checks

    if kind == "genz_mvn":
        from structure_optimizer.core.reliability import system_reliability_series_exact

        pf = system_reliability_series_exact(
            np.asarray(rec["betas"]), np.asarray(rec["correlation"]), n_samples=rec["n_samples"], seed=rec["seed"]
        )
        checks = [("p_failure", rec["p_failure"], pf)]
        return np.array([pf]), ("pf_sha256", rec["pf_sha256"]), checks

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
        # v5 multi-physics
        "vibrating_beam__smoke_modal",
        "heat_sink__smoke",
        "nonlinear_cantilever__smoke",
        "stochastic_uq_smoke",
        "stochastic_worst_case_smoke",
        # v6 production-grade (Wave LL closure)
        "tl_cantilever__smoke",
        "damped_fr_cantilever__smoke",
        "anisotropic_thermal_heat_sink__smoke",
        "form_linear_limit_state",
        "marching_squares_disk",
        # v7 production drivers (Wave TT closure)
        "tl_adjoint_cantilever__smoke",
        "nataf_correlated_form",
        "dynamic_compliance_cantilever__smoke",
        "anisotropic_thermal_field_heat_sink__smoke",
        "earclip_holed_polygon",
        # v8 closing-the-loop drivers (Wave BBB closure)
        "nonlinear_oc_cantilever__smoke",
        "general_nataf_weibull_gumbel",
        "system_reliability_series",
        "fibre_steering_heat_sink__smoke",
        "holed_cap_rect",
        # v9 second-order drivers (Wave JJJ closure)
        "mma_nonlinear_cantilever__smoke",
        "band_gap_cantilever__smoke",
        "rosenblatt_trivariate",
        "coupled_thermal_heat_sink__smoke",
        "slit_free_annulus",
        # v10 constraint-rich / manufacturable drivers (Wave RRR closure)
        "multi_constraint_cantilever__smoke",
        "target_band_cantilever__smoke",
        "copula_rosenblatt_clayton",
        "simultaneous_coupled_heat_sink__smoke",
        "smooth_watertight_ring",
        # v11 exact-&-robust drivers (Wave ZZZ closure)
        "qp_relaxed_stress_cantilever__smoke",
        "adaptive_band_cantilever__smoke",
        "reference_free_indicators",
        "clayton_d_rosenblatt_trivariate",
        "genz_system_reliability",
    }
    missing = expected - stems
    assert not missing, f"missing multi-physics fingerprints: {sorted(missing)}"
