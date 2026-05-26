# D114 — anti-symmetric ordering constraint embedded in optimize_stacking_sequence (Wave AAAAAAAA, v16)

**Status**: Accepted
**Wave**: AAAAAAAA (v16)
**Supersedes**: none (closes D110's reopening; extends D095/D106 `optimize_stacking_sequence`)
**Superseded by**: none

## Context

D110 (v15) added the anti-symmetric laminate as a **standalone construction**
(`make_antisymmetric_laminate` / `is_antisymmetric_laminate`) that zeros the bending–shear
coupling `D₁₆=D₂₆`, and recorded as a reopening criterion:

> *"Embed anti-symmetry into `optimize_stacking_sequence` (a `bending_shear_decoupled`
> flag, analogous to D106's `balanced`)."*

D106 had embedded the *balanced* (extension–shear) constraint into the production stacking
optimiser; D114 does the bending-side analogue, so the optimiser can return a laminate whose
**optimised** stack is bending–shear decoupled — not just a hand-built construction.

## Decision

- **`optimize_stacking_sequence(..., bending_shear_decoupled=False)`** — when `True`, the
  input `ply_angles` is treated as the **bottom half-stack**; the optimiser orders the half
  to maximise `D_11` (rearrangement: stiffest half-ply nearest a surface) and builds the
  full laminate **anti-symmetrically** as `[half, −reversed(half)]`
  (`make_antisymmetric_laminate`) ⟹ `D₁₆=D₂₆=0` **and** `A₁₆=A₂₆=0`.
- **Mutually exclusive** with `symmetric`/`balanced` (anti-symmetry is its own construction
  and already implies balance) — guarded by `stacking_antisym_exclusive`.

**Why the rearrangement is still globally optimal**: `Q̄₁₁` is **even** in `θ`, so each
half-ply `θ_j` contributes `Q̄₁₁(θ_j)` at both its position `j` and the mirror position
`2m−1−j` (which carries `−θ_j`). The position weights `c_k` are symmetric, so `D_11 = Σ_j
2c_j Q̄₁₁(θ_j)`; maximising it places the largest `Q̄₁₁` at the largest `c_j` (the surface)
— the closed-form rearrangement optimum, now *among anti-symmetric orderings*.

## Verification (quantitative anchors)

`tests/test_antisym_embed.py` (6 passed; adjacent regression on `test_balanced_stacking` +
`test_constrained_select` + `test_antisymmetric_laminate` + `test_balanced_laminate` +
`test_stacking_sequence` + `test_periodic_fibre_laminate`, 37 pass):

1. **headline — embedded decoupling**: the optimiser's output with
   `bending_shear_decoupled=True` has `D₁₆=D₂₆=0` (abs 1e-7).
2. **also balanced**: the output has `A₁₆=A₂₆=0` (abs 1e-7).
3. **binding (changes the optimum)**: the plain optimiser on the same inventory keeps
   `|D₁₆|>1e2`; the decoupled output drops it to <1e-7 and the stack genuinely differs
   (anti-symmetry doubles the half).
4. **byte-exact opt-in default**: `bending_shear_decoupled=False` reproduces the no-flag
   (D095/D106) result with exact equality (sequence + objective).
5. **global optimum among anti-symmetric orderings**: the rearrangement `D_11` equals the
   brute-force max over all anti-symmetric orderings of the half-stack (abs 1e-9).
6. **guards**: `bending_shear_decoupled` + `symmetric` and `+ balanced` raise
   `stacking_antisym_exclusive`; empty plies raise `stacking_no_plies`.

## Honest scope notes

- **`max_bending` objective only is closed-form** under anti-symmetry. For `min_coupling`
  the output reports `‖B‖_F` of the rearrangement-ordered anti-symmetric stack (which has
  `B₁₆,B₂₆≠0` by construction — the D110 trade); it is **not** a search for the
  `min_coupling`-optimal anti-symmetric ordering. Anti-symmetry is chosen *for* `D`-shear
  decoupling, so optimising `‖B‖` under it is not the natural pairing; left as a reopening.
- **Trade preserved**: as in D110, `D₁₆=D₂₆=0` and `A₁₆=A₂₆=0` come at the cost of
  `B₁₆,B₂₆≠0`. The optimiser does not (and cannot) remove all coupling simultaneously.
- **Input is the half-stack** (like `symmetric=True`), uniform thickness, angles in radians.
- Mutually exclusive with `symmetric`/`balanced` by design — combining anti-symmetry with
  mirror-symmetry would force all angles onto 0/±π2.

## Reopening criteria

- **`min_coupling` search under anti-symmetry** (order the half to additionally minimise a
  chosen `B` norm subject to the anti-symmetric structure).
- **Per-ply thickness** anti-symmetric optimisation.
- **Joint objective** trading `D`-decoupling against `B₁₆` magnitude.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio optional),
2D/2.5D only, local `pytest -q` (no network), single-line stderr + `SolverError` status
strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM, self-deprecation over
self-promotion.
