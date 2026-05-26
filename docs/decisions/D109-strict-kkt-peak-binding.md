# D109 — strictly KKT-binding peak-binding (closes D104's deferral) (Wave DDDDDDD, v15)

**Status**: Accepted
**Wave**: DDDDDDD (v15)
**Supersedes**: none (closes D104's reopening, extends D104 peak_binding_mma)
**Superseded by**: none

## Context

D104 (v14) demonstrated the *coupling* — minimising `J(ω_op)` in the anti-resonance
valley raises a flanking resonance — but honestly recorded as a reopening criterion:

> *"A strictly-active flanking constraint with a measurable J sacrifice (positive KKT
> multiplier)."*

D104 found the constraint acting as a **basin selector**, not a binding constraint: at the
limits it probed (≥ 0.3·initial flank) the J-optimum basin already had a low flank, so the
flank stayed below the limit and `J` was not sacrificed. D109 investigates tighter limits.

## Decision

- **`kkt_binding_status(config, mesh, result, ..., tol=0.1, j_reference=None)`** →
  `PeakBindingKKTStatus`. A diagnostic that recomputes a `peak_binding_mma` design's true
  flanking peak by dense sweep, forms `g₁ = flank/limit − 1`, and reports the constraint
  **active** when `|g₁| ≤ tol`. With `j_reference` (the unconstrained min `J`) the
  `active_multiplier` field reports the relative objective sacrifice `J/J_ref − 1` —
  strictly positive iff the KKT multiplier is > 0.

- **The finding that closes D104**: a **tight enough limit** (empirically ≲ 0.1·initial
  flank) drives the flank *below the J-optimum basin's natural level*, so the constraint
  goes **active** (`g₁ → 0`) **and** `J(ω_op)` is forced up — a genuine objective
  trade-off. D104 simply never probed tight enough.

## Verification (quantitative anchors)

`tests/test_kkt_peak_binding.py` (6 passed; adjacent regression on `test_peak_binding`
[D104] + `test_bandwidth_adaptive_band`). Smoke 24×10 mesh, against a dense sweep:

1. **strictly binding (tight limit 0.08·init)**: `kkt_binding_status` reports
   `active=True` (`|g₁| ≤ 0.1`, probe `g₁≈−0.03`) **and** `active_multiplier > 0` (probe
   `+0.37`: `J` ≈ 1.37× the unconstrained minimum) — the constraint is active *and* costs
   the objective. **This is the strict KKT binding D104 could not exhibit.**
2. **inactive at loose limit (the D104 basin-selector regime, 0.40·init)**:
   `active=False`, `g₁ < −0.1` (flank well below limit), `active_multiplier < 0` (`J` no
   larger than unconstrained, probe `−0.72`).
3. **the active constraint suppresses the flank**: the tight design's flank is `< 0.5×`
   the loose (≈unconstrained-level) design's flank — it does real work, at a J cost.
4. **g₁ matches an independent dense sweep** (rel 1e-9).
5. **`active_multiplier is None`** without a reference (active flag still computes).
6. **deterministic** (no randomness in the diagnostic).

## Honest scope notes

- **Strict binding requires a *tight* limit (≲ 0.1·initial flank).** At loose limits the
  D104 basin-selector behaviour holds (constraint inactive, no J cost) — D109 does not
  contradict D104, it *extends* it: the binding regime is the tight-limit corner, and the
  diagnostic distinguishes the two regimes quantitatively.
- **The binding regime is non-convex / path-sensitive.** The intermediate limit 0.07·init
  probed as transiently infeasible (`g₁≈+0.7`) — MMA on the dynamic objective is
  non-convex, so "active" is not monotone in the limit. The test uses 0.08·init (a
  robust, deterministic active point) and 0.40·init (robust inactive); it does **not**
  claim a clean monotone active-set boundary.
- **`active_multiplier` is a *relative-sacrifice proxy* (`J/J_ref − 1`), not the exact MMA
  dual.** Computing the true Lagrange multiplier `λ` would need the MMA dual iterate; the
  sign (`> 0` ⟺ objective sacrificed ⟺ `λ > 0`) is what is asserted, which is the KKT
  binding criterion. I do not report a calibrated `λ`.
- **Smoke 24×10, single flanking mode, Rayleigh light damping** (cf. D104). Finer-mesh /
  multi-flanking-mode binding is not claimed.

## Reopening criteria

- **Exact MMA dual multiplier `λ`** (not the relative-sacrifice proxy).
- **Multi-flanking-mode** active sets (several constraints active simultaneously).
- **A monotone active-set characterisation** (which limits bind, robustly) on a finer
  mesh.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
