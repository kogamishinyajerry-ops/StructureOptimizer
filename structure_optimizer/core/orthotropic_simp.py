"""Elastic orthotropic topology optimisation: simultaneous (ρ, θ) MMA with a
fibre-continuity constraint (Wave XXX, v11, D079).

D070 delivered simultaneous (ρ, θ) MMA for **thermal** conductivity. Its reopening
criterion named the **elastic** analogue — an orthotropic lamina stiffness rotated
by a per-element fibre angle — plus a **fibre-continuity** constraint (the thermal
version let θ vary freely between neighbours). This module is that elastic path,
built on a Q4 Gauss-integrated element stiffness (validated to reproduce the
isotropic closed-form ``fem2d.element_stiffness``) and a 4th-order-tensor rotation
of the plane-stress stiffness (so the engineering-shear bookkeeping is exact).

numpy-only; dense assembly (smoke meshes); ``SolverError`` status strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations

import numpy as np

from structure_optimizer.core.config import BenchmarkConfig
from structure_optimizer.core.fem2d import SolverError
from structure_optimizer.core.mesh import StructuredMesh

# 2×2 Gauss-Legendre on the unit square [0,1]² (weights 0.5 each in 1-D).
_GP = (0.5 - 1.0 / (2.0 * np.sqrt(3.0)), 0.5 + 1.0 / (2.0 * np.sqrt(3.0)))
_GW = 0.5

# Voigt (engineering-shear) ↔ 4th-order tensor index map.
_VOIGT_PAIRS = ((0, 0), (1, 1), (0, 1))
_TENSOR_IDX = {(0, 0): 0, (1, 1): 1, (0, 1): 2, (1, 0): 2}


def orthotropic_plane_stress_matrix(e1: float, e2: float, nu12: float, g12: float) -> np.ndarray:
    """Orthotropic plane-stress stiffness ``D₀`` (3×3, material axes, Voigt with
    engineering shear)."""
    if e1 <= 0 or e2 <= 0 or g12 <= 0:
        raise SolverError("orthotropic_nonpositive_modulus")
    nu21 = nu12 * e2 / e1
    denom = 1.0 - nu12 * nu21
    if denom <= 0:
        raise SolverError("orthotropic_invalid_poisson")
    return np.array(
        [[e1 / denom, nu12 * e2 / denom, 0.0], [nu12 * e2 / denom, e2 / denom, 0.0], [0.0, 0.0, g12]]
    )


def _voigt_to_tensor(d: np.ndarray) -> np.ndarray:
    c = np.zeros((2, 2, 2, 2))
    for i in range(2):
        for j in range(2):
            for k in range(2):
                for ll in range(2):
                    c[i, j, k, ll] = d[_TENSOR_IDX[(i, j)], _TENSOR_IDX[(k, ll)]]
    return c


def _tensor_to_voigt(c: np.ndarray) -> np.ndarray:
    d = np.zeros((3, 3))
    for a, (i, j) in enumerate(_VOIGT_PAIRS):
        for b, (k, ll) in enumerate(_VOIGT_PAIRS):
            d[a, b] = c[i, j, k, ll]
    return d


def rotate_plane_stress(d0: np.ndarray, theta: float) -> np.ndarray:
    """Rotate the plane-stress stiffness ``D₀`` to global axes by fibre angle
    ``theta`` via the 4th-order tensor rotation ``C'=QQQQ:C`` (exact engineering-
    shear handling)."""
    q = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    c = _voigt_to_tensor(d0)
    cr = np.einsum("ia,jb,kc,ld,abcd->ijkl", q, q, q, q, c)
    return _tensor_to_voigt(cr)


def drotate_plane_stress_dtheta(d0: np.ndarray, theta: float) -> np.ndarray:
    """Analytic derivative ``dD(θ)/dθ`` of :func:`rotate_plane_stress` (product rule
    over the four rotation factors)."""
    q = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    dq = np.array([[-np.sin(theta), -np.cos(theta)], [np.cos(theta), -np.sin(theta)]])
    c = _voigt_to_tensor(d0)
    dc = (
        np.einsum("ia,jb,kc,ld,abcd->ijkl", dq, q, q, q, c)
        + np.einsum("ia,jb,kc,ld,abcd->ijkl", q, dq, q, q, c)
        + np.einsum("ia,jb,kc,ld,abcd->ijkl", q, q, dq, q, c)
        + np.einsum("ia,jb,kc,ld,abcd->ijkl", q, q, q, dq, c)
    )
    return _tensor_to_voigt(dc)


def _q4_b(xi: float, eta: float) -> np.ndarray:
    """Q4 strain-displacement matrix (3×8) on the unit square, node order
    (0,0),(1,0),(1,1),(0,1), DOFs (ux,uy) — matching ``mesh`` connectivity."""
    dnx = np.array([-(1.0 - eta), (1.0 - eta), eta, -eta])
    dny = np.array([-(1.0 - xi), -xi, xi, (1.0 - xi)])
    b = np.zeros((3, 8))
    for a in range(4):
        b[0, 2 * a] = dnx[a]
        b[1, 2 * a + 1] = dny[a]
        b[2, 2 * a] = dny[a]
        b[2, 2 * a + 1] = dnx[a]
    return b


_B_GP = [(_q4_b(xi, eta)) for xi in _GP for eta in _GP]


def orthotropic_element_stiffness(d: np.ndarray) -> np.ndarray:
    """8×8 Q4 element stiffness ``∫ Bᵀ D B`` (2×2 Gauss, unit square). With an
    isotropic ``D`` this reproduces ``fem2d.element_stiffness`` to machine
    precision (validated by test)."""
    ke = np.zeros((8, 8))
    for b in _B_GP:
        ke += (_GW * _GW) * (b.T @ d @ b)
    return ke


@dataclass
class OrthotropicTOResult:
    """Output of simultaneous (ρ,θ) elastic orthotropic MMA (Wave XXX, D079)."""

    densities: np.ndarray
    angles: np.ndarray
    compliance_history: list[float]
    volume_history: list[float]
    continuity_history: list[float]
    continuity_limit: float | None
    converged: bool


def _design_adjacency_pairs(mesh: StructuredMesh) -> list[tuple[int, int]]:
    """Orthogonally-adjacent design-cell element-id pairs (for fibre continuity)."""
    design = mesh.design_mask
    pairs: list[tuple[int, int]] = []
    for ey in range(mesh.nely):
        for ex in range(mesh.nelx):
            e = ey * mesh.nelx + ex
            if not design[e]:
                continue
            if ex + 1 < mesh.nelx:
                f = ey * mesh.nelx + (ex + 1)
                if design[f]:
                    pairs.append((e, f))
            if ey + 1 < mesh.nely:
                f = (ey + 1) * mesh.nelx + ex
                if design[f]:
                    pairs.append((e, f))
    return pairs


def _assemble_orthotropic(mesh: StructuredMesh, scale: np.ndarray, ke_cache: list[np.ndarray]) -> np.ndarray:
    k = np.zeros((mesh.ndof, mesh.ndof))
    for e in range(mesh.elements.shape[0]):
        edofs = mesh.element_dofs(e)
        k[np.ix_(edofs, edofs)] += scale[e] * ke_cache[e]
    return k


def _solve(config: BenchmarkConfig, mesh: StructuredMesh, scale: np.ndarray, ke_cache: list[np.ndarray]):
    k = _assemble_orthotropic(mesh, scale, ke_cache)
    f = mesh.force_vector(config.loads)
    fixed = mesh.fixed_dofs(config.boundary_conditions)
    free = np.setdiff1d(np.arange(mesh.ndof), fixed)
    if free.size == 0:
        raise SolverError("orthotropic_all_dofs_fixed")
    u = np.zeros(mesh.ndof)
    try:
        u[free] = np.linalg.solve(k[np.ix_(free, free)], f[free])
    except np.linalg.LinAlgError as exc:
        raise SolverError("orthotropic_singular_stiffness") from exc
    return u, float(f @ u)


def orthotropic_compliance_sensitivities(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    densities: np.ndarray,
    angles: np.ndarray,
    d0: np.ndarray,
) -> tuple[float, np.ndarray, np.ndarray]:
    """Compliance and its **self-adjoint** sensitivities ``dC/dρ`` and ``dC/dθ`` for
    the orthotropic SIMP body (Wave XXX, D079).

    ``K = Σ_e scale_e·ke(θ_e)`` with ``scale_e = ρ_min + ρ_e^p(1−ρ_min)``; for
    minimum compliance ``C = fᵀu``,

        dC/dρ_e = −dscale_e · uₑᵀ ke(θ_e) uₑ,
        dC/dθ_e = −scale_e  · uₑᵀ (dke/dθ)(θ_e) uₑ,

    where ``dke/dθ = ∫ Bᵀ (dD/dθ) B`` reuses the analytic
    :func:`drotate_plane_stress_dtheta`. Both validated against central FD.
    """
    opt = config.optimization
    rho = np.asarray(densities, dtype=float).reshape(-1)
    ang = np.asarray(angles, dtype=float).reshape(-1)
    n_elem = mesh.elements.shape[0]
    active = np.where(mesh.void_mask, opt.min_density, rho)
    scale = opt.min_density + (active**opt.penalty) * (1.0 - opt.min_density)
    dscale = opt.penalty * np.where(mesh.void_mask, 0.0, active ** (opt.penalty - 1.0)) * (1.0 - opt.min_density)

    ke_cache = [orthotropic_element_stiffness(rotate_plane_stress(d0, ang[e])) for e in range(n_elem)]
    u, compliance = _solve(config, mesh, scale, ke_cache)

    d_rho = np.zeros(n_elem)
    d_theta = np.zeros(n_elem)
    for e in range(n_elem):
        ue = u[mesh.element_dofs(e)]
        d_rho[e] = -dscale[e] * float(ue @ (ke_cache[e] @ ue))
        if not mesh.void_mask[e]:
            dke = orthotropic_element_stiffness(drotate_plane_stress_dtheta(d0, ang[e]))
            d_theta[e] = -scale[e] * float(ue @ (dke @ ue))
    return compliance, d_rho, d_theta


def _continuity_metric(angles: np.ndarray, pairs: list[tuple[int, int]]) -> tuple[float, dict[int, float]]:
    """Mean adjacent squared angle difference + per-element gradient contributions."""
    if not pairs:
        return 0.0, {}
    grad: dict[int, float] = {}
    total = 0.0
    for e, f in pairs:
        diff = angles[e] - angles[f]
        total += diff * diff
        grad[e] = grad.get(e, 0.0) + 2.0 * diff
        grad[f] = grad.get(f, 0.0) - 2.0 * diff
    n = len(pairs)
    return total / n, {k: v / n for k, v in grad.items()}


def period_aware_continuity(
    angles: np.ndarray, pairs: list[tuple[int, int]]
) -> tuple[float, dict[int, float]]:
    """**Period-aware** fibre-continuity metric ``mean_{(e,f)} sin²(θ_e − θ_f)`` +
    per-element gradient (Wave FFFF, D087).

    D079's :func:`_continuity_metric` penalised ``(θ_e − θ_f)²`` — but a fibre angle
    is **π-periodic** (θ and θ+π describe the *same* fibre orientation). The squared
    difference therefore wrongly punishes a +89°/−89° seam as a 178° jump, even
    though those plies are only 2° apart in orientation. ``sin²(Δθ)`` has period π
    and vanishes at Δθ = 0 *and* π, so it measures true orientation mismatch:
    ``sin²(θ_e+π − θ_f) = sin²(θ_e − θ_f)``. For small Δθ, ``sin²(Δ) ≈ Δ²`` so it
    degenerates to D079's metric. Gradient: ``∂/∂θ_e mean sin²(θ_e−θ_f) =
    mean sin(2(θ_e−θ_f))`` (and the negative for ``θ_f``).
    """
    if not pairs:
        return 0.0, {}
    grad: dict[int, float] = {}
    total = 0.0
    for e, f in pairs:
        diff = angles[e] - angles[f]
        total += float(np.sin(diff) ** 2)
        g = float(np.sin(2.0 * diff))
        grad[e] = grad.get(e, 0.0) + g
        grad[f] = grad.get(f, 0.0) - g
    n = len(pairs)
    return total / n, {k: v / n for k, v in grad.items()}


def laminate_abd(
    d0: np.ndarray, angles: np.ndarray, thicknesses: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Classical-lamination-theory **[A, B, D]** stiffness matrices for a stack of
    plies (Wave FFFF, D087).

    Each ply ``k`` has principal-axis plane-stress stiffness ``D₀`` rotated to its
    fibre angle ``θ_k`` (:func:`rotate_plane_stress`) and thickness ``t_k``. With the
    through-thickness coordinates ``z_k`` measured from the **mid-plane** (so the
    stack is centred, ``z₀ = −h/2``, ``z_N = +h/2``, ``h = Σ t_k``),

        A = Σ_k Q̄_k (z_k − z_{k-1})              (extensional, 3×3)
        B = ½ Σ_k Q̄_k (z_k² − z_{k-1}²)          (extension–bending coupling)
        D = ⅓ Σ_k Q̄_k (z_k³ − z_{k-1}³)          (bending)

    Closed-form sanity: a single centred ply gives ``A = Q̄·t``, ``B = 0``,
    ``D = Q̄·t³/12``; any **mid-plane-symmetric** stack gives ``B = 0`` (the classic
    decoupling result); an unsymmetric stack (e.g. [0/90]) gives ``B ≠ 0``.
    """
    angles = np.asarray(angles, dtype=float).reshape(-1)
    thicknesses = np.asarray(thicknesses, dtype=float).reshape(-1)
    n = angles.size
    if n == 0:
        raise SolverError("laminate_no_plies")
    if thicknesses.size != n:
        raise SolverError("laminate_thickness_count_mismatch")
    if np.any(thicknesses <= 0.0):
        raise SolverError("laminate_nonpositive_thickness")
    h = float(np.sum(thicknesses))
    z = np.concatenate([[-h / 2.0], -h / 2.0 + np.cumsum(thicknesses)])
    A = np.zeros((3, 3))
    B = np.zeros((3, 3))
    D = np.zeros((3, 3))
    for k in range(n):
        qbar = rotate_plane_stress(d0, float(angles[k]))
        A += qbar * (z[k + 1] - z[k])
        B += 0.5 * qbar * (z[k + 1] ** 2 - z[k] ** 2)
        D += (1.0 / 3.0) * qbar * (z[k + 1] ** 3 - z[k] ** 3)
    return A, B, D


