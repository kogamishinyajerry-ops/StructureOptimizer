# D042 — reliability-based topology optimization (Wave MM)

**Status**: Accepted
**Wave**: MM (v7)
**Supersedes**: none (wires D038's FORM into a SIMP driver)
**Superseded by**: none

## Context

v6 Wave II (D038) delivered FORM/SORM as a forward reliability evaluator and
explicitly named "a reliability-based TO driver" as its reopening criterion. v7
opens with that driver — the first of v7's "forward solver → design driver"
upgrades.

## Decision

Add `core/rbto.py`:

- Reliability model: the load magnitude carries a multiplicative factor
  `s ~ N(1, load_cov)`. Linear-elastic displacement scales linearly with load,
  so the displacement limit state `g(s) = d_allow − s·d_nominal` is **linear**
  in `s`; in standard-normal space `g(u) = (d_allow − d_nominal) −
  load_cov·d_nominal·u`. FORM is therefore exact:
  `β = (d_allow − d_nominal)/(load_cov·d_nominal)`, `P_f = Φ(−β)`.
- `displacement_limit_state(d_nominal, d_allow, load_cov)` → the U-space callable.
- `displacement_reliability(...)` → runs `form_hlrf` (D038) on it, returning a
  `ReliabilityResult` (this is the FORM-into-driver wiring).
- `reliability_tightened_volume_floor(load_cov, beta_target)` → closed-form
  displacement-ratio bound `1/(1+βσ)` (analytical sanity).
- `rbto_simp(config, mesh, d_allow, beta_target, load_cov, ...)` → because the
  min-compliance topology is invariant under uniform load scaling, the
  reliability knob is the **volume fraction** (more material → lower d_nominal →
  higher β). Bisects vf for the lightest min-compliance design meeting
  β ≥ β_target; returns `RBTOResult` with the achieved β, the selected vf, a
  `feasible` flag, and the SIMP-solve count.

## Verification (quantitative)

- **FORM == closed form** (`test_form_reliability_matches_closed_form`): the
  FORM β reproduces `(d_allow−d_nom)/(cov·d_nom)` to ≤1e-7 and `P_f = Φ(−β)` to
  ≤1e-9 — the analytical anchor.
- **Monotonicity** (`test_reliability_monotone_in_margin_and_cov`): β rises with
  margin, falls with cov; **origin-unsafe** (`..._nominal_exceeds_allowable`):
  d_nom > d_allow → β < 0, P_f > 0.5.
- **RBTO meets target + needs more material**
  (`test_rbto_higher_target_needs_more_volume`): a more demanding β_target
  selects ≥ the volume fraction of a looser one, both achieving β ≥ target —
  the RBTO-vs-deterministic difference, quantified.
- **Infeasibility** flagged when the target is unreachable in-bracket; **trivial
  target** met at the lightest vf; contract errors. 9 tests, all green. Adjacent
  `test_solver_adapter` + `test_form_sorm` (21) unchanged.

## Honest scope notes

- Uncertainty is a single load-magnitude factor (one standard-normal variable).
  Multiple/correlated random variables are out of scope here (Wave PP adds the
  Nataf transform for correlated Gaussians).
- The reliability constraint is on **displacement** (linear in load → FORM
  exact). A compliance limit state (∝ load²) would be nonlinear and need the
  full HL-RF iteration; the driver already calls `form_hlrf`, so it generalises,
  but the analytical anchor uses the linear displacement case.
- RBTO searches over a single scalar (volume fraction) via bisection, assuming
  β is monotone in vf (true for min-compliance designs in practice). A general
  RBTO over the full density field is a larger, separate effort.

## Reopening criteria

- Correlated / non-Gaussian load + material uncertainty → Wave PP (Nataf).
- Compliance- or stress-based reliability limit states → add the nonlinear
  limit-state path (form_hlrf already supports it).

## Red lines

numpy-only, 2D, single-line stderr — all held. `run_simp` and `form_hlrf`
reused unchanged.
