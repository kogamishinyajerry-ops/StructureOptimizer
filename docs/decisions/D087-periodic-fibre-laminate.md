# D087 — period-aware fibre continuity (sin²Δθ) + laminate [A,B,D] (Wave FFFF, v12)

**Status**: Accepted
**Wave**: FFFF (v12)
**Supersedes**: none (extends D079)
**Superseded by**: none

## Context

D079 (v11 Wave XXX) added the orthotropic SIMP driver with a fibre-continuity
constraint, the graph-Laplacian `mean (θ_e − θ_f)²`. Its recorded reopening
criterion:

> *"period-aware fibre continuity (sin²Δθ) + laminates."*

A fibre angle is **π-periodic** — θ and θ+π describe the *same* fibre orientation —
so `(θ_e − θ_f)²` wrongly punishes a +89°/−89° seam as a 178° jump even though the
plies are only 2° apart in orientation, and it is not invariant to the ±π wrap a
free optimiser will happily introduce. And D079 modelled only in-plane stiffness,
no through-thickness laminate. v12 Wave FFFF closes both.

## Decision

- **`orthotropic_simp.period_aware_continuity(angles, pairs)`** — the metric
  `mean_{(e,f)} sin²(θ_e − θ_f)` with gradient `mean sin(2(θ_e−θ_f))`. `sin²` has
  period π, so it is invariant to adding π to any ply (`sin²(θ_e+π−θ_f)=sin²(θ_e−θ_f)`)
  and vanishes at both Δθ=0 and Δθ=π; for small Δθ, `sin²(Δ)≈Δ²` so it degenerates
  to D079's metric. Mirrors `_continuity_metric`'s `(value, grad-dict)` signature.

- **`orthotropic_simp.simultaneous_elastic_orientation_mma(..., periodic_continuity=
  False)`** — an **opt-in** flag selecting `period_aware_continuity` for the
  driver's continuity constraint. **Default `False` reproduces D079 exactly** (no
  regression).

- **`orthotropic_simp.laminate_abd(d0, angles, thicknesses) → (A, B, D)`** —
  classical lamination theory for a centred stack (`z` from `−h/2` to `+h/2`):
  `A = Σ Q̄_k Δz`, `B = ½ Σ Q̄_k Δz²`, `D = ⅓ Σ Q̄_k Δz³`, with `Q̄_k` the
  rotated plane-stress stiffness.

- **`tests/test_periodic_fibre_laminate.py`** — seven anchors.

## Verification (quantitative anchors)

`tests/test_periodic_fibre_laminate.py` (7 passed; adjacent regression on
test_orthotropic_simultaneous = 6 passed):

1. **π-periodicity / ±89° not penalised**: the sin² metric on a +89°/−89° seam
   scores < 2e-3 (≈ sin²2°) while the squared metric scores > 9.0; adding π to a ply
   leaves the metric unchanged to ≤ 1e-12.
2. **small-angle degeneration**: at 2° apart, `sin²/squared` ratio is within 1e-3 of 1.
3. **continuity gradient vs central FD** ≤ 1e-6 on a 5-angle ring.
4. **single centred ply**: `A = Q̄·t`, `B = 0`, `D = Q̄·t³/12` exactly.
5. **symmetric vs unsymmetric coupling**: mid-plane-symmetric [45/−45/−45/45] gives
   `‖B‖ ≤ 1e-3`; unsymmetric [0/90] gives `‖B‖ > 1`; `A`, `D` symmetric.
6. **driver opt-in**: with a ±89° checkerboard initial field, the
   `periodic_continuity=True` driver reports continuity < 2e-3 where the default
   (squared) driver reports > 1.0.
7. **guards**: no plies / thickness-count mismatch / non-positive thickness raise
   `SolverError`.

## Honest scope notes

- **`laminate_abd` is a standalone CLT calculator, not wired into a driver.** It
  takes ply angles + thicknesses and returns [A,B,D]; it does **not** optimise the
  stacking sequence, and the orthotropic SIMP driver remains a single-layer in-plane
  problem (the laminate is reported, not designed). Stacking-sequence optimisation
  and a B-coupling objective are reopening items.
- **`sin²Δθ` is period-π but still has a spurious stationary point at Δθ=π/2.** It
  correctly identifies aligned (0, π) and is smooth, but its gradient also vanishes
  at a *perpendicular* seam (Δθ=π/2, a genuine maximum) — fine for a penalty (we sit
  near minima) but it is not a metric distance on the circle; a true geodesic angle
  distance is a possible refinement.
- **Opt-in default preserves D079.** I did **not** switch the driver's default to
  period-aware, because D079's tests and any downstream expectations assume the
  squared metric; flipping the default would be an unannounced behaviour change.
  Callers opt in explicitly.
- **`B≠0`/`B=0` thresholds are scale-dependent.** The `‖B‖ > 1` / `≤ 1e-3` test
  bounds are loose, scale-aware sanity gates (the coupling for [0/90] is ~6e10 in SI
  Q̄ units), not tight tolerances — the *exact* anchors are the single-ply closed
  forms and the symmetric-stack `B=0`.

## Reopening criteria

- **Stacking-sequence optimisation** over `laminate_abd` (discrete ply angles,
  symmetry/balance constraints) with a coupling-`B` or bending-`D` objective.
- **Geodesic angle distance** on the circle as the continuity metric (vs `sin²`,
  which is period-π but not a metric and is stationary at the perpendicular seam).
- **3-D/2.5-D layered stiffness** coupling `laminate_abd` back into the element
  stiffness so the through-thickness layup *drives* the in-plane design.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
