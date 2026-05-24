"""Stress aggregation utilities (Wave F / v1.6.0).

Per-element von Mises stress is already computed inside
``fem2d.solve_linear_elastic`` (kept private as ``_approx_element_stress``);
this module re-exposes it as a vector for downstream tooling, and adds two
smooth-max aggregations:

- **p-norm**: ``(Σ σ_e^p)^(1/p)`` — classical smoothed max
- **Kreisselmeier-Steinhauser (KS)**: ``(1/p) log Σ exp(p σ_e)`` (with
  max-shift for numerical stability)

Both approach ``max σ`` as ``p → ∞``; both are differentiable surrogates for
the discontinuous max. Use p = 8-12 for p-norm, p = 50-100 for KS in
practice (Le et al. 2010; Duysinx & Bendsøe 1998).

This module is integration-light: F 波 wires it through ``verification.py``
to produce ``stress_constraint_failed`` status when a final density fails a
configured limit. Full stress-constrained SIMP (gradient via adjoint method)
is intentionally **not** in v1.6 scope — that's a separate adjoint-method
ADR not yet written.
"""

from __future__ import annotations

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.mesh import StructuredMesh


def element_von_mises_stresses(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    displacements: np.ndarray,
) -> np.ndarray:
    """Per-element von Mises stress (length = number of elements).

    Uses the same plane-stress kernel as the FEM solver
    (``fem2d._approx_element_stress``); reading from displacement is
    cheaper than re-solving when stresses are needed at a known design.
    """
    from structure_optimizer.core.fem2d import _approx_element_stress

    stresses = np.zeros(mesh.elements.shape[0], dtype=float)
    for eid in range(mesh.elements.shape[0]):
        edofs = mesh.element_dofs(eid)
        ue = displacements[edofs]
        stresses[eid] = _approx_element_stress(mesh, eid, ue, config)
    return stresses


def p_norm_stress(
    stresses: np.ndarray,
    p: float,
    mask: np.ndarray | None = None,
) -> float:
    """Compute ``(Σ σ_e^p)^(1/p)`` over (optionally masked) elements.

    Uses max-shift normalization to avoid overflow for large p. Returns 0.0
    if no elements remain after masking or all stresses are zero.
    """
    if p <= 0:
        raise ValueError("p must be positive")
    s = stresses[mask] if mask is not None else stresses
    if s.size == 0:
        return 0.0
    s_abs = np.abs(s)
    smax = float(s_abs.max())
    if smax == 0.0:
        return 0.0
    normalized = s_abs / smax
    return float(smax * np.sum(normalized**p) ** (1.0 / p))


def ks_stress(
    stresses: np.ndarray,
    p: float,
    mask: np.ndarray | None = None,
) -> float:
    """Kreisselmeier-Steinhauser smooth max: ``max σ + (1/p) log Σ exp(p (σ - max σ))``.

    The max-shift form is numerically stable for large p. KS approaches
    ``max σ`` faster than p-norm at the same p but has steeper gradients.
    """
    if p <= 0:
        raise ValueError("p must be positive")
    s = stresses[mask] if mask is not None else stresses
    if s.size == 0:
        return 0.0
    s_abs = np.abs(s)
    smax = float(s_abs.max())
    if smax == 0.0:
        return 0.0
    return float(smax + (1.0 / p) * np.log(np.sum(np.exp(p * (s_abs - smax)))))


def aggregate_stress(
    stresses: np.ndarray,
    aggregation: str,
    p: float,
    mask: np.ndarray | None = None,
) -> float:
    """Dispatch to ``p_norm_stress`` or ``ks_stress`` by ``aggregation`` string."""
    if aggregation == "p_norm":
        return p_norm_stress(stresses, p, mask)
    if aggregation == "ks":
        return ks_stress(stresses, p, mask)
    raise ValueError(f"unknown stress aggregation '{aggregation}'; expected 'p_norm' or 'ks'")


