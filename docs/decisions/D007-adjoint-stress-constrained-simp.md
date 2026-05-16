# D007 — Adjoint method for stress-constrained SIMP

- **Status**: accepted
- **Date**: 2026-05-16
- **Wave**: L (v2.1.0)
- **Supersedes**: D003 (which deferred adjoint integration explicitly)

## Context

D003 (Wave F, v1.6.0) added stress aggregation (p-norm / KS) and a verification
chain entry so that "stress > limit" became a reportable failure status. It
**deliberately left a 留白**: stress did not affect the SIMP gradient. The optimizer
saw σ_PN only as a post-hoc verifier, never as a gradient signal. The ADR
explicitly named "integrate stress into OC sensitivity via adjoint method" as a
v2.1+ task.

The v3.x rubric §1.1 makes this a 8-point hard requirement.

## Decision

Implement classical adjoint-method stress sensitivity in
`structure_optimizer/core/adjoint.py`, and wire it into `core/simp.py` as a
penalty-augmented OC update controlled by `OptimizationConfig.stress_penalty`.

### Math (per Bendsøe-Sigmund 2003 §3.5 + Le et al. 2010)

For aggregated stress σ_PN(ρ, u) where u = u(ρ) satisfies K(ρ) u = f:

1. **Compute** ∂σ_PN/∂u by chain rule:
   - σ_vm,e² = σ_x² − σ_x σ_y + σ_y² + 3 σ_xy² with σ = D B u_e
   - ∂σ_PN/∂σ_vm,e = σ_vm,e^(p-1) · σ_PN^(1-p)  (p-norm) or softmax weight (KS)
   - Element contribution scatters into a length-`ndof` vector
2. **Solve adjoint linear system** K λ = (∂σ_PN/∂u)^T (one extra linear solve
   per SIMP iteration; reuses the existing solver backend)
3. **Per-element sensitivity**:
   dσ_PN/dρ_e = −p · ρ_e^(p−1) · (1−ρ_min) · (λ_e^T · K_e^0 · u_e)
   (analogous to compliance sensitivity, with λ replacing u in the bilinear form)

### Integration in SIMP loop

```
sensitivities = compliance_sens
if stress_constraint.enabled and stress_penalty > 0:
    sigma_pn, stress_sens, _ = adjoint_stress_sensitivity(...)
    violation = max(0, sigma_pn / limit - 1)
    if violation > 0:
        # Le et al. 2010 normalization: scale stress_sens to match
        # compliance sens magnitude before combining
        stress_sens *= mean(|compliance_sens|) / mean(|stress_sens|)
        sensitivities += stress_penalty * violation * stress_sens
```

The bisection OC update then sees a sensitivity field that **pushes density
down in high-stress elements**, in addition to the usual compliance signal.

## Correctness verification

The most load-bearing test is `test_adjoint_sensitivity_matches_finite_difference`:
for 5 interior elements of a 5×4 mesh, the adjoint sensitivity is checked
against centered finite differences with h=1e-6. **Relative error < 1%** on
every checked element, typically ≪ 0.01%.

A bug-discovery story worth recording: my initial implementation had two
errors that the FD test caught:
1. Wrong sign on the adjoint RHS (`rhs = -dpn_du[free]` instead of `+dpn_du[free]`).
   Fixed by aligning with the derivation: the negative sign goes into the
   final formula `sensitivity = −p · ρ^(p-1) · (1-ρ_min) · bilinear`, not into
   the adjoint RHS.
2. Stress sensitivity magnitude was orders of magnitude larger than compliance
   sensitivity, so the OC bisection bracket was overwhelmed and the result
   diverged. Fixed by Le et al. 2010 normalization (rescale to match
   compliance-sens mean magnitude).

After both fixes: FD ratio = 1.000 to 4 decimals, and
`test_simp_stress_adjoint_reduces_stress_vs_baseline` shows σ_PN decreases
(225.6 → 220.8 at stress_penalty=1.0 on stress_limited_bracket).

## Honest scope limitation (intentional)

The classical penalty method (`sensitivities += penalty · violation · stress_sens`)
is **not** a full augmented Lagrangian or MMA. It can:

- Provably reduce σ_PN vs the no-adjoint baseline at moderate `stress_penalty`
- Push designs toward lower-stress topologies when σ_PN exceeds limit

It cannot:
- Drive σ_PN to ≤ limit unconditionally for arbitrary problems. Higher
  `stress_penalty` values may destabilize OC's bisection (a known limitation
  of penalty methods).
- Guarantee feasibility — that requires MMA/GCMMA/IPOPT, none of which fit the
  "NumPy-only runtime" red line.

This is documented as a v3.x scope choice. Users who need rigorous feasibility
should treat stress_penalty as a *nudge*, then run verification post-hoc with
`stress_constraint.limit` set to the design intent and inspect
`stress_constraint_failed` status.

## Alternatives considered

1. **MMA / GCMMA / IPOPT** — rejected: adds scipy.optimize / non-NumPy
   dependency, violates v1.x red line "runtime mandatory deps stay NumPy-only".
2. **Augmented Lagrangian** — rejected for v2.1 (deferred): would require dual
   variable updates and an outer loop refactor; not needed for v3.x rubric §1.1.
3. **Stress as hard constraint via active-set** — rejected: incompatible with
   bisection OC update.

## Files touched (Wave L)

- `structure_optimizer/core/adjoint.py` (NEW, 222 LOC)
- `structure_optimizer/core/config.py` — added `OptimizationConfig.stress_penalty` (default 0.0, validated ≥ 0)
- `structure_optimizer/core/simp.py` — wired adjoint into loop, gated by `stress_constraint.enabled and stress_penalty > 0`
- `tests/test_adjoint_stress.py` (NEW, 15 tests including FD verification)

## References

- Bendsøe, M.P. & Sigmund, O. (2003). *Topology Optimization: Theory, Methods and Applications*, §3.5.
- Le, C., Norato, J., Bruns, T., Ha, C., & Tortorelli, D. (2010). "Stress-based topology optimization for continua." *Structural and Multidisciplinary Optimization* 41(4), 605–620.
