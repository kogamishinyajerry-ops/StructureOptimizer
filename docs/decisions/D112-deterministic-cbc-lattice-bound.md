# D112 — deterministic CBC-lattice worst-case error bound (Wave GGGGGGG, v15)

**Status**: Accepted
**Wave**: GGGGGGG (v15)
**Supersedes**: none (closes D099's "CBC-certified lattice deterministic error bound" reopening)
**Superseded by**: none

## Context

Wave GGGGGGG offered three options (blueprint): **multi-apex** concentric-shell refinement,
a **deterministic QMC bound**, or an **honest defer**. I probed the geometry path first and
took the QMC path because:

- **The realistic multi-apex case is already handled by D107.** A cross-section with
  *multiple separate* small-angle apexes (e.g. left + right acute spikes) refines to a
  **watertight** STL under `concentric_shells=True` while plain midpoint refine raises
  `ruppert_not_watertight` (probe: a two-spike section → `is_watertight=True, n_tri=28`).
  `_small_angle_apexes` already returns the full *set* and the per-apex shell rule fires for
  each apex independently. The only theoretically-unhandled case — a single constraint edge
  whose *both* endpoints are acute apexes — I could not construct as a valid simple polygon
  (two acute corners sharing an edge is a degenerate "anti-needle"). Fixing code against an
  inconstructible failing case would be speculative, so I leave that residual as a reopening
  rather than fake a test for it.
- **The QMC bound is a genuine, rigorous, pure-numpy contribution** that directly closes
  D099's reopening and certifies lattice quality *deterministically* (no randomisation),
  complementing `genz_mvn_cdf_lattice`'s *statistical* `std_error`.

## Decision

Add the deterministic weighted-Korobov (smoothness α=1) worst-case error machinery to
`reliability.py` (pure additions; no existing function modified):

- **`korobov_worst_case_error(z, n_points, weights)`** — the deterministic certificate
  `e(z)` of the rank-1 lattice rule, via the exact O(N·d) spatial form

      e²(z) = −1 + (1/N) Σ_{k=0}^{N−1} Π_j (1 + γ_j ω(frac(k z_j/N))),   ω(x)=2π²B₂({x}).

  For **every** `f` in the unit ball of the space, `|Q_N(f) − ∫f| ≤ e(z)·‖f‖`
  (Koksma–Hlawka / RKHS inequality). No RNG, no seed → byte-exact reproducible.
- **`cbc_korobov_generating_vector(dim, n_points, weights)`** — component-by-component
  (Sloan–Reztsov) construction greedily minimising `e(z)`; deterministic, and `e(z_CBC)`
  is **≤** the textbook Korobov `(1,a,…,aᵈ⁻¹)` bound for the same `N`.
- **`_korobov_kernel_omega`** — the shift-invariant kernel piece `ω(x)=2π²B₂({x})`.

## Verification (quantitative anchors)

`tests/test_deterministic_qmc.py` (6 passed; adjacent regression on `test_genz_mvn_system`
+ `test_series_copula_reliability` + `test_multi_family_copula`, 17 pass):

1. **headline — two formulas agree**: the O(N) lattice *spatial* `e²` equals the O(N²)
   *general RKHS double-sum* `e²` to machine precision (abs 1e-12), and `e²≥0`. This
   anchors the spatial formula's correctness against the definition.
2. **binding (CBC changes & improves)**: the CBC vector ≠ the Korobov vector and gives
   `e(z_CBC) ≤ e(z_Korobov)` (greedy optimality); CBC is deterministic (byte-exact on
   repeat — no RNG). Probe: CBC `[1,34,25]` `e=0.2034` < Korobov `e=0.2225`.
3. **deterministic Koksma–Hlawka bound holds**: for `f = K(·,t)` (integral 1, norm
   `√K(t,t)`) the quadrature error obeys `|Q_N f − 1| ≤ e(z)·‖f‖` for every anchor `t` —
   the certificate in action, with no randomness.
4. **convergence**: refining `N` (CBC each) lowers `e` monotonically (31→257), a
   deterministic `O(N^{−1+δ})` decay (not a noisy MC trend).
5. **degenerate sanity**: all-zero weights ⟹ only constants in the space ⟹ exact lattice
   integration ⟹ `e(z)=0` (abs 1e-12).
6. **guards**: too-few points, z/weights mismatch, negative weight, CBC dim<1, CBC
   weights mismatch all raise `SolverError`.

## Honest scope notes

- **A deterministic *bound*, not a new estimator.** D112 *certifies* a lattice rule's
  worst-case quality; it does not replace `genz_mvn_cdf_lattice`'s production estimate.
  Wiring the CBC vector into the Genz estimator (it uses a single-`a` Korobov vector, a
  *different* vector family from a general CBC `z`) is a reopening, not done here.
- **Weighted Korobov space, smoothness α=1 only.** The bound is for product-weighted
  first-order spaces (the `B₂` kernel). Higher smoothness (α≥2, `B_{2α}` kernels) and
  general (non-product) weights are out of scope.
- **Naive O(d·N²) CBC.** Correct and clear, not the fast-CBC FFT O(d·N·log N). Tests use
  modest prime `N` (≤257). Primality is recommended (best theory) but **not enforced** —
  the formula is valid for any `N≥2`; the guarantee quality just degrades for composite `N`.
- **Multi-apex geometry residual deferred** (see Context): the both-endpoints-apex edge is
  inconstructible as a simple polygon in my probes, so it is left as a reopening with
  evidence rather than patched speculatively.
- The worst-case error formula is the standard QMC-theory result (Sloan–Kuo–Joe);
  validated numerically (two equivalent forms agree to 1e-12), not re-derived symbolically.

## Reopening criteria

- **Wire the CBC `z` into `genz_mvn_cdf_lattice`** as an optional deterministic generating
  vector (replacing the single-`a` Korobov vector), reporting `e(z)` alongside the estimate.
- **Fast-CBC** (FFT, O(d·N·log N)) for large `N`; higher smoothness α≥2.
- **Both-endpoints-apex** concentric-shell handling, once a valid failing simple-polygon
  section is constructed.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio optional),
2D/2.5D only, local `pytest -q` (no network), single-line stderr + `SolverError` status
strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM, self-deprecation over
self-promotion.