def _element_stress_matrix(config: BenchmarkConfig, mesh: StructuredMesh) -> np.ndarray:
    """The constant 3×8 operator ``S`` with ``[σx, σy, τxy] = S @ uₑ``.

    Differentiates the same finite-difference plane-stress kernel used by
    ``fem2d._approx_element_stress``: strains ``[εxx, εyy, γxy] = B uₑ`` with the
    edge-difference operator ``B`` (constant on a structured mesh), then the
    plane-stress constitutive matrix ``D`` gives ``S = D B``. Uniform mesh +
    material → one matrix for every element.
    """
    e = config.material.young_modulus
    nu = config.material.poisson_ratio
    hx = mesh.width / mesh.nelx
    hy = mesh.height / mesh.nely
    b = np.zeros((3, 8), dtype=float)
    b[0, [0, 2, 4, 6]] = np.array([-0.5, 0.5, 0.5, -0.5]) / hx
    b[1, [1, 3, 5, 7]] = np.array([-0.5, -0.5, 0.5, 0.5]) / hy
    b[2, [0, 2, 4, 6]] = np.array([-0.5, -0.5, 0.5, 0.5]) / hy
    b[2, [1, 3, 5, 7]] = np.array([-0.5, 0.5, 0.5, -0.5]) / hx
    c = e / (1.0 - nu**2)
    g = e / (2.0 * (1.0 + nu))
    d = np.array([[c, c * nu, 0.0], [c * nu, c, 0.0], [0.0, 0.0, g]])
    return d @ b


# von Mises quadratic form: σ² = sᵀ V s with s = [σx, σy, τxy]
_VON_MISES_FORM = np.array([[1.0, -0.5, 0.0], [-0.5, 1.0, 0.0], [0.0, 0.0, 3.0]])


