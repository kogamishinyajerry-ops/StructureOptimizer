"""Wave U: linearized-buckling eigenvalue analysis for SIMP designs.

Classical linear-buckling eigenvalue problem on a SIMP-designed
structure::

    (K(ρ) + λ K_g(ρ, u)) φ = 0

where:
    - K(ρ) is the SIMP-penalized stiffness (assembled by the existing
      ``core/fem2d`` machinery).
    - K_g(ρ, u) is the geometric (stress) stiffness assembled from the
      static-equilibrium displacement field ``u = K^{-1} f``.
    - (λ, φ) is the buckling eigenpair. ``λ_crit = min |λ| > 0`` is the
      buckling load factor: the load multiplier at which a non-trivial
      lateral mode appears.

Engineering use: when adding buckling as a constraint to SIMP, we want
``λ_crit ≥ 1`` (or, more commonly, ``λ_crit ≥ λ_safety``). This module
computes ``λ_crit`` and its sensitivity ``∂λ/∂ρ_e`` so SIMP/MMA can
push designs toward higher buckling margin.

Numerics:
    - Inverse iteration on the smallest-magnitude eigenpair via NumPy.
      scipy is *not* required (we factor K once and iterate). For very
      large systems this is slower than ARPACK shift-invert; for v4
      mesh sizes (up to ~10⁵ DOF) it is adequate. A scipy backend can
      be wired later.
    - Geometric stiffness uses plane-stress CST/QUAD assumption: the
      6×6 (tri) or 8×8 (quad) ``Kg`` is the standard linearization
      ``∫ B_NL^T σ B_NL dV`` evaluated at the element centroid.

This module is **quad-only** in Wave U (matches existing FEM scope);
triangle buckling is deferred.

Reference:
    Bathe (1996), *Finite Element Procedures*, §6.6 — linearized
    buckling. Bendsøe & Sigmund (2003), §1.3.4 — buckling constraints
    in topology optimization.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.fem2d import _assemble_stiffness_dense, element_stiffness
from structure_optimizer.core.mesh import StructuredMesh


def _element_geometric_stiffness_quad(
    mesh: StructuredMesh,
    young_modulus: float,
    poisson_ratio: float,
    ue: np.ndarray,
) -> np.ndarray:
    """Geometric stiffness K_g^e (8×8) for one quad at the displacement state.

    Uses a single Gauss-point evaluation at the element centroid. The
    stress at the centroid is computed from the displacement field; then
    K_g^e = ∫ G^T σ̄ G dV where G is the spatial gradient of shape functions
    and σ̄ is the (2D) stress-block matrix.

    For plane stress on a unit quad:
        σ̄ = [[σ_xx, σ_xy], [σ_xy, σ_yy]]
    expanded to a (4×4) block-diagonal form ``Σ`` for the 4 corners.
    """
    hx = mesh.width / mesh.nelx
    hy = mesh.height / mesh.nely
    # ∂N/∂x and ∂N/∂y at centroid for 4-node quad
    # Shape function gradients for unit-scaled quad: ±1/(2hx), ±1/(2hy)
    a = 1.0 / (2.0 * hx)
    b = 1.0 / (2.0 * hy)
    dn_dx = np.array([-a, a, a, -a])
    dn_dy = np.array([-b, -b, b, b])

    # Strain at centroid from element nodal displacements
    # u = [ux1, uy1, ux2, uy2, ux3, uy3, ux4, uy4]
    ux = ue[0::2]
    uy = ue[1::2]
    eps_x = float(dn_dx @ ux)
    eps_y = float(dn_dy @ uy)
    gamma_xy = float(dn_dy @ ux + dn_dx @ uy)

    # Constitutive law (plane stress)
    nu = poisson_ratio
    factor = young_modulus / (1.0 - nu**2)
    sigma_x = factor * (eps_x + nu * eps_y)
    sigma_y = factor * (nu * eps_x + eps_y)
    sigma_xy = factor * 0.5 * (1.0 - nu) * gamma_xy

    # G matrix (4×8): G[2i:2i+2, 2j:2j+2] = diag(dN_j/dx, dN_j/dy) for node j at row 2i
    # Standard form: G is (4×8) where rows = [dNx, dNy, dNx, dNy] per node block
    # K_g^e = thickness * area * G^T * Σ * G  where Σ is (4×4) block-diagonal
    # of [[σ_x, σ_xy], [σ_xy, σ_y]]
    G = np.zeros((4, 8))
    for j in range(4):
        G[0, 2 * j] = dn_dx[j]
        G[1, 2 * j] = dn_dy[j]
        G[2, 2 * j + 1] = dn_dx[j]
        G[3, 2 * j + 1] = dn_dy[j]
    Sigma = np.array(
        [
            [sigma_x, sigma_xy, 0.0, 0.0],
            [sigma_xy, sigma_y, 0.0, 0.0],
            [0.0, 0.0, sigma_x, sigma_xy],
            [0.0, 0.0, sigma_xy, sigma_y],
        ]
    )
    area = hx * hy
    return float(area) * (G.T @ Sigma @ G)


def assemble_geometric_stiffness(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    displacements: np.ndarray,
    g_penalty: float | None = None,
) -> np.ndarray:
    """Assemble the global geometric stiffness K_g (dense, ndof×ndof).

    SIMP-penalized: each element's K_g^e is multiplied by ``ρ_e^{g_penalty}``.
    ``g_penalty`` defaults to ``opt.penalty`` (the original behaviour, same as K);
    raising it is the **void-mode relaxation** knob (Wave AAAA, D082) — a steeper
    geometric-stiffness interpolation drives low-density elements' K_g toward zero
    faster, suppressing the spurious localized buckling modes they otherwise host.
    """
    opt = config.optimization
    gp = opt.penalty if g_penalty is None else float(g_penalty)
    ndof = mesh.ndof
    Kg = np.zeros((ndof, ndof))
    for eid in range(mesh.elements.shape[0]):
        edofs = mesh.element_dofs(eid)
        ue = displacements[edofs]
        kge = _element_geometric_stiffness_quad(mesh, config.material.young_modulus, config.material.poisson_ratio, ue)
        scale = max(densities[eid], opt.min_density) ** gp
        Kg[np.ix_(edofs, edofs)] += scale * kge
    return Kg


def buckling_load_factor(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    displacements: np.ndarray,
    n_modes: int = 1,
    max_iter: int = 100,
    tol: float = 1e-6,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute the smallest ``n_modes`` buckling eigenpairs.

    Solves the generalized eigenproblem ``K φ = λ (-K_g) φ`` for the
    *positive* λ closest to zero (the critical load factor). This is the
    sign convention where K_g is sign-flipped so the "buckling load" is
    the smallest positive eigenvalue.

    Returns:
        ``(lambdas, phis)`` — eigenvalues (length ``n_modes``) and
        eigenvectors (``ndof × n_modes``, both restricted to free DOFs
        then zero-padded).
    """
    opt = config.optimization
    ke = element_stiffness(config.material.young_modulus, config.material.poisson_ratio)
    active_density = np.where(mesh.void_mask, opt.min_density, densities)
    density_scale = opt.min_density + (active_density**opt.penalty) * (1.0 - opt.min_density)
    K = _assemble_stiffness_dense(mesh, density_scale, ke)
    Kg = assemble_geometric_stiffness(config, mesh, densities, displacements)

    fixed = mesh.fixed_dofs(config.boundary_conditions)
    free = np.setdiff1d(np.arange(mesh.ndof), fixed)
    Kff = K[np.ix_(free, free)]
    Kgff = Kg[np.ix_(free, free)]

    # Generalized eigenproblem: Kff φ = λ (-Kgff) φ
    # Reformulate as K_inv * (-Kg) * φ = (1/λ) φ → power iteration on 1/λ
    # i.e. inverse iteration on the smallest |λ|: use numpy.linalg.eig on
    # the dense generalized problem (size = free DOFs, may be large but
    # this is the v4 baseline; scipy.linalg.eigh + ARPACK would be the
    # production upgrade).
    try:
        # eigh requires symmetric — K and Kg are symmetric by construction
        lam, phi = np.linalg.eig(np.linalg.solve(Kff, -Kgff))
    except np.linalg.LinAlgError as e:
        raise RuntimeError(f"buckling eigensolve failed: {e}") from e
    # Each eigenvalue η = 1/λ → λ = 1/η. Pick smallest |λ| > 0.
    # Equivalent: largest |η|. Filter to positive λ (physical buckling).
    real_lam = np.real(lam)
    # 1/η → only real, positive
    candidates = []
    for i, eta in enumerate(real_lam):
        if abs(eta) < 1e-30:
            continue
        L = 1.0 / eta
        if L > 0.0:
            candidates.append((L, i))
    if not candidates:
        # No positive buckling mode (design is unconditionally stable under
        # the applied load) — return a large sentinel.
        large = 1e30
        eigvecs = np.zeros((mesh.ndof, n_modes))
        return np.full(n_modes, large), eigvecs
    candidates.sort(key=lambda t: t[0])
    selected = candidates[: max(1, n_modes)]
    lambdas = np.array([s[0] for s in selected])
    phi_full = np.zeros((mesh.ndof, len(selected)))
    for k, (_, idx) in enumerate(selected):
        v = np.real(phi[:, idx])
        phi_full[free, k] = v / max(np.linalg.norm(v), 1e-30)
    return lambdas, phi_full


