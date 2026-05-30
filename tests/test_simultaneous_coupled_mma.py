"""Wave OOO (v10, D070): simultaneous (ρ,θ) MMA coupled thermal TO.

Quantitative anchors (analytical, not qualitative trend):
- the **combined sensitivity** stacked as ``[dC/dρ ; dC/dθ]`` matches central
  finite differences to relative error ≤ 1e-4 on the highest-sensitivity
  elements of *both* blocks (the merge is correct);
- simultaneous MMA reaches a thermal compliance **≤ the block-coordinate
  alternating minimisation** (GGG, D062) on the same problem — joint stepping
  escapes coordinate-wise stalls (the headline payoff);
- the volume inequality ``mean(ρ) ≤ vf`` is satisfied at convergence.

D062's reopening criterion: simultaneous (ρ,θ) MMA instead of alternating
block-coordinate descent.
"""

from __future__ import annotations

import numpy as np
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.thermal import orientation_field_to_tensors, solve_thermal
from structure_optimizer.core.thermal_simp import (
    anisotropic_thermal_sensitivity,
    coupled_density_orientation_to,
    load_thermal_benchmark,
    orientation_sensitivity,
    simultaneous_density_orientation_mma,
)

KXX, KYY = 5.0, 1.0


def _setup():
    config, _k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
    return config, create_structured_mesh(config), sources, bcs


def _compliance(config, mesh, rho, angles, sources, bcs):
    field = orientation_field_to_tensors(KXX, KYY, angles, 0.0)
    return float(
        solve_thermal(
            config,
            mesh,
            rho,
            conductivity=1.0,
            heat_sources=sources,
            thermal_bcs=bcs,
            conductivity_tensor_field=field,
        ).thermal_compliance
    )


def test_combined_sensitivity_matches_central_fd():
    config, mesh, sources, bcs = _setup()
    design = mesh.design_mask
    n_elem = mesh.elements.shape[0]
    rng = np.random.default_rng(0)
    rho = np.clip(0.5 + 0.1 * rng.standard_normal(n_elem), 0.2, 1.0)
    angles = 0.3 * rng.standard_normal(n_elem)

    field = orientation_field_to_tensors(KXX, KYY, angles, 0.0)
    d_rho = anisotropic_thermal_sensitivity(
        config, mesh, rho, conductivity_tensor_field=field, heat_sources=sources, thermal_bcs=bcs
    )
    d_theta = orientation_sensitivity(config, mesh, rho, angles, KXX, KYY, 0.0, sources, bcs)
    h = 1e-6

    # ρ block (design elements only)
    rho_order = [e for e in np.argsort(-np.abs(d_rho)) if design[e]][:4]
    for e in rho_order:
        rp = rho.copy()
        rp[e] += h
        rm = rho.copy()
        rm[e] -= h
        fd = (
            _compliance(config, mesh, rp, angles, sources, bcs) - _compliance(config, mesh, rm, angles, sources, bcs)
        ) / (2 * h)
        rel = abs(d_rho[e] - fd) / (abs(fd) + 1e-30)
        assert rel <= 1e-4, f"dC/dρ e{e}: {d_rho[e]:.4e} vs {fd:.4e} (rel {rel:.2e})"

    # θ block
    th_order = np.argsort(-np.abs(d_theta))[:4]
    for e in th_order:
        ap = angles.copy()
        ap[e] += h
        am = angles.copy()
        am[e] -= h
        fd = (_compliance(config, mesh, rho, ap, sources, bcs) - _compliance(config, mesh, rho, am, sources, bcs)) / (
            2 * h
        )
        rel = abs(d_theta[e] - fd) / (abs(fd) + 1e-30)
        assert rel <= 1e-4, f"dC/dθ e{e}: {d_theta[e]:.4e} vs {fd:.4e} (rel {rel:.2e})"


def test_simultaneous_mma_beats_or_matches_alternating():
    config, mesh, sources, bcs = _setup()
    sim = simultaneous_density_orientation_mma(
        config, mesh, KXX, KYY, max_iter=40, heat_sources=sources, thermal_bcs=bcs
    )
    alt = coupled_density_orientation_to(
        config, mesh, KXX, KYY, n_outer=8, n_orient_steps=8, heat_sources=sources, thermal_bcs=bcs
    )
    # joint stepping reaches a compliance at least as low (allow a tiny tolerance)
    assert sim.compliance_history[-1] <= alt.compliance_history[-1] * 1.001, (
        f"simultaneous {sim.compliance_history[-1]:.4e} worse than alternating {alt.compliance_history[-1]:.4e}"
    )


def test_simultaneous_mma_feasible_volume():
    config, mesh, sources, bcs = _setup()
    vf = config.optimization.volume_fraction
    sim = simultaneous_density_orientation_mma(
        config, mesh, KXX, KYY, max_iter=40, heat_sources=sources, thermal_bcs=bcs
    )
    assert sim.volume_history[-1] <= vf + 0.02, f"infeasible volume {sim.volume_history[-1]:.4f}"
    assert sim.densities.shape[0] == mesh.elements.shape[0]
    assert sim.angles.shape[0] == mesh.elements.shape[0]


def test_simultaneous_mma_contract_and_determinism():
    config, mesh, sources, bcs = _setup()
    a = simultaneous_density_orientation_mma(config, mesh, KXX, KYY, max_iter=8, heat_sources=sources, thermal_bcs=bcs)
    b = simultaneous_density_orientation_mma(config, mesh, KXX, KYY, max_iter=8, heat_sources=sources, thermal_bcs=bcs)
    assert np.allclose(a.densities, b.densities)
    assert np.allclose(a.angles, b.angles)
    assert len(a.compliance_history) == len(a.volume_history)
    # angles stay within the box bound
    assert np.all(np.abs(a.angles) <= np.pi / 2.0 + 1e-9)
