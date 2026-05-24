# D082 — design-grade buckling sensitivity: the ∂u/∂ρ adjoint (Wave AAAA, v12)

**Status**: Accepted
**Wave**: AAAA (v12)
**Supersedes**: none (extends D074, completes its deferral)
**Superseded by**: none

## Context

D074 (v11 Wave SSS) **deferred** buckling-constrained / buckling-driven topology
optimisation, with explicit probe evidence: the existing analysis-grade
`buckling_sensitivity` (Lund / Bendsøe-Sigmund adjoint-free formula) **ignores the
indirect ∂u/∂ρ contribution** to the geometric stiffness `K_g = K_g(σ(u(ρ)))`, and
a fixed-volume λ_crit *ascent* driven by that truncated gradient *lowered* λ_crit
(20.1 → 8.1) — the gradient pointed the wrong way. D074's recorded reopening
criterion:

> *"design-grade buckling sensitivity (∂u/∂ρ + void-mode relaxation) to unlock
> buckling-driven TO. Entry condition: a probe where fixed-volume λ_crit ascent
> increases λ_crit above baseline."*

v12 Wave AAAA meets that entry condition and closes the deferral.

## Decision

- **`buckling.design_grade_buckling_sensitivity(config, mesh, densities,
  displacements, eigenvalue, eigenvector, g_penalty=None)`** — the **full** adjoint
  sensitivity. With `φ` re-normalised so `φᵀ(−K_g)φ = 1` and `K φ = λ(−K_g)φ`,

      dλ/dρ_e = dscale_e·φₑᵀkₑφₑ + λ·g_dscale_e·φₑᵀkgeₑ(uₑ)φₑ − λ·dscale_e·μₑᵀkₑuₑ
      K μ = w,   w = ∂(φᵀK_gφ)/∂u

  The first two terms are the explicit `∂K/∂ρ` and `∂K_g/∂ρ|_u` (what the
  analysis-grade formula keeps); the **third is the adjoint term** for the
  implicit `∂u/∂ρ` via the pre-buckling state. `K_g^e` is linear in `u_e`, so
  `w` is assembled element-wise as `φₑᵀ K_g^e(unit_k) φₑ`. `dscale_e` matches
  `solve_linear_elastic`'s SIMP derivative.

- **`buckling.assemble_geometric_stiffness(..., g_penalty=None)`** — the
  **void-mode relaxation** knob: the geometric stiffness interpolation
  `ρ^{g_penalty}` (default `opt.penalty`, behaviour-preserving). A steeper
  `g_penalty` drives low-density elements' `K_g` toward zero faster, suppressing
  the spurious localized buckling modes they otherwise host.

- **`buckling.maximize_buckling_load(config, mesh, vf=None, n_steps=30, …)`** —
  fixed-volume λ_crit maximisation (minimise `−λ_crit` s.t. `mean(ρ) ≤ vf`) via
  move-limited MMA on the design-grade sensitivity. Returns `BucklingTOResult`.

- **`tests/test_design_grade_buckling.py`** — five quantitative anchors.

## Verification (quantitative anchors)

`tests/test_design_grade_buckling.py` (5 passed; adjacent regression on
test_buckling = 11 passed):

1. **design-grade ∂λ/∂ρ vs central FD ≤ 1e-3** on the top-|sensitivity| elements
   (measured ≈ 4e-8) — validating the adjoint term the analysis-grade truncates.
2. **entry condition met**: a fixed-volume ascent on the design-grade gradient
   **raises** λ_crit above baseline (20.1 → 34.8), while the same ascent on the
   analysis-grade gradient **lowers** it (20.1 → 8.1); design-grade final > analysis-
   grade final. This is the decisive D074 gate.
3. **`maximize_buckling_load` driver**: final λ_crit > initial, volume feasible
   (≤ vf+0.02), deterministic.
4. **void-mode relaxation knob**: `g_penalty=None` reproduces the original K_g
   exactly; a steeper `g_penalty` strictly reduces `‖K_g‖` (sub-unity densities).
5. **property test**: design-grade matches FD on the top element for several
   random feasible densities.

## Honest scope notes

- **The ∂u/∂ρ adjoint, not void-mode relaxation, is what closed the deferral.**
  On the coarse smoke mesh the validated ascent (20.1 → 34.8) uses the default
  `g_penalty = opt.penalty` (the same ρ^p the eigenpair is computed with) — i.e.
  the adjoint term *alone* reverses the wrong-way gradient. Void-mode relaxation
  is shipped as a tunable knob (tested independently) for finer meshes / lower
  densities where spurious localized modes bite; it is **not** claimed to be what
  fixes the smoke-mesh case.
- **The eigenpair is still a single lowest mode, no mode-tracking.** Buckling TO
  is notorious for **mode switching** (the lowest mode changes identity along the
  optimisation) and **repeated eigenvalues** (the sensitivity is non-smooth at
  multiplicity). `maximize_buckling_load` follows the lowest `λ` each step without
  tracking or multi-eigenvalue (sub-gradient) handling — the ascent has a visible
  transient dip (it₅ ≈ 8.4) before climbing to 34.8, consistent with an early mode
  reshuffle. Robust mode-tracking / k-lowest aggregation is a reopening item.
- **Driver is ascent (maximise λ), not a buckling *constraint* in a compliance
  problem.** Combining the design-grade sensitivity as a third MMA inequality
  alongside compliance + volume (true buckling-*constrained* TO) is the natural
  next step, not done here.
- **Single Gauss-point K_g** (element-centroid stress, as in the v4 module) — the
  geometric stiffness inherits that approximation; the adjoint differentiates
  exactly that kernel (FD-validated), so it is consistent.
- **Dense assembly + adjoint solve per step** — fine for smoke meshes; the adjoint
  adds one linear solve per buckling-sensitivity evaluation over the analysis-grade
  cost.

## Reopening criteria

- **Mode-tracking + repeated-eigenvalue (sub-gradient) handling** for robust
  buckling optimisation through mode switches and multiplicities.
- **Buckling-*constrained* MMA** (λ_crit ≥ λ_safety as a third inequality with
  compliance + volume), the production use case.
- **k-lowest-mode aggregation** (e.g. KS / p-norm over the smallest modes) to
  smooth the non-differentiable min-eigenvalue.
- **Continuation on `g_penalty`** (void-mode relaxation schedule) for fine meshes
  where localized modes dominate.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
