# D119 — copula parallel / k-out-of-n system reliability (Wave FFFFFFFF, v16)

**Status**: Accepted
**Wave**: FFFFFFFF (v16)
**Supersedes**: none (closes D111's "parallel / general system events" reopening; extends D098)
**Superseded by**: none

## Context

D098's `system_reliability_series_copula` modelled only the **series** system (safe iff all
safe ⟹ `P_f = 1 − C(u)`). D111 recorded as a reopening:

> *"Parallel / general system events (not only series 'all safe') under a mixture copula."*

Redundant structures fail only when **all** modes fail (parallel), and the general
**k-out-of-m** criterion (fails iff ≥k modes fail) unifies series (k=1) and parallel (k=m).
D119 adds both under an arbitrary dependence copula.

## Decision

- **`_subset_all_fail_prob(u, copula, subset)`** — `P(⋂_{i∈subset} fail)`, the joint
  upper-orthant probability of the safe-copula by inclusion–exclusion
  `Σ_{S⊆subset} (−1)^{|S|} C(w^S)` (`w^S_k = u_k` if `k∈S` else `1`; setting a coordinate to
  1 marginalises `C`, so only `C.cdf` is needed).
- **`system_reliability_parallel_copula(betas, copula)`** — `P_f = P(all fail)` via the
  full-set upper orthant.
- **`system_reliability_k_out_of_n_copula(betas, copula, k)`** — `P(≥k fail)` via the
  Schuette–Nesbitt identity `Σ_{j=k}^{m} (−1)^{j−k} C(j−1,k−1) S_j`, `S_j = Σ_{|T|=j} P(all
  in T fail)`. `k=1` ⟹ series (inclusion–exclusion for the union); `k=m` ⟹ parallel.

## Verification (quantitative anchors)

`tests/test_parallel_copula.py` (6 passed; adjacent regression on
`test_series_copula_reliability` + `test_multi_family_copula` + `test_copula_marginals`,
18 pass):

1. **independence parallel = ∏ P(fail)**: with the independence copula
   `P_f_parallel = ∏_k (1 − Φ(β_k))` (abs 1e-14).
2. **k=1 ≡ series**: `system_reliability_k_out_of_n_copula(…, 1)` equals
   `system_reliability_series_copula` exactly (abs 1e-12).
3. **k=m ≡ parallel**: `k_out_of_n(…, m)` equals `system_reliability_parallel_copula`
   (abs 1e-12).
4. **parallel ≤ series**: `P_f_parallel ≤ P_f_series` for any copula (a parallel system is
   at least as reliable).
5. **monotone in k**: `P(≥k fail)` is non-increasing in `k`, every value in `[0,1]`.
6. **guards**: copula-dim mismatch, no modes, `k ∉ [1,m]` raise `SolverError`.

## Honest scope notes

- **`O(Σ_j C(m,j) 2^j)` copula evaluations** — exact but exponential in `m`; intended for
  the small `m` (≤ ~6) of 2.5-D reliability. No large-`m` approximation (e.g. simulation)
  is provided; that is a reopening.
- **Standard-normal safe-probabilities** `u_k = Φ(β_k)` (the D098 convention). The
  general-marginal path (D115) is a separate function; combining k-out-of-n with general
  marginals is a trivial follow-up but not wired here.
- **`P(≥k fail)` is the exact inclusion–exclusion** of the copula upper orthants — no
  independence or normal-approximation assumption on the dependence (the copula is exact);
  it is exact in arithmetic up to floating-point cancellation in the alternating sum (which
  is benign for the small `m` here, validated by the independence anchor to 1e-14).
- **k-out-of-n on the safe-copula assumes the copula models the *safe*-event dependence**
  (consistent with D098); using a survival copula directly is equivalent and not separately
  exposed.

## Reopening criteria

- **Large-`m` estimator** (Monte-Carlo / lattice) for k-out-of-n when `2^m` is prohibitive.
- **k-out-of-n with general non-normal marginals** (compose with D115).
- **Min-cut / general coherent-structure** system reliability beyond series/parallel/k-of-n.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio optional),
2D/2.5D only, local `pytest -q` (no network), single-line stderr + `SolverError` status
strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM, self-deprecation over
self-promotion.
