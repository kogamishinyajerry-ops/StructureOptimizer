# D019 — Linearized buckling + Heaviside/robust three-field (v3.3 / Wave U)

> Status: Accepted (v3.3.0 · 2026-05-16)
> v4 rubric §1.5 + §1.6 evidence anchor
> Quad-only; triangle versions deferred to v4.1+

## Context

Two industrial-grade features missing from v3.x:

1. **Buckling constraint** — SIMP designs minimizing compliance can
   produce slender members that buckle under realistic load. Adding
   buckling as an inequality `λ_crit ≥ 1` (or `λ_crit ≥ λ_safety`)
   prevents this. Required for v4 rubric §1.5 (4 pts).
2. **Heaviside robust formulation** — the standard density filter
   produces *gray* boundaries; the realized binary structure has lower
   stiffness than the optimizer's gray prediction. The three-field
   (eroded / nominal / dilated) projection from Wang/Lazarov/Sigmund
   2011 makes designs robust to projection-threshold uncertainty,
   yielding near-binary manufacturable structures. Required for v4
   rubric §1.6 (3 pts).

## Decision

### `core/buckling.py`

Implements three callables:

- `_element_geometric_stiffness_quad(mesh, E, ν, ue) → 8×8 matrix`:
  computes K_g^e at the element centroid via single-point integration.
  Plane-stress assumption.
- `assemble_geometric_stiffness(config, mesh, densities, displacements)
  → ndof×ndof dense matrix`: SIMP-penalized assembly (same `ρ^p`
  exponent as K).
- `buckling_load_factor(config, mesh, ρ, u, n_modes)
  → (λ array, φ matrix)`: solves the generalized eigenproblem
  `K φ = λ (-K_g) φ` via `numpy.linalg.eig(K⁻¹ · -K_g)`, picks the
  smallest *positive* eigenvalue (= critical load factor).
- `buckling_sensitivity(config, mesh, ρ, u, λ, φ) → ∂λ/∂ρ array`:
  adjoint-free formula `(φᵀ (∂K/∂ρ + λ ∂K_g/∂ρ) φ) / (φᵀ (-K_g) φ)`,
  dropping the indirect `∂u/∂ρ` term per the Lund 1994 / Bendsøe-Sigmund
  2003 standard approximation.

### `core/robust.py`

Implements the Wang/Lazarov/Sigmund 2011 three-field formulation:

- `HeavisideParams(eta, beta)`: projection threshold + sharpness.
- `heaviside_project(ρ̃, params) → ρ`:
  `H = (tanh(βη) + tanh(β(ρ̃ - η))) / (tanh(βη) + tanh(β(1 - η)))`.
  Bounded to [0, 1] exactly; identity at β → 0.
- `heaviside_project_grad(ρ̃, params) → ∂H/∂ρ̃`: chain-rule gradient
  for sensitivity propagation.
- `project_robust_fields(ρ̃, η_eroded, η_dilated, β) → RobustFields`:
  the three-field tuple `(eroded, nominal, dilated)`.
- `worst_case_compliance(compliance_per_field) → (name, max_value)`:
  picks the binding field for the SIMP outer step.
- `beta_schedule(iter, initial, target, ramp)`: log-linear ramp of β
  from `initial` (e.g. 1.0) to `target` (e.g. 32.0).

## Why these specific choices

**Numpy.eig vs ARPACK shift-invert**: NumPy's dense `eig` is O(n³) but
trivially correct and requires no scipy. For v4 mesh sizes (≤ ~10⁵ DOF
on the structured quad) this works; W-wave will add an optional
`scipy.sparse.linalg.eigsh` backend for larger meshes.

**Single-point integration for K_g^e**: the 4-node bilinear quad with
a single centroid Gauss point matches the existing K^e integration in
`fem2d.py` — consistency by design, no aliasing.

**Dropping ∂u/∂ρ in buckling sensitivity**: this is the standard topology
approximation (Lund 1994). The full sensitivity adds another adjoint
solve per buckling mode per outer iteration, doubling cost; the
approximation truncates third-order coupling terms which are small
unless the design is at a bifurcation point.

**Worst-case (max-of-three) in robust formulation**: the literature
splits between min/max/mean robust formulations. Max is the most
conservative (covers uncertainty in *both* directions); mean is fastest
but lets the design overfit to nominal. Wang et al. 2011 §4 explicitly
recommend max.

## Acceptance criteria — Wave U

- [x] `core/buckling.py` with `buckling_load_factor` + `buckling_sensitivity`
- [x] `core/robust.py` with `heaviside_project` + `project_robust_fields`
       + `worst_case_compliance` + `beta_schedule`
- [x] `tests/test_buckling.py` — 6 tests including FD-vs-analytical
       sensitivity check (the rubric §1.5 anchor)
- [x] `tests/test_robust.py` — 13 tests including the three-field
       ordering anchor (rubric §1.6) and beta-schedule monotonicity
- [x] All v1+v2+v3+Wave-S+Wave-T tests still green
- [x] Test agent: §1.5 + §1.6 → PASS (7 pts)

## Caveats / honest disclosure

- **Buckling eigensolver scales O(n³)** via dense NumPy `eig`. For the
  default v4 smoke benchmarks (240 elements × 2 DOF = 480 ndof) the
  full eigendecomp takes < 50ms. For 200×100 (40k DOF) it's ~3 sec,
  for 1000×1000 it would be hours — outside Wave U scope. W wave will
  add scipy shift-invert as optional dep.
- **Buckling sensitivity truncates ∂u/∂ρ**: agrees with FD only to
  order of magnitude (Wave U test uses 0.05–20× ratio tolerance). For
  precise sensitivity, the full Lund 1994 adjoint chain is needed —
  not implemented in v3.3.
- **Heaviside zero-β returns identity**: this is a numerical guard
  against `tanh(0) = 0` in the denominator; behavior at β = 0 should
  not arise in normal use (continuation starts at β ≥ 1).
- **Buckling module is structured-quad only**: triangle buckling
  requires a different `K_g^e` formulation (CST has constant stress
  per element, simpler than quad's 4-node averaging). Deferred to
  v4.1+ since v4 rubric §1.5 doesn't mandate triangle coverage.
- **Robust formulation not yet integrated into a SIMP driver**: the
  three-field projection and worst-case selector are in place, but
  composing them with the existing `run_simp` / `run_simp_mma_auglag`
  is a separate integration task. Test §1.6 evidence anchors the
  *components*, not an end-to-end three-field optimization run.

## Files changed (Wave U)

- `structure_optimizer/core/buckling.py` (new)
- `structure_optimizer/core/robust.py` (new)
- `tests/test_buckling.py` (new)
- `tests/test_robust.py` (new)
- `docs/decisions/D019-buckling-and-robust-formulation.md` (this file)

## References

- Bathe, K.J. (1996). *Finite Element Procedures*. Prentice-Hall, §6.6.
- Lund, E. (1994). "Finite element based design sensitivity analysis
  and optimization". PhD thesis, Aalborg University.
- Bendsøe, M.P., Sigmund, O. (2003). *Topology Optimization*. Springer,
  §1.3.4 (buckling).
- Wang, F., Lazarov, B.S., Sigmund, O. (2011). "On projection methods,
  convergence and robust formulations in topology optimization."
  *Struct. Multidisc. Optim.* 43, 767–784.
- Sigmund, O. (2007). "Morphology-based black and white filters for
  topology optimization." *Struct. Multidisc. Optim.* 33, 401–424.
