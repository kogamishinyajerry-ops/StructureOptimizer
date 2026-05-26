# D110 — anti-symmetric laminate bending-shear decoupling D₁₆=D₂₆=0 (Wave EEEEEEE, v15)

**Status**: Accepted
**Wave**: EEEEEEE (v15)
**Supersedes**: none (closes D101's reopening, extends D087 laminate_abd / D101 balanced)
**Superseded by**: none

## Context

D101 (v14) zeroed the *extensional* shear coupling `A₁₆=A₂₆` (balanced laminates) and
recorded as a reopening criterion:

> *"D₁₆/D₂₆ bending-shear decoupling (anti-symmetric or specially-ordered stacks) for
> full shear decoupling, not just A₁₆/A₂₆."*

A symmetric-balanced stack decouples extension–shear (`A₁₆=A₂₆=0`) and extension–bending
(`B=0`) but **not** bending–shear (`D₁₆,D₂₆ ≠ 0`). D110 adds the anti-symmetric
construction that zeros `D₁₆=D₂₆`.

## Decision

- **`make_antisymmetric_laminate(angles)`** — builds the **anti-symmetric** stack
  `θ(−z) = −θ(+z)` as `[half, −reversed(half)]` (radians).
- **`is_antisymmetric_laminate(angles, tol=1e-9)`** — True iff `θ_k ≡ −θ_{n-1-k}` (mod π)
  for every mirror pair (odd counts never anti-symmetric).
- **`_angle_eq_mod_pi`** — period-π angle equality helper.

**Why it decouples bending–shear**: in `D = Σ Q̄_k·(z_k³−z_{k-1}³)/3`, mirror plies span
`[z1,z2]` and `[−z2,−z1]` which share the **same** positive `z³` weight; carrying `±θ`,
their **odd** `Q̄₁₆/Q̄₂₆` cancel ⟹ `D₁₆=D₂₆=0`. The same odd-cancellation in the
order-independent `A` gives `A₁₆=A₂₆=0` (anti-symmetric is also balanced). The `z²`
weight in `B` is *anti*-symmetric across the mid-plane, so the even terms cancel
(`B₁₁=B₁₂=B₂₂=0`) but the odd `Q̄₁₆/Q̄₂₆` reinforce (`B₁₆,B₂₆ ≠ 0`).

## Verification (quantitative anchors)

`tests/test_antisymmetric_laminate.py` (6 passed; adjacent regression on
`test_balanced_laminate` + `test_balanced_stacking` + `test_constrained_select` +
`test_periodic_fibre_laminate`, 25 pass):

1. **headline — bending-shear decoupling**: anti-symmetric `[30,60,−60,−30]` has
   `D₁₆=D₂₆=0` (abs 1e-7).
2. **also balanced**: anti-symmetric `[15,45,75,...]` has `A₁₆=A₂₆=0` (abs 1e-7).
3. **contrast (necessity)**: the symmetric-balanced stack (D101) keeps `|D₁₆|,|D₂₆|>1e2`
   — symmetry+balance alone cannot decouple bending-shear.
4. **coupling signature**: anti-symmetry zeros `B₁₁=B₁₂=B₂₂=0` but keeps `|B₁₆|>1e2`
   (the classical anti-symmetric trade: B-coupling for D-decoupling).
5. **detection**: `is_antisymmetric_laminate` True for constructed anti-symmetric and for
   `[30,−30]`, False for symmetric-balanced and odd counts.
6. **guards**: empty plies raise `SolverError`.

## Honest scope notes

- **Anti-symmetry trades coupling, it does not remove all of it.** `D₁₆=D₂₆=0` and
  `A₁₆=A₂₆=0` are achieved **at the cost of `B₁₆,B₂₆ ≠ 0`** (extension–shear/bending
  coupling). There is no single stack that zeros A-shear, B, *and* D-shear simultaneously
  for arbitrary off-axis angles — anti-symmetric (D-decoupled, B≠0) and symmetric-balanced
  (B=0, D-coupled) are the two complementary choices. I state this explicitly rather than
  implying anti-symmetry is strictly better.
- **Construction + verification, not an optimiser constraint.** Like D101, this provides
  `make_*`/`is_*`; embedding anti-symmetry into `optimize_stacking_sequence` (analogous to
  D106) is a natural follow-up, not done here.
- **Angles in radians**, uniform thickness assumed in the constructor.
- **`Q̄₁₆/Q̄₂₆` odd-in-θ** is the CLT identity the decoupling rests on (same basis as
  D101); validated numerically, not re-derived symbolically.

## Reopening criteria

- **Embed anti-symmetry into `optimize_stacking_sequence`** (a `bending_shear_decoupled`
  flag, analogous to D106's `balanced`).
- **Per-ply thickness** anti-symmetry.
- **Joint objective** trading B₁₆ magnitude against D-decoupling.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
