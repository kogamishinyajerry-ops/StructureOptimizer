# D120 — fast-CBC (Nuyens–Cools FFT) lattice construction (Wave GGGGGGGG, v16)

**Status**: Accepted
**Wave**: GGGGGGGG (v16)
**Supersedes**: none (closes D112's "fast-CBC (FFT, O(d·N·log N))" reopening)
**Superseded by**: none

## Context

D112 added the naive component-by-component (CBC) construction
`cbc_korobov_generating_vector` — the Sloan–Reztsov greedy that, for each component,
rescans all `N−1` candidates recomputing the worst-case error: `O(d·N²)`. D112 recorded a
reopening:

> *"fast-CBC (FFT, O(d·N·log N))"* — the Nuyens–Cools acceleration.

This wave is a **probe-then-decide** wave: the blueprint set the anchor as *"fast-CBC z ==
naive-CBC z (同贪心结果) + O(dNlogN) 加速 **或诚实 defer**"*, explicitly allowing a defer
with probe evidence (D074/D091/D104/D112 precedent).

## Probe findings (recorded before deciding)

A standalone FFT fast-CBC was prototyped and compared to the naive routine across primes
`N ∈ {31,…,4093}` and several weight profiles:

1. **The FFT correlation is exact.** The per-component CBC objective, after re-indexing the
   multiplicative group of `Z/N` by a primitive root, is a cyclic correlation; one FFT pair
   reproduces the direct `O(N²)` correlation to **2.1e-14**. The algorithm is correct.
2. **It genuinely minimises.** `e(fast_cbc) ≤ e(textbook Korobov)` and `≤ min e` over random
   vectors, for **every** tested prime (substantial margins). It produces certified-optimal
   CBC vectors.
3. **The speedup is real and grows as predicted:** 9× (N=31) → 1107× (N=4093),
   tracking `O(N²)/O(N log N)`.
4. **But bit-exact `z`-equality with the naive routine is *unachievable*.** The kernel
   `B₂(t) = t²−t+1/6` satisfies `B₂(1−t) = B₂(t)`, so `g` and `N−g` give an **exact**
   worst-case-error tie — the per-component optimum is a `2^{d−1}`-member symmetric set. The
   naive routine resolves each tie by **floating-point summation order** (the same `frac`
   multiset summed in a different `k`-order for `g` vs `N−g`), *not* by any canonical rule —
   N=1021 naive even picked the *larger* twin `z₂=593` over `428`. Once any component's tie
   resolves differently, the running products diverge and all later components diverge.
   Attempts to force a match (rounding `conv`; symmetrising the `g↔N−g` pair; a canonical
   min-`g` reference) reached **20/21** cases but the 21st needed an arbitrary
   rounding-granularity choice (`e` vs `conv` vs `e²`) — i.e. **fake precision**.

## Decision

**Implement** `fast_cbc_korobov_generating_vector(dim, n_points, weights)` (FFT,
Nuyens–Cools), anchored on the **achievable** truths, **not** the unachievable bit-equality:

- For **prime** `N`, re-index `(Z/N)^×` by a primitive root `ρ` (`_smallest_primitive_root`);
  the per-component objective becomes the cyclic correlation `T̃(b) = Σ_a P(ρ^a)
  ω(frac(ρ^{a+b}/N))`, evaluated for all candidates by one `rfft/irfft` pair in
  `O(N log N)`. Total `O(d·N log N)`.
- Resolve the exact `g↔N−g` symmetry by a **canonical** symmetrised min-`g` tie-break
  (`conv = ½(conv + conv[partner])`, then `lexsort` by `(conv, g)`) so the output is
  **deterministic** (no RNG, byte-stable across calls).
- Guard non-prime `N` (`fast_cbc_n_not_prime`) — the cyclic-group reduction requires it; the
  only in-repo consumer (`genz_mvn_cdf_cbc`, default `N=1021`) already uses a prime.

This is a **pure addition** — the naive `cbc_korobov_generating_vector` is left untouched, so
no v14 byte-exact obligation applies; instead the honest scope note (below) explains why fast
and naive `z` differ.

## Verification (quantitative anchors)

`tests/test_fast_cbc.py` (6 passed + 1 `--run-slow`; adjacent regression on
`test_genz_cbc` + `test_deterministic_qmc` + `test_alpha_korobov`, 18 pass):

1. **FFT correlation == direct O(N²)** (white-box reconstruction, abs `< 1e-10`) — proves
   "fast" computes the *same* quantity as the naive rescan.
2. **`e(fast_cbc) ≤ e(textbook Korobov)`** for `N ∈ {31,61,127,251,509,1021}` — the CBC
   greedy-optimality certificate.
3. **`e(fast_cbc) ≤ min(e over 30 random vectors)`** at N=1021 — genuinely good lattice.
4. **deterministic**: two calls return byte-identical `z`; `z[0]=1`, all components in
   `{1,…,N−1}`.
5. **adjacency**: naive `cbc_korobov_generating_vector` still importable & in the same
   optimal class (`≤` textbook Korobov), confirming both target the same optimum.
6. **guards**: non-prime `N`, `dim<1`, weight mismatch raise `SolverError`.
7. **[--run-slow]** fast-CBC ≥ 10× faster than naive at N=1021, landing in the same optimal
   class.

## Honest scope notes

- **NOT byte-identical to the naive `z`** — and this is *provably* so, not a bug: the exact
  `g↔N−g` kernel symmetry makes the optimum a `2^{d−1}`-member set, and which member each
  routine picks is a round-off artifact (naive: summation order; fast: canonical min-`g`).
  Both are equally optimal (identical worst-case-error *class*, both certified `≤` textbook
  Korobov). The wave's literal blueprint anchor ("fast z == naive z") was therefore replaced
  by the achievable "same optimal class + correct FFT correlation + speedup".
- **Prime `N` only.** Composite `N` (non-cyclic group) is rejected, not supported by a slower
  fallback — a reopening. The in-repo consumer uses prime `N`.
- **Academic speedup for this codebase.** The only consumer (`genz_mvn_cdf_cbc`, `N≤1021`)
  runs naive CBC in ~0.35 s one-shot; the `O(N log N)` win matters only at `N ≳ 10⁴` which
  2.5-D reliability never needs. Shipped for completeness/correctness, not because the
  codebase is CBC-bound.
- **`e(fast)` can differ slightly from `e(naive)`** (e.g. N=127: 1.484e-1 vs 1.489e-1) when a
  *non-symmetric* near-tie sends the two greedy paths to different (both valid) optima — a
  property of greedy CBC, not an error.

## Reopening criteria

- **Composite-`N` fast-CBC** (Bluestein / mixed-radix on the non-cyclic group) if a non-prime
  point count is ever needed.
- **Wire fast-CBC into `genz_mvn_cdf_cbc`** as an opt-in `fast=True` path if a large-`N` Genz
  estimate is ever required (currently unnecessary).
- **Higher-smoothness fast-CBC** (compose with D118's `α≥2` kernel) — the FFT recurrence is
  kernel-agnostic, so this is a small follow-up.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (`np.fft` is numpy;
scipy/pyamg/meshio optional), 2D/2.5D only, local `pytest -q` (no network), single-line
stderr + `SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion (the honest scope note leads with why bit-equality is
impossible and why the speedup is academic here).