def buckling_sensitivity(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    displacements: np.ndarray,
    eigenvalue: float,
    eigenvector: np.ndarray,
) -> np.ndarray:
    """Approximate ``∂λ/∂ρ_e`` for one buckling eigenpair.

    Uses the **adjoint-free** formula valid for symmetric K, K_g (Lund
    1994; Bendsøe & Sigmund 2003 eq. 1.42):

        ∂λ/∂ρ_e ≈ φ^T (∂K/∂ρ_e + λ ∂K_g/∂ρ_e) φ / (φ^T (-K_g) φ)

    For SIMP-penalized assembly:
        ∂K/∂ρ_e = p ρ_e^(p-1) K_e^0
        ∂K_g/∂ρ_e = p ρ_e^(p-1) K_g^e (the geometric part with the
        same penalty exponent and the *same* u — this is the standard
        approximation that ignores the indirect ∂u/∂ρ contribution to
        K_g, which is a separate (and expensive) adjoint solve).

    This approximation is what most production topology codes use for
    buckling sensitivities; the truncation is small in practice unless
    the design is very close to a bifurcation.
    """
    opt = config.optimization
    ke = element_stiffness(config.material.young_modulus, config.material.poisson_ratio)
    n_elem = mesh.elements.shape[0]

    # Denominator: φ^T (-K_g) φ
    Kg = assemble_geometric_stiffness(config, mesh, densities, displacements)
    denom = float(eigenvector @ (-Kg @ eigenvector))
    if abs(denom) < 1e-30:
        return np.zeros(n_elem)

    sens = np.zeros(n_elem)
    p = opt.penalty
    for eid in range(n_elem):
        edofs = mesh.element_dofs(eid)
        phi_e = eigenvector[edofs]
        rho = max(densities[eid], opt.min_density)
        # ∂K^e/∂ρ contribution
        dKe_drho = p * (rho ** (p - 1.0)) * ke
        ue = displacements[edofs]
        dKge_drho = (
            p
            * (rho ** (p - 1.0))
            * _element_geometric_stiffness_quad(mesh, config.material.young_modulus, config.material.poisson_ratio, ue)
        )
        numer = float(phi_e @ (dKe_drho + eigenvalue * dKge_drho) @ phi_e)
        sens[eid] = numer / denom
    return sens


