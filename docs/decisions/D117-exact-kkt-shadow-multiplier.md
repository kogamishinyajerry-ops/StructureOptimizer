# D117 — exact KKT shadow-price multiplier for peak-binding (Wave DDDDDDDD, v16)

**Status**: Accepted (positive machinery + **honest partial defer** of cross-regime stability)
**Wave**: DDDDDDDD (v16)
**Supersedes**: none (advances D109's reopening; D109's proxy retained as cross-regime indicator)
**Superseded by**: none

## Context

D109 (v15) closed D104's deferral by showing the flanking-peak constraint is strictly
KKT-binding at a tight limit, but reported the objective sacrifice through a **relative
proxy** `active_multiplier = J/J_ref − 1` and recorded as a reopening:

> *"`active_multiplier` is a relative-sacrifice proxy (J/J_ref−1), not the exact MMA dual λ."*

D117 upgrades this to the **exact Lagrange multiplier** — the constraint's shadow price
`λ = −dJ*/d(limit)` (envelope theorem) — and honestly bounds where it is reliable for the
production optimiser.

## Decision

- **`peak_binding_exact_multiplier(j_star_fn, limit, rel_delta=0.01)`** — the exact KKT /
  Lagrange multiplier `λ = −dJ*/d(limit)` by central finite difference of a caller-supplied
  re-solve `j_star_fn(limit) → J*`. `λ > 0` ⟺ active (relaxing the limit lowers `J*`);
  `λ ≈ 0` ⟺ inactive. This is the **exact** multiplier for a differentiable value function,
  replacing D109's relative-sacrifice proxy with the true shadow price.

## Probe (why cross-regime stability is deferred — honest, not faked)

Applied to the production `peak_binding_mma` (non-convex MMA with **in-loop band
re-gridding**):

- **Active regime** (tight limit `0.08·init`): `λ = +0.73` — a clean, positive shadow price
  (relaxing the firmly-active limit lowers `J*`, exactly the KKT sign). **Reliable.**
- **Inactive regime** (loose limit `0.40·init`): the central FD gave `λ = −1.10`. The true
  multiplier is `0` (inactive), but `J*(limit)` swung **~40%** across `0.39→0.41·init`: the
  optimiser's path-noise (regrid + non-convexity, the D104/D109 basin-selector) **exceeds**
  the active-regime signal. There is no stable shadow price to extract where the constraint
  is not binding.

So `peak_binding_exact_multiplier` is the genuine exact multiplier **in the firmly-active
regime where a multiplier matters**; a *cross-regime* stable exact `λ` is **honestly
deferred** (mirrors D074/D091's probe-evidenced defers). D109's proxy remains the robust
active/inactive indicator across both regimes.

## Verification (quantitative anchors)

`tests/test_kkt_exact_multiplier.py` (6 fast passed + 1 `--run-slow` production anchor):

1. **headline — exact recovery**: for `J*(L)=A/L` the closed-form shadow price `λ=A/L²` is
   recovered by the central-FD machinery (abs 1e-2).
2. **linear exact**: `J*(L)=c−mL` ⟹ `λ=m` to machine precision (central FD exact on linears).
3. **inactive ⟹ λ=0**: a limit-independent `J*` gives `λ=0` exactly (envelope signature of
   inactivity).
4. **active ⟹ λ>0**: a feasible-monotone `J*` gives the positive KKT sign (`λ=1`, abs 1e-9).
5. **central-FD convergence**: shrinking `rel_delta` brackets the closed-form `λ` (O(δ²)).
6. **guards**: `rel_delta ∉ (0,1)` and non-positive limit raise `SolverError`.
7. **(--run-slow) production active regime**: the exact shadow price of `peak_binding_mma`'s
   `J*(limit)` at `0.08·init` is **positive** (deterministic; the firmly-active KKT sign).

## Honest scope notes

- **Exact for a differentiable value function** (the envelope theorem is exact; central FD
  is exact for linear `J*` and O(δ²) otherwise). The "exactness" is mathematical, not a
  claim that the production `J*` is everywhere differentiable.
- **Production reliability is regime-dependent**: trustworthy where the constraint is
  firmly active; noise-dominated (true `λ=0`) where inactive — **stated explicitly**, with
  the probe numbers, rather than presenting a smooth cross-regime `λ`.
- **Not the MMA subproblem dual**: this is the *value-function* shadow price (envelope
  theorem), not the internal MMA dual variable. The two coincide at a true KKT point; the
  envelope FD is the principled, solver-agnostic route and needs no MMA internals.
- D109's `active_multiplier` proxy is **kept** (not removed) — the robust cross-regime
  active/inactive indicator; D117 adds the exact shadow price for the active regime.

## Reopening criteria

- **Cross-regime stable exact `λ`** once the peak-binding optimiser is made smoother (fixed
  band — no in-loop regrid — or a convex surrogate) so `J*(limit)` is differentiable enough
  for a stable inactive-regime FD.
- **MMA subproblem dual** extraction (expose the converged dual variable) as an independent
  cross-check of the envelope shadow price.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio optional),
2D/2.5D only, local `pytest -q` (no network), single-line stderr + `SolverError` status
strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM, self-deprecation over
self-promotion.
