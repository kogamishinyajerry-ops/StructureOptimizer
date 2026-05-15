# D003 — Stress constraint at verification time only (Wave F / v1.6)

**Status**: Accepted (v1.6.0, 2026-05-16)

## Context

Wave F adds stress-constraint checking. The honest topology-optimization
approach is **stress-constrained SIMP**: include p-norm stress as a soft
constraint inside the SIMP loop, with sensitivity computed via the adjoint
method. This is a multi-month implementation in any FEM codebase (the
adjoint state needs to be solved at each iteration; the sensitivity
expression has terms for material AND geometric stiffness contributions).

## Decision

For v1.6, implement stress aggregation + checking **only at verification
time**:

1. After SIMP/BESO finishes, compute per-element von Mises stress from the
   final displacement field.
2. Apply p-norm or KS aggregation, gated by `density_threshold`.
3. Compare aggregated stress to `limit`; report `stress_constraint_failed`
   if exceeded.
4. Do **not** modify the SIMP sensitivity to push design away from
   high-stress regions.

## Alternatives considered

1. **Heuristic penalty in SIMP gradient** (`σ²` term added to sensitivities).
   Rejected: not mathematically justified; can mask real design issues;
   conflicts with the rigorous adjoint approach when it's eventually added.
2. **Full adjoint-based stress-constrained SIMP**. Deferred: out of v2.0
   scope; needs a dedicated ADR + ~600 LOC + 50 tests + benchmark validation.
3. **No stress check at all** (status quo). Rejected: users have repeatedly
   asked "is this design safe?"; need a first-class verification answer.

## Consequences

- Users who care about stress get a real constraint check on the final
  design, with a clear `stress_constraint_failed` status code.
- Users will sometimes get designs that satisfy compliance but violate
  stress, and they'll need to either adjust the volume fraction up or
  manually iterate. Document this in the tutorial.
- The verification check is **cheap** (one extra solve per verify call) —
  no SIMP loop overhead.

## Reopening criteria

- ≥3 users report "I keep getting stress_constraint_failed and can't easily
  fix it without massive volume_fraction increase". → time to write the
  adjoint-method ADR.
- A user reports a benchmark where stress-constrained SIMP gives substantially
  better mass-vs-stress trade-off than the current approach.