@dataclass
class StackingSequenceResult:
    """Output of :func:`optimize_stacking_sequence` (Wave FFFFF, D095)."""

    sequence: np.ndarray  # optimised ply angles, bottom (−h/2) → top (+h/2)
    a_matrix: np.ndarray  # extensional A (3×3)
    b_matrix: np.ndarray  # coupling B (3×3)
    d_matrix: np.ndarray  # bending D (3×3)
    objective_value: float  # D[0,0] for "max_bending"; ‖B‖_F for "min_coupling"


def _stacking_position_weights(n: int, thickness: float) -> np.ndarray:
    """Bending position weights ``c_k = (z_k³ − z_{k-1}³)/3`` for ``n`` uniform plies of
    thickness ``t`` in a mid-plane-centred stack — the per-ply multiplier on ``Q̄_11``
    in ``D_11``. Largest at the two surfaces, smallest at the mid-plane."""
    h = n * thickness
    z = np.concatenate([[-h / 2.0], -h / 2.0 + np.cumsum(np.full(n, thickness))])
    return (z[1:] ** 3 - z[:-1] ** 3) / 3.0


def optimize_stacking_sequence(
    d0: np.ndarray,
    ply_angles: np.ndarray,
    thickness: float = 1.0,
    objective: str = "max_bending",
    symmetric: bool = False,
) -> StackingSequenceResult:
    """Optimise the **stacking sequence** (ordering) of a fixed ply inventory under
    classical lamination theory (Wave FFFFF, D095).

    Two discrete objectives over the *arrangement* of the given plies (uniform
    ``thickness``):

    - ``"max_bending"`` — maximise the bending stiffness ``D_11``. Because
      ``D_11 = Σ_k c_k · Q̄_11(θ_k)`` with **fixed, position-only** weights
      ``c_k`` (:func:`_stacking_position_weights`, largest at the surfaces), the
      maximiser is the **rearrangement inequality**: place the stiffest plies (largest
      ``Q̄_11``) at the highest-``c`` positions (the outer surfaces). This is a
      **closed-form, provably global** optimum — no search.
    - ``"min_coupling"`` — minimise the extension–bending coupling ``‖B‖_F`` by
      exhaustive search over the distinct permutations (exact for the small inventories,
      ``n ≤ 8``, of 2.5-D laminate design).

    With ``symmetric=True`` the input ``ply_angles`` is the **bottom half-stack**; the
    full laminate is built as ``half + reversed(half)``, which makes ``B = 0`` *exactly*
    (the classical mid-plane-symmetry decoupling) regardless of the objective, and the
    half-stack order is then chosen to maximise ``D_11``.
    """
    d0 = np.asarray(d0, dtype=float)
    angles = np.asarray(ply_angles, dtype=float).reshape(-1)
    if angles.size == 0:
        raise SolverError("stacking_no_plies")
    if thickness <= 0.0:
        raise SolverError("stacking_nonpositive_thickness")
    if objective not in ("max_bending", "min_coupling"):
        raise SolverError("stacking_unknown_objective")

    def _abd(seq: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return laminate_abd(d0, seq, np.full(seq.size, thickness))

    if symmetric:
        # ply_angles is the half-stack; mirror about the mid-plane ⟹ B = 0 exactly.
        q_half = np.array([rotate_plane_stress(d0, float(a))[0, 0] for a in angles])
        order = np.argsort(-q_half)  # stiffest half-ply nearest the surface (rearrangement)
        half = angles[order]
        seq = np.concatenate([half, half[::-1]])
        a_m, b_m, d_m = _abd(seq)
        obj = float(np.linalg.norm(b_m)) if objective == "min_coupling" else float(d_m[0, 0])
        return StackingSequenceResult(seq, a_m, b_m, d_m, obj)

    n = angles.size
    if objective == "max_bending":
        c = _stacking_position_weights(n, thickness)
        q = np.array([rotate_plane_stress(d0, float(a))[0, 0] for a in angles])
        seq = np.empty(n)
        # rearrangement: highest Q̄_11 ply → highest-c position
        seq[np.argsort(-c)] = angles[np.argsort(-q)]
        a_m, b_m, d_m = _abd(seq)
        return StackingSequenceResult(seq, a_m, b_m, d_m, float(d_m[0, 0]))

    # min_coupling: exhaustive over distinct permutations (small n only)
    if n > 8:
        raise SolverError("stacking_min_coupling_too_many_plies")
    best_seq = None
    best_norm = np.inf
    for perm in {tuple(p) for p in permutations(angles.tolist())}:
        _, b_m, _ = _abd(np.array(perm))
        nb = float(np.linalg.norm(b_m))
        if nb < best_norm:
            best_norm = nb
            best_seq = np.array(perm)
    a_m, b_m, d_m = _abd(best_seq)
    return StackingSequenceResult(best_seq, a_m, b_m, d_m, float(np.linalg.norm(b_m)))


def _is_self_balanced_angle(theta: float, tol: float = 1e-9) -> bool:
    """A 0 or ±π/2 ply is its own balance — its ``Q̄₁₆ = Q̄₂₆ = 0`` (the off-axis
    shear-extension coupling vanishes on the principal axes). Angles are radians,
    period π."""
    r = float(theta) % np.pi
    return abs(r) < tol or abs(r - np.pi / 2.0) < tol or abs(r - np.pi) < tol


def make_balanced_laminate(angles: np.ndarray, symmetric: bool = True) -> np.ndarray:
    """Build a **balanced** (every ``+θ`` paired with a ``−θ``) — and optionally
    **symmetric** — stacking sequence (radians) from a list of distinct lamina angles
    (Wave DDDDDD, v14, D101).

    Because ``Q̄₁₆(θ)`` and ``Q̄₂₆(θ)`` are **odd** in ``θ`` while the extensional
    stiffness ``A = Σ Q̄_k t_k`` is order-independent, pairing each ``+θ`` with a
    ``−θ`` ply of equal thickness makes the extension–shear coupling **``A₁₆ = A₂₆ =
    0``** exactly. ``0`` and ``±π/2`` plies are already self-balanced and are not
    duplicated. With ``symmetric=True`` the balanced half-stack is mirrored about the
    mid-plane, which additionally gives ``B = 0`` (D087) — a **symmetric-balanced**
    laminate, the workhorse decoupled layup (no extension–shear *and* no
    extension–bending coupling).
    """
    angles = np.asarray(angles, dtype=float).reshape(-1)
    half: list[float] = []
    for a in angles:
        half.append(float(a))
        if not _is_self_balanced_angle(a):
            half.append(-float(a))
    half_arr = np.array(half, dtype=float)
    if symmetric:
        return np.concatenate([half_arr, half_arr[::-1]])
    return half_arr


def is_balanced_laminate(angles: np.ndarray, thicknesses: np.ndarray | None = None, tol: float = 1e-9) -> bool:
    """True iff the laminate is **balanced** — every non-self-balanced ``+θ`` ply is
    matched by a ``−θ`` ply of equal total thickness, so ``A₁₆ = A₂₆ = 0`` (Wave
    DDDDDD, v14, D101).

    Geometric test on the angles alone (radians): accumulate the **signed** thickness
    per acute magnitude ``|θ|`` (``+θ`` adds, ``−θ`` subtracts); the laminate is
    balanced iff every net is zero. ``0`` / ``±π/2`` plies are self-balanced and
    ignored.
    """
    angles = np.asarray(angles, dtype=float).reshape(-1)
    n = angles.size
    if n == 0:
        raise SolverError("balanced_laminate_no_plies")
    t = np.ones(n) if thicknesses is None else np.asarray(thicknesses, dtype=float).reshape(-1)
    if t.size != n:
        raise SolverError("balanced_laminate_thickness_count_mismatch")
    net: dict[float, float] = {}
    for a, ti in zip(angles, t, strict=True):
        if _is_self_balanced_angle(a):
            continue
        r = float(a) % np.pi  # +θ ↦ θ∈(0,π/2); −θ ↦ π−θ∈(π/2,π)
        key = round(min(r, np.pi - r), 9)  # acute magnitude (shared by ±θ)
        sign = 1.0 if r < np.pi / 2.0 else -1.0
        net[key] = net.get(key, 0.0) + sign * float(ti)
    return all(abs(v) < tol for v in net.values())


def simultaneous_elastic_orientation_mma(
    config: BenchmarkConfig,
    mesh: StructuredMesh,
    d0: np.ndarray,
    vf: float | None = None,
    fibre_continuity_limit: float | None = None,
    init_angles: np.ndarray | None = None,
    max_iter: int = 40,
    theta_bound: float = np.pi / 2.0,
    change_tol: float = 1e-3,
    periodic_continuity: bool = False,
) -> OrthotropicTOResult:
    """Minimise elastic compliance over the stacked design ``[ρ; θ]`` by
    **simultaneous** MMA, optionally subject to a **fibre-continuity** constraint
    (Wave XXX, D079).

    Inequalities for :func:`core.mma.mma_step`:

        g₁(x) = mean(ρ) − vf ≤ 0                       (volume; ∂/∂θ ≡ 0)
        g₂(x) = mean_{(e,f)} (θ_e − θ_f)² / lim − 1 ≤ 0   (fibre continuity, if set)

    The objective gradient stacks ``dC/dρ`` and ``dC/dθ``
    (:func:`orthotropic_compliance_sensitivities`); θ is box-bounded to
    ``[−θ_bound, θ_bound]`` (the rotated stiffness has period π so π/2 spans all
    directions). When ``fibre_continuity_limit`` is None only the volume
    constraint acts. Stops on ``max|Δx| < change_tol`` or ``max_iter``.
    """
    from structure_optimizer.core.filtering import density_filter
    from structure_optimizer.core.mma import MMAState, mma_step

    opt = config.optimization
    design = mesh.design_mask
    n_design = max(1, int(np.count_nonzero(design)))
    n_elem = mesh.elements.shape[0]
    vf_target = float(opt.volume_fraction) if vf is None else float(vf)
    pairs = _design_adjacency_pairs(mesh)

    rho = np.where(mesh.void_mask, opt.min_density, vf_target)
    angles = np.zeros(n_elem) if init_angles is None else np.asarray(init_angles, dtype=float).reshape(-1).copy()

    x = np.concatenate([rho[design], angles[design]])
    xmin = np.concatenate([np.full(n_design, opt.min_density), np.full(n_design, -theta_bound)])
    xmax = np.concatenate([np.ones(n_design), np.full(n_design, theta_bound)])
    state = MMAState()
    design_ids = np.where(design)[0]
    pos = {int(eid): i for i, eid in enumerate(design_ids)}

    metric_fn = period_aware_continuity if periodic_continuity else _continuity_metric

    compliance_history: list[float] = []
    volume_history: list[float] = []
    continuity_history: list[float] = []
    converged = False
    for _ in range(max_iter):
        rho[design] = x[:n_design]
        angles[design] = x[n_design:]
        compliance, d_rho, d_theta = orthotropic_compliance_sensitivities(config, mesh, rho, angles, d0)
        d_rho = density_filter(mesh, rho, d_rho, opt.filter_radius, opt.min_density)
        cont, cont_grad = metric_fn(angles, pairs)

        compliance_history.append(compliance)
        volume_history.append(float(np.mean(x[:n_design])))
        continuity_history.append(cont)

        df0dx = np.concatenate([d_rho[design], d_theta[design]])
        if fibre_continuity_limit is None:
            fval = np.array([float(np.mean(x[:n_design]) - vf_target)])
            dfdx = np.zeros((1, 2 * n_design))
            dfdx[0, :n_design] = 1.0 / n_design
        else:
            fval = np.array(
                [float(np.mean(x[:n_design]) - vf_target), cont / fibre_continuity_limit - 1.0]
            )
            dfdx = np.zeros((2, 2 * n_design))
            dfdx[0, :n_design] = 1.0 / n_design
            for eid, g in cont_grad.items():
                if eid in pos:
                    dfdx[1, n_design + pos[eid]] = g / fibre_continuity_limit
        x_new, _lmbda = mma_step(x, df0dx, fval, dfdx, xmin, xmax, state)
        change = float(np.max(np.abs(x_new - x)))
        x = x_new
        if change < change_tol:
            converged = True
            break

    rho[design] = x[:n_design]
    angles[design] = x[n_design:]
    compliance, _, _ = orthotropic_compliance_sensitivities(config, mesh, rho, angles, d0)
    cont, _ = metric_fn(angles, pairs)
    compliance_history.append(compliance)
    volume_history.append(float(np.mean(x[:n_design])))
    continuity_history.append(cont)
    return OrthotropicTOResult(
        densities=rho,
        angles=angles,
        compliance_history=compliance_history,
        volume_history=volume_history,
        continuity_history=continuity_history,
        continuity_limit=fibre_continuity_limit,
        converged=converged,
    )
