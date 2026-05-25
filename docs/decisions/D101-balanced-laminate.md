# D101 — balanced laminate constraint (A₁₆ = A₂₆ = 0) (Wave DDDDDD, v14)

**Status**: Accepted
**Wave**: DDDDDD (v14)
**Supersedes**: none (extends D087 laminate_abd + D095 stacking sequence)
**Superseded by**: none

## Context

D095 (v13 Wave FFFFF) added stacking-sequence optimisation with a *symmetric* (B=0)
constraint and recorded:

> *"Balanced-laminate constraint (+θ/−θ pairs ⟹ A₁₆ = A₂₆ = 0) alongside the symmetric
> B = 0 constraint."*

A *symmetric* laminate decouples extension from bending (B=0). A *balanced* laminate —
every `+θ` ply matched by a `−θ` ply — decouples extension from **shear** (A₁₆=A₂₆=0).
The workhorse decoupled layup is **symmetric-balanced** (both). D095 had symmetry; this
wave adds balance.

## Decision

- **`orthotropic_simp.make_balanced_laminate(angles, symmetric=True)`** — builds a
  balanced (each `+θ` paired with `−θ`) and, by default, symmetric (mirrored) stack
  from distinct lamina angles (**radians**). `0`/`±π/2` plies are self-balanced (their
  `Q̄₁₆ = Q̄₂₆ = 0`) and not duplicated.

- **`orthotropic_simp.is_balanced_laminate(angles, thicknesses=None, tol=1e-9)`** — a
  geometric (angles-only) test: accumulate **signed** thickness per acute magnitude
  `|θ|` (`+θ` adds, `−θ` subtracts); balanced iff every net is zero. Thickness-weighted,
  so unequal `+θ`/`−θ` thickness is correctly *not* balanced.

- **`orthotropic_simp._is_self_balanced_angle(θ)`** — helper: `0`/`±π/2` (mod π).

- **`tests/test_balanced_laminate.py`** — six anchors.

## Verification (quantitative anchors)

`tests/test_balanced_laminate.py` (6 passed; adjacent regression on
`test_stacking_sequence` + `test_periodic_fibre_laminate` + `test_orthotropic_simultaneous`,
19 pass):

1. **balanced ⟹ A₁₆=A₂₆=0**: a balanced [+30,−30,+60,−60] stack has A₁₆, A₂₆ = 0 to
   abs 1e-7 (the odd-in-θ `Q̄₁₆`/`Q̄₂₆` cancel).
2. **symmetric-balanced ⟹ both zero**: A₁₆=A₂₆=0 (balance) **and** ‖B‖<1e-7 (symmetry,
   D087) simultaneously; the constructed stack is mirror-symmetric.
3. **unbalanced contrast**: [+45,+45] has |A₁₆|,|A₂₆| > 1e3 and `is_balanced_laminate`
   returns False.
4. **detection + self-balance**: True for ±θ pairs and for [0, π/2] (both
   self-balanced); False for a lone +45.
5. **thickness-weighted**: [+45,−45] with equal thickness is balanced; with thickness
   [2,1] it is *not* (and that stack indeed has A₁₆ ≠ 0).
6. **guards**: empty-plies / thickness-count-mismatch raise single-string `SolverError`.

## Honest scope notes

- **Construction + verification, not yet an *optimiser* constraint.** This wave gives
  `make_balanced_laminate` (build a balanced stack) and `is_balanced_laminate` (check
  one). Wiring the balanced constraint *into* `optimize_stacking_sequence` (so the
  ordering search only considers balanced arrangements) is a natural next step, not done
  here — `optimize_stacking_sequence` (D095) is unchanged.
- **Angles in radians.** Consistent with `rotate_plane_stress`/`laminate_abd`; callers
  passing degrees get physically-wrong couplings (the functions do not convert). The
  tests use `np.deg2rad` explicitly. (D095's stacking optimiser is unit-agnostic for
  *ordering*, but the balance/coupling physics here needs the radian convention.)
- **A₁₆/A₂₆ only.** Balance zeros the *extensional* shear coupling. It does **not** zero
  the *bending* shear coupling D₁₆/D₂₆ — a symmetric-balanced laminate generally still
  has D₁₆,D₂₆ ≠ 0 (those need an anti-symmetric or special stack). I do not claim full
  shear decoupling, only A₁₆=A₂₆=0.
- **Uniform thickness in the constructor.** `make_balanced_laminate` returns angles
  only; per-ply thickness is the caller's (and `is_balanced_laminate` takes it). Equal
  thickness is assumed when building.

## Reopening criteria

- **Wire `balanced=True` into `optimize_stacking_sequence`** so the ordering / selection
  search is restricted to balanced (and symmetric-balanced) layups.
- **D₁₆/D₂₆ bending-shear decoupling** (anti-symmetric or specially-ordered stacks) for
  full shear decoupling, not just A₁₆/A₂₆.
- **Balance under per-ply thickness optimisation** (currently the constructor assumes
  uniform thickness).

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
