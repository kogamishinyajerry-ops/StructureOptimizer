# D075 — adaptive band sampling + peak-as-constraint (Wave TTT, v11)

**Status**: Accepted
**Wave**: TTT (v11)
**Supersedes**: none (extends D067)
**Superseded by**: none

## Context

D067 (`target_band_placement`) suppressed the worst-case forced response over a
target frequency band, but with two recorded limitations that became its
reopening criteria:

> *"…samples a **fixed** ω-grid…"* and the peak was the **objective** of a
> projected-gradient descent. Reopening: **adaptive band sampling; peak-as-constraint**.

Both bite in practice. A forced-response resonance is **sharp** (narrow in ω):
sampling a fixed coarse grid can land entirely *between* samples, so the
optimiser "minimises" a peak it never measured — the reported peak underestimates
the true band maximum. And expressing the peak only as an objective cannot pose
the common engineering requirement *"minimise something else (compliance,
material) while keeping the in-band response bounded"*. v11 Wave TTT cashes in
both.

## Decision

- **`freq_response._dynamic_compliance_objective(config, mesh, densities, omega,
  alpha=0, beta=0, mass_type)`** — a forward-only `J = |fᵀû|²` (the same complex
  dynamic-stiffness solve as `dynamic_compliance_sensitivity` but **without** the
  per-element adjoint loop), so the sampler can evaluate many frequencies cheaply.

- **`freq_response.adaptive_band_sample(config, mesh, densities, omega_lo,
  omega_hi, n_init=5, n_refine=10, alpha=0, beta=0, mass_type) → AdaptiveBandResult`**
  — starts from `n_init` uniform samples, then does `n_refine` **bisection-toward-
  the-peak** steps: each step bisects the sub-interval adjacent to the current
  peak sample whose endpoints have the larger summed response. This concentrates
  evaluations at the resonance. Returns sorted `omegas`/`values` + `peak_value`/
  `peak_omega` + `n_evals`.

- **`freq_response.peak_constrained_mma(config, mesh, peak_limit, band_omegas,
  alpha=0, beta=1e-4, vf=None, max_iter=40, change_tol=1e-3, p=12, mass_type) →
  PeakConstrainedTOResult`** — minimise **static compliance** subject to **two**
  MMA inequalities:

      g₁(x) = J_peak(x)/J_lim − 1 ≤ 0   (in-band forced-response peak)
      g₂(x) = mean(x) − vf ≤ 0          (volume)

  reusing the proven D066 two-constraint MMA structure with the smooth p-norm
  band-peak sensitivity (`target_band_peak_sensitivity`) swapped in for the
  stress. Objective gradient = the standard SIMP compliance sensitivity; both
  gradients density-filtered.

- **`tests/test_adaptive_band_peak.py`** — five quantitative anchors (below).

## Verification (quantitative anchors)

`tests/test_adaptive_band_peak.py` (5 passed; adjacent regression on
test_target_band_placement / test_frequency_response / test_dynamic_compliance /
test_band_gap / test_modal below):

1. **adaptive captures a sharp resonance a coarse uniform grid misses**: over a
   β-damped band `[0.80·ω₁, 1.30·ω₁]`, adaptive sampling (7 init + 18 refine = 25
   evals) recovers the dense-400-reference peak to ≤ 2 % (measured 0.015 %),
   while the equal-size **uniform-7** grid underestimates the peak by ≥ 20 %
   (measured ≈ 41 %). Adaptive captures ≥ 1.2× the uniform peak.
2. **adaptive concentrates evaluations at the peak**: the nearest refined sample
   to the located `peak_omega` is < 1/8 of the initial uniform spacing; samples
   stay sorted and in-band.
3. **invalid range / too-few-initial raise** `SolverError`.
4. **peak-as-constraint MMA binds**: with `J_lim = 0.6·`(the min-compliance
   `run_simp` design's band peak), the peak is driven from the uniform start down
   onto the limit (final ≤ J_lim·1.05, and < 0.5× the start) while volume stays
   ≤ vf+0.02. Probe: peak 3.99e5 → 2.23e4 ≤ limit 2.14e4, volume held 0.450.
5. **contract + determinism**: histories aligned, `peak_limit` echoed, two runs
   identical, non-positive limit raises.

## Honest scope notes

- **Damping is required for a well-posed peak.** At exactly an undamped natural
  frequency the dynamic stiffness `D = K − ω²M` is singular and `J → ∞` (a probe
  with `β = 0` and a band symmetric about ω₁ returned `J ≈ 4e30` — the resonance
  singularity, not a physical peak). The sampler and the constraint therefore use
  a small Rayleigh stiffness damping `β` (tests use `β = 2e-6` for sampling,
  `1e-4` for the MMA). The "peak" is the **damped** forced-response maximum.
- **The peak constraint must be a band, not a single frequency.** A single-ω
  constraint is trivially gamed by *detuning* — the optimiser shifts the
  resonance off the one sampled frequency while the true peak rises elsewhere. An
  earlier min-volume-objective formulation with a single-ω constraint collapsed
  to minimum density (volume 0.45 → 0.01) with the real peak exploding to ~2.6e9.
  The shipped driver therefore (a) aggregates a **multi-frequency band** p-norm
  peak and (b) **minimises compliance with volume held as its own constraint**
  (not min-volume), which keeps the design from collapsing. This is the honest
  reason the objective is compliance, not material.
- The adaptive scheme is a **greedy bisection toward the current peak**, not a
  certified global band-max finder: a band with two comparable resonances could
  leave the secondary one under-resolved. For a single dominant in-band resonance
  (the design-relevant case) it is accurate; multi-modal certified sampling is a
  reopening item.
- `adaptive_band_sample` uses the forward-only objective, but
  `peak_constrained_mma` evaluates the band peak **on a fixed `band_omegas`** each
  iteration (it does not re-adapt the grid inside the optimisation loop) — coupling
  in-loop re-adaption is a reopening item.
- Static compliance objective (not the full forced-response compliance) keeps the
  objective cheap; the dynamic content enters only through the constraint.

## Reopening criteria

- **In-loop adaptive re-gridding**: re-run `adaptive_band_sample` each MMA
  iteration so the constraint always tracks the (moving) resonance, instead of a
  fixed `band_omegas`.
- **Multi-modal certified sampling**: refine all in-band resonances (bisect every
  interval whose response exceeds a fraction of the running max), with an error
  bound on the recovered peak.
- **Forced-response (dynamic) compliance objective** combined with the peak
  constraint, instead of static compliance.
- **Min-material with a robust band constraint**: revisit the min-volume objective
  once the band constraint is robust enough to prevent detuning-collapse (e.g.
  with in-loop re-gridding), for genuine least-material resonance-safe designs.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
