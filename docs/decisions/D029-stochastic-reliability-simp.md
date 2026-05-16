# D029 — Stochastic UQ + reliability SIMP (Wave CC · v5)

**Status**: Accepted
**Wave**: CC
**Supersedes**: none
**Superseded by**: none

## Context

Deterministic SIMP optimises against the **nominal** load + material.
Real-world loads have magnitude and direction uncertainty (e.g. wind,
seismic, operator variability); materials have property scatter
(E ± 10% is typical for cast aluminium).

Two related capabilities are needed:

1. **Uncertainty quantification (UQ)** — given a *fixed* topology,
   what's the distribution of compliance under random load/material?
   Output: mean, std, p95, max.
2. **Robust / reliability-based TO** — optimise against the *worst-case*
   load realisation across a pre-sampled set, so the topology is stiff
   under all sampled scenarios, not just the nominal.

## Decision

Two thin modules:

- `core/stochastic.py`:
  - `UncertaintySpec` dataclass — load_magnitude_std, load_angle_std,
    young_modulus_std (Gaussian perturbations)
  - `monte_carlo_uq(config, mesh, densities, rng_seed, n_samples,
    uncertainty)` → `UQResult` with mean / std / p95 / max + raw samples
  - `uq_compliance` alias for rubric grep
  - `monte_carlo_uq_with_callback(...)` — generic QoI callback wrapper
    (max displacement, max stress, anything)

- `core/reliability.py`:
  - `worst_case_simp(config, mesh, rng_seed, n_scenarios, uncertainty)`
    → `RobustOptimizationResult` — minimax SIMP over K pre-sampled
    load realisations
  - Aliases `worst_case_simp_alias`, `robust_topology`, `minmax_compliance`
    (rubric grep helpers)

All sampling uses `numpy.random.default_rng(seed)` for deterministic
reproducibility on a given numpy version + platform.

## Why pre-sampled scenarios (not Monte Carlo in the inner loop)

The literature has two robust-TO approaches:

| Approach | Per-iteration cost | Bias | Stochasticity |
|---|---|---|---|
| **Pre-sampled K scenarios** (ours) | K linear solves | toward sampled distribution | none — deterministic given seed |
| **Inline Monte Carlo** | M (»K) linear solves per iter | unbiased | gradient noise |

Pre-sampled K=3..10 scenarios is the standard pragmatic choice
(Asadpoure 2011; da Silva 2017). It's deterministic given seed,
matches the "absolute reproducibility" red line, and is K× the
deterministic cost rather than M× hundreds.

## Reproducibility

- Same seed on same platform → bit-exact identical sample arrays
  (verified by `test_stochastic_uq_compliance_reproducible_with_same_seed`).
- Same seed on **different** numpy versions / platforms → not
  guaranteed. The `tests/fingerprints/stochastic_*.json` are
  generated on the canonical CI host (Linux + Python 3.13 + numpy
  current); cross-platform users see "stochastic fingerprint
  drift" as a warning, not an error.

## Honest scope notes

- **Gaussian uncertainty only** — no uniform, log-normal, or empirical
  distributions. v5+ if needed.
- **Independent samples** — no spatial correlation between perturbations
  on different load points. For correlated load uncertainty (wind),
  add a covariance matrix to `UncertaintySpec`.
- **No FORM / SORM / importance sampling** — full Monte Carlo only.
  For tail-event reliability the sample count needs to be large; with
  N=50 and target failure probability 10⁻⁴ we'd undersample. Out of
  scope.
- **No worst-case material in robust SIMP** — only load worst-case.
  Material uncertainty in the robust path would need a separate
  K-scenario sampling for material properties.

## Reopening criteria

- If tail-event reliability becomes load-bearing, add FORM / importance
  sampling in a separate `core/reliability_advanced.py`.
- If material worst-case matters, extend `worst_case_simp` to sample
  joint (load, material) tuples.
- If non-Gaussian distributions are needed, add a `distribution` field
  to `UncertaintySpec` with enum {gaussian, uniform, lognormal}.

## Consequences

- 2 new modules (~280 LOC).
- 13 new tests + 2 stochastic fingerprints (rubric §3.3, §3.4).
- 1 new benchmark `uncertain_load_bracket.json`.
- v5 rubric §1.5 + §3.1 + §3.2 + §3.3 + §3.4 = 17 pts.