def stress_pnorm_sensitivity(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    p: float = 8.0,
    mask: np.ndarray | None = None,
) -> tuple[float, np.ndarray]:
    """Density sensitivity ``dσ_PN/dρ`` of the p-norm von Mises stress via the
    adjoint method (Wave KKK, D066).

    The aggregated measure is ``σ_PN = (Σ_e σ_e^p)^(1/p)`` (the smax-normalised
    :func:`p_norm_stress` equals this exactly). Each ``σ_e`` is the plane-stress
    von Mises stress of ``fem2d._approx_element_stress``, which is the norm of a
    quantity *linear in the element displacement*: ``σ_e² = (S uₑ)ᵀ V (S uₑ)``
    with ``S = D B`` constant per element. The raw material stress carries **no
    explicit ρ dependence**, so ``σ_PN`` depends on the design only through the
    state ``u(ρ)`` and the sensitivity is the pure adjoint term

        ``dσ_PN/dρ_e = − dscale_e · (λₑᵀ kₑ uₑ)``,  ``K λ = ∂σ_PN/∂u``,

    where ``dscale_e = ∂/∂ρ_e [ρ_min + ρ_e^pen (1−ρ_min)]`` is the SIMP scaling
    derivative (0 on void cells). Validated against central finite differences to
    relative error ≤ 1e-6 on the highest-sensitivity elements.

    Args:
        mask: optional boolean element mask restricting which elements enter the
            aggregation (e.g. design cells only); ``None`` = all elements.

    Returns:
        ``(sigma_pn, dsigma_pn_drho)`` with ``dsigma_pn_drho`` length n_elem.
    """
    if p <= 0:
        raise ValueError("p must be positive")
    from structure_optimizer.adapters.solver_base import get_linear_solver
    from structure_optimizer.core.fem2d import (
        _assemble_stiffness_dense,
        _assemble_stiffness_sparse,
        element_stiffness,
        solve_linear_elastic,
    )

    opt = config.optimization
    densities = np.asarray(densities, dtype=float).reshape(-1)
    n_elem = mesh.elements.shape[0]
    res = solve_linear_elastic(config, mesh, densities)
    u = res.displacements
    stresses = element_von_mises_stresses(config, mesh, u)
    sigma_pn = p_norm_stress(stresses, p, mask)
    dsdrho = np.zeros(n_elem, dtype=float)
    if sigma_pn == 0.0:
        return sigma_pn, dsdrho

    s_mat = _element_stress_matrix(config, mesh)
    use = np.ones(n_elem, dtype=bool) if mask is None else np.asarray(mask, dtype=bool)

    # ∂σ_PN/∂u assembled element-by-element: ∂σ_PN/∂σ_e = (σ_e/σ_PN)^(p-1),
    # ∂σ_e/∂uₑ = (V s)ᵀ S / σ_e.
    dpn_du = np.zeros(mesh.ndof, dtype=float)
    for eid in range(n_elem):
        if not use[eid] or stresses[eid] <= 0.0:
            continue
        edofs = mesh.element_dofs(eid)
        s = s_mat @ u[edofs]
        dpn_dse = (stresses[eid] / sigma_pn) ** (p - 1.0)
        dse_due = ((_VON_MISES_FORM @ s) / stresses[eid]) @ s_mat
        dpn_du[edofs] += dpn_dse * dse_due

    # adjoint solve K λ = ∂σ_PN/∂u (K symmetric); fixed dofs carry λ = 0.
    ke = element_stiffness(config.material.young_modulus, config.material.poisson_ratio)
    active = np.where(mesh.void_mask, opt.min_density, densities)
    density_scale = opt.min_density + (active**opt.penalty) * (1.0 - opt.min_density)
    solver = get_linear_solver(config.solver.backend)
    if solver.prefers_sparse:
        stiffness = _assemble_stiffness_sparse(mesh, density_scale, ke)
    else:
        stiffness = _assemble_stiffness_dense(mesh, density_scale, ke)
    fixed = mesh.fixed_dofs(config.boundary_conditions)
    free = np.setdiff1d(np.arange(mesh.ndof), fixed)
    kff = stiffness.tocsr()[free, :][:, free] if solver.prefers_sparse else stiffness[np.ix_(free, free)]
    lam = np.zeros(mesh.ndof, dtype=float)
    lam[free] = solver.solve(kff, dpn_du[free])

    dscale = opt.penalty * np.where(mesh.void_mask, 0.0, active ** (opt.penalty - 1.0)) * (1.0 - opt.min_density)
    for eid in range(n_elem):
        edofs = mesh.element_dofs(eid)
        ue = u[edofs]
        le = lam[edofs]
        dsdrho[eid] = -dscale[eid] * float(le @ (ke @ ue))
    return sigma_pn, dsdrho