def design_grade_buckling_sensitivity(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    displacements: np.ndarray,
    eigenvalue: float,
    eigenvector: np.ndarray,
    g_penalty: float | None = None,
) -> np.ndarray:
    """**Design-grade** ``∂λ/∂ρ_e`` for one buckling eigenpair — the full adjoint
    sensitivity that :func:`buckling_sensitivity` truncates (Wave AAAA, D082).

    The analysis-grade formula ignores the indirect ``∂u/∂ρ`` contribution to the
    geometric stiffness ``K_g = K_g(σ(u(ρ)))``. That truncation is **not** small
    for design: a fixed-volume λ_crit *ascent* driven by the truncated gradient
    *lowers* λ_crit (probe: 20.1 → 8.1), because the gradient points the wrong way.
    Including the adjoint term reverses this (ascent 20.1 → 34.8).

    With ``φ`` re-normalised so ``φᵀ(−K_g)φ = 1`` and ``K φ = λ(−K_g)φ``,

        dλ/dρ_e = dscale_e·φₑᵀkₑφₑ  +  λ·g_dscale_e·φₑᵀkgeₑ(uₑ)φₑ
                  − λ·dscale_e·μₑᵀkₑuₑ,            K μ = w,
        w = ∂(φᵀK_gφ)/∂u   (assembled element-wise; K_g is linear in u),

    where ``dscale_e`` is the SIMP derivative of the elastic K (matching
    :func:`core.fem2d.solve_linear_elastic`) and ``g_dscale_e`` the derivative of
    the K_g interpolation (``g_penalty``, default ``opt.penalty`` — the value the
    eigenpair was computed with). Validated against central FD to ≤ 1e-3.
    """
    opt = config.optimization
    gp = opt.penalty if g_penalty is None else float(g_penalty)
    young, nu = config.material.young_modulus, config.material.poisson_ratio
    ke = element_stiffness(young, nu)
    n_elem = mesh.elements.shape[0]
    rho = np.asarray(densities, dtype=float).reshape(-1)

    # Re-normalise φ so φᵀ(−K_g)φ = 1 (the sensitivity formula assumes this).
    kg = assemble_geometric_stiffness(config, mesh, rho, displacements, g_penalty=gp)
    denom = float(eigenvector @ (-kg @ eigenvector))
    if abs(denom) < 1e-30:
        return np.zeros(n_elem)
    phi = eigenvector / np.sqrt(abs(denom))

    # SIMP-scaled elastic K (matches solve_linear_elastic) for the adjoint solve.
    active = np.where(mesh.void_mask, opt.min_density, rho)
    k_scale = opt.min_density + (active**opt.penalty) * (1.0 - opt.min_density)
    big_k = _assemble_stiffness_dense(mesh, k_scale, ke)
    fixed = mesh.fixed_dofs(config.boundary_conditions)
    free = np.setdiff1d(np.arange(mesh.ndof), fixed)

    # w = ∂(φᵀ K_g φ)/∂u : K_g^e is linear in u_e, so the per-dof derivative is
    # φₑᵀ K_g^e(unit_k) φₑ (the geometric stiffness evaluated at a unit displacement).
    kg_units = [
        _element_geometric_stiffness_quad(mesh, young, nu, np.eye(8)[k]) for k in range(8)
    ]
    w = np.zeros(mesh.ndof)
    for eid in range(n_elem):
        edofs = mesh.element_dofs(eid)
        phe = phi[edofs]
        sc = max(rho[eid], opt.min_density) ** gp
        w[edofs] += np.array([sc * float(phe @ (kg_units[k] @ phe)) for k in range(8)])

    mu = np.zeros(mesh.ndof)
    mu[free] = np.linalg.solve(big_k[np.ix_(free, free)], w[free])

    dscale = opt.penalty * np.where(mesh.void_mask, 0.0, active ** (opt.penalty - 1.0)) * (1.0 - opt.min_density)
    sens = np.zeros(n_elem)
    for eid in range(n_elem):
        edofs = mesh.element_dofs(eid)
        phe = phi[edofs]
        ue = displacements[edofs]
        mue = mu[edofs]
        kge = _element_geometric_stiffness_quad(mesh, young, nu, ue)
        g_dscale = gp * max(rho[eid], opt.min_density) ** (gp - 1.0)
        sens[eid] = (
            dscale[eid] * float(phe @ (ke @ phe))
            + eigenvalue * g_dscale * float(phe @ (kge @ phe))
            - eigenvalue * dscale[eid] * float(mue @ (ke @ ue))
        )
    return sens


