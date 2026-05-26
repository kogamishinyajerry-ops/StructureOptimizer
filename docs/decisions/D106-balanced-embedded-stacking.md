# D106 — balanced constraint embedded in optimize_stacking_sequence (Wave AAAAAAA, v15)

**Status**: Accepted
**Wave**: AAAAAAA (v15)
**Supersedes**: none (closes D101's reopening, embeds into D095 optimiser)
**Superseded by**: none

## Context

D101 (v14) added `make_balanced_laminate` / `is_balanced_laminate` as **standalone**
construction+verification helpers and recorded as a reopening criterion:

> *"Wire `balanced=True` into `optimize_stacking_sequence` so the ordering / selection
> search is restricted to balanced (and symmetric-balanced) layups."*

v14 left balance as a thing you check *after* building a stack; D106 embeds it *inside*
the production stacking optimiser so the optimiser's output is balanced by construction.

## Decision

- **`optimize_stacking_sequence(..., balanced: bool = False)`** (D095 optimiser). When
  `True`, the input `ply_angles` is first replaced by its **+θ/−θ paired multiset**
  (`_balanced_stacking_inventory` → `make_balanced_laminate(symmetric=False)`); the
  existing objective ordering (`max_bending` rearrangement / `min_coupling` brute force)
  then proceeds on that multiset.

- **Why the embedding is sound**: the extensional `A = Σ Q̄_k t_k` is
  **order-independent** and `Q̄₁₆/Q̄₂₆` are odd in θ, so a +θ/−θ paired multiset has
  `A₁₆ = A₂₆ = 0` for **any** ordering. The optimiser is therefore free to reorder it for
  the objective without ever breaking balance — and with `symmetric=True` the mirror
  additionally gives `B = 0` (a **symmetric-balanced** output).

- **`_balanced_stacking_inventory(angles)`** — the helper carrying the `balanced_stacking`
  embedding.

## Verification (quantitative anchors)

`tests/test_balanced_stacking.py` (6 passed; adjacent regression on `test_stacking_sequence`
+ `test_balanced_laminate` + `test_angle_selection`, 18 pass). Proves the embedded
constraint **truly binds** (v15 discipline):

1. **feasible**: `balanced=True` on `[30°,60°]` ⟹ `A₁₆=A₂₆=0` (abs 1e-7); the inventory
   is the +θ/−θ paired multiset.
2. **changes the design**: `balanced=False` on the same angles has `|A₁₆|>1e3` (raw
   inventory unbalanced) and a different (un-paired) sequence — the constraint binds.
3. **symmetric-balanced**: `symmetric=True`+`balanced=True` ⟹ `A₁₆=A₂₆=0` **and**
   `‖B‖<1e-7`, mirror-symmetric sequence.
4. **byte-exact default (integration铁律)**: `balanced=False` reproduces the D095 default
   path byte-for-byte (`np.array_equal` on sequence/A/B/D, `==` on objective).
5. **order-independent**: balance holds under both `max_bending` and `min_coupling`
   (cross-checked against an independent `laminate_abd` on the paired multiset).
6. **guard**: pairing doubles the inventory, so `min_coupling`'s `n≤8` brute-force guard
   still fires (`stacking_min_coupling_too_many_plies`).

## Honest scope notes

- **Balance is achieved by *construction*, not by a *search restriction*.** Because `A`
  is order-independent, there is no ordering search to restrict — the embedding replaces
  the inventory with a balanced multiset and the objective ordering is over that. This is
  the honest reading of "restrict to balanced layups": the optimiser's feasible set *is*
  the balanced multiset's orderings.
- **`balanced=True` changes the ply count** (each non-self-balanced angle is doubled).
  The input is interpreted as the set of distinct angles to balance (typically the
  positive representatives); passing an already-paired inventory would double again.
- **A₁₆/A₂₆ only** — not D₁₆/D₂₆ (bending–shear); full bending–shear decoupling is
  Wave EEEEEE (D110, anti-symmetric stacks).
- **Angles in radians**; `make_balanced_laminate` does not convert.
- **min_coupling brute force** still capped at the paired-multiset size ≤ 8.

## Reopening criteria

- **Per-ply thickness** in the balanced multiset (currently uniform `thickness`).
- **Balanced + discrete angle *selection*** (which angles to balance, not just order) —
  Wave CCCCCCC (D108).
- **Joint balanced + min-D₁₆** objective (couple D106 with D110).

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