def qp_relaxed_stress_pnorm_sensitivity(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    p: float = 8.0,
    q: float = 2.5,
    mask: np.ndarray | None = None,
) -> tuple[float, np.ndarray]:
    """qp-**relaxed** p-norm von Mises stress + density sensitivity (Wave SSS, D074).

    The raw stress measure of :func:`stress_pnorm_sensitivity` (D066) suffers the
    classical **stress-singularity** phenomenon: a vanishing-density element keeps
    a finite (often *large*) raw von Mises stress, so the feasible set has thin
    degenerate spikes that gradient optimisers cannot enter — the stress-limited
    optimum is singular. The qp-relaxation multiplies each element stress by
    ``ρ_e^q`` (``q`` typically < the stiffness penalty ``p_simp``) so the relaxed
    stress of a void element vanishes, removing the singularity:

        ``σ̃_e = ρ_e^q · σ_vm,e(u)``,  ``σ̃_PN = (Σ_e σ̃_e^p)^(1/p)``.

    Unlike the raw measure, ``σ̃_e`` has an **explicit** ρ dependence, so the
    sensitivity carries two terms — an explicit ``∂(ρ_e^q)`` part plus the implicit
    adjoint part through ``u(ρ)``:

        ``dσ̃_PN/dρ_j = w_j · q ρ_j^(q−1) σ_j``  (explicit)
        ``           − dscale_j · (λ_jᵀ k_j u_j)``  (implicit, ``K λ = ∂σ̃_PN/∂u``)

    with ``w_e = (σ̃_e/σ̃_PN)^(p−1)`` and ``∂σ̃_PN/∂u = Σ_e w_e ρ_e^q (∂σ_e/∂u)``.
    Validated against central FD to relative error ≤ 1e-4 on the
    highest-sensitivity elements (explicit + implicit together).

    Returns ``(sigma_pn_relaxed, dsigma_pn_drho)``.
    """
    if p <= 0:
        raise ValueError("p must be positive")
    if q <= 0:
        raise ValueError("q must be positive")
    from structure_optimizer.adapters.solver_base import get_linear_solver
    from structure_optimizer.core.fem2d import (
        _assemble_stiffness_dense,
        _assemble_stiffness_sparse,
        element_stiffness,
        solve_linear_elastic,
    )

    opt = config.optimization
    densities = np.asarray(densities, dtype=float).reshape(-1)
    n_elem = mesh.elements.shape[0]
    res = solve_linear_elastic(config, mesh, densities)
    u = res.displacements
    raw = element_von_mises_stresses(config, mesh, u)
    rho_q = np.power(np.clip(densities, 0.0, None), q)
    relaxed = rho_q * raw
    sigma_pn = p_norm_stress(relaxed, p, mask)
    dsdrho = np.zeros(n_elem, dtype=float)
    if sigma_pn == 0.0:
        return sigma_pn, dsdrho

    s_mat = _element_stress_matrix(config, mesh)
    use = np.ones(n_elem, dtype=bool) if mask is None else np.asarray(mask, dtype=bool)
    w = np.where(use & (relaxed > 0.0), (relaxed / sigma_pn) ** (p - 1.0), 0.0)

    # explicit term: ∂σ̃_e/∂ρ_e via ρ^q (only the diagonal element contributes)
    dexplicit = w * q * np.power(np.clip(densities, 1e-300, None), q - 1.0) * raw

    # implicit term: adjoint with the ρ^q-weighted ∂σ̃_PN/∂u
    dpn_du = np.zeros(mesh.ndof, dtype=float)
    for eid in range(n_elem):
        if w[eid] == 0.0 or raw[eid] <= 0.0:
            continue
        edofs = mesh.element_dofs(eid)
        s = s_mat @ u[edofs]
        dse_due = ((_VON_MISES_FORM @ s) / raw[eid]) @ s_mat
        dpn_du[edofs] += w[eid] * rho_q[eid] * dse_due

    ke = element_stiffness(config.material.young_modulus, config.material.poisson_ratio)
    active = np.where(mesh.void_mask, opt.min_density, densities)
    density_scale = opt.min_density + (active**opt.penalty) * (1.0 - opt.min_density)
    solver = get_linear_solver(config.solver.backend)
    stiffness = _assemble_stiffness_sparse(mesh, density_scale, ke) if solver.prefers_sparse else _assemble_stiffness_dense(mesh, density_scale, ke)
    fixed = mesh.fixed_dofs(config.boundary_conditions)
    free = np.setdiff1d(np.arange(mesh.ndof), fixed)
    kff = stiffness.tocsr()[free, :][:, free] if solver.prefers_sparse else stiffness[np.ix_(free, free)]
    lam = np.zeros(mesh.ndof, dtype=float)
    lam[free] = solver.solve(kff, dpn_du[free])

    dscale = opt.penalty * np.where(mesh.void_mask, 0.0, active ** (opt.penalty - 1.0)) * (1.0 - opt.min_density)
    dimplicit = np.zeros(n_elem, dtype=float)
    for eid in range(n_elem):
        edofs = mesh.element_dofs(eid)
        dimplicit[eid] = -dscale[eid] * float(lam[edofs] @ (ke @ u[edofs]))
    return sigma_pn, dexplicit + dimplicit