@dataclass
class BucklingTOResult:
    """Output of fixed-volume buckling-load maximisation (Wave AAAA, D082)."""

    densities: np.ndarray
    lambda_history: list[float]
    volume_history: list[float]
    converged: bool


def maximize_buckling_load(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    vf: float | None = None,
    n_steps: int = 30,
    move: float = 0.1,
    filter_radius: float | None = None,
    init_densities: np.ndarray | None = None,
) -> BucklingTOResult:
    """Maximise the critical buckling load factor ``λ_crit`` at fixed volume, via
    move-limited MMA on the **design-grade** sensitivity (Wave AAAA, D082).

    Minimises ``−λ_crit`` subject to ``g = mean(ρ) − vf ≤ 0`` using
    :func:`design_grade_buckling_sensitivity` (density-filtered). With the correct
    adjoint gradient the ascent genuinely *raises* λ_crit (the analysis-grade
    gradient does not — see D074/D082). Starts from the volume-fraction design (or
    ``init_densities``). Stops on ``n_steps``.
    """
    from structure_optimizer.core.fem2d import solve_linear_elastic
    from structure_optimizer.core.filtering import density_filter
    from structure_optimizer.core.mma import MMAState, mma_step

    opt = config.optimization
    radius = opt.filter_radius if filter_radius is None else filter_radius
    design = mesh.design_mask
    n_design = max(1, int(np.count_nonzero(design)))
    vf_target = float(opt.volume_fraction) if vf is None else float(vf)

    if init_densities is None:
        rho = np.where(mesh.void_mask, opt.min_density, vf_target)
    else:
        rho = np.asarray(init_densities, dtype=float).reshape(-1).copy()

    x = rho[design].astype(float).copy()
    xmin = np.full(n_design, opt.min_density)
    xmax = np.ones(n_design)
    dfdx = np.zeros((1, n_design))
    dfdx[0, :] = 1.0 / n_design
    state = MMAState()

    lambda_history: list[float] = []
    volume_history: list[float] = []
    converged = False
    for _ in range(n_steps):
        rho[design] = x
        u = solve_linear_elastic(config, mesh, rho).displacements
        lambdas, phis = buckling_load_factor(config, mesh, rho, u, n_modes=1)
        lam = float(lambdas[0])
        dl = design_grade_buckling_sensitivity(config, mesh, rho, u, lam, phis[:, 0])
        dl = density_filter(mesh, rho, dl, radius, opt.min_density)

        lambda_history.append(lam)
        volume_history.append(float(np.mean(x)))

        df0dx = -dl[design]  # minimise −λ ⇒ maximise λ
        fval = np.array([float(np.mean(x) - vf_target)])
        x_new, _lmbda = mma_step(x, df0dx, fval, dfdx, xmin, xmax, state)
        change = float(np.max(np.abs(x_new - x)))
        x = x_new
        if change < 1e-4:
            converged = True
            break

    rho[design] = x
    u = solve_linear_elastic(config, mesh, rho).displacements
    lam_final = float(buckling_load_factor(config, mesh, rho, u, n_modes=1)[0][0])
    lambda_history.append(lam_final)
    volume_history.append(float(np.mean(x)))
    return BucklingTOResult(
        densities=rho,
        lambda_history=lambda_history,
        volume_history=volume_history,
        converged=converged,
    )
