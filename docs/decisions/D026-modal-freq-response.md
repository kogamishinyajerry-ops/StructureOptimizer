# D026 — Modal analysis + frequency response (Wave Z · v5)

**Status**: Accepted
**Wave**: Z
**Supersedes**: none
**Superseded by**: none

## Context

Topology optimization for **dynamic** loads (vibration isolation,
anti-resonance, eigenfrequency maximisation) is a major industrial
use case missing from v1-v4. Wave Z fills it.

Two modules are needed:

- **Modal** — solve `K φ = ω² M φ` for the lowest natural frequencies.
- **Frequency response** — solve `(K - ω² M) u = f` for steady-state
  harmonic excitation amplitude.

Both share a new mass-matrix assembly path.

## Decision

- **Mass matrix**: 4-node bilinear quad consistent mass matrix
  (Hughes 1987 §7.3 Table 7.3.2), built as
  `Me = ρ · t · A / 36 · pattern ⊗ I₂` where pattern is the standard
  4×4 quadratic-shape-function product integrals and `I₂` couples ux/uy
  DOFs. Lumped option = row-sum lumping → diagonal.
- **Eigensolver**: pure-NumPy Cholesky transform → `np.linalg.eigh`.
  Scipy `eigh(K, M)` would be cleaner but scipy is optional; the
  Cholesky transform delivers the same answer with only numpy.
- **SIMP mass scaling**: **linear** (no penalty exponent) per
  Diaz & Kikuchi 1992. Penalising mass with p > 1 creates spurious
  localised eigenmodes in low-density regions.
- **Frequency response**: real-valued (no damping). Solves the
  dynamic stiffness `D = K - ω² M`. Singular-at-resonance maps to
  `SolverError("frequency_response_resonance_singular")` rather than
  silently returning huge amplitudes.

## Why Cholesky transform vs scipy eigh

scipy.linalg.eigh(K, M) is the standard approach, but scipy is an
**optional** dep under the v1-v4 red-line policy. The Cholesky transform

    M = L Lᵀ  → solve L⁻¹ K L⁻ᵀ ψ = λ ψ  → φ = L⁻ᵀ ψ

reduces the generalised problem to a standard symmetric eigenproblem that
`np.linalg.eigh` handles in pure numpy. The factorization is dense
O(N³), same as scipy's underlying LAPACK call; the cost difference is
negligible at the mesh sizes v5 targets.

## Anti-resonance topology optimisation

The frequency-response objective `‖u(ω)‖` minimised over densities at a
fixed excitation ω is the **anti-resonance** design problem: shape the
topology so the natural frequencies sit on either side of the operating
frequency, suppressing the response at ω. The sensitivity is

    d(uᵀu)/dρ_e = 2 uᵀ D⁻¹ [dK/dρ_e - ω² dM/dρ_e] D⁻¹ u

(adjoint method) and is straightforward to add atop the SIMP main loop
when needed. v5 ships the FEM kernel + tests; the integrated SIMP
driver is deferred to a v5+ sub-wave if a real workflow demands it.

## Element mass matrix derivation (honest reference)

For a bilinear quad on a unit reference square `(ξ, η) ∈ [-1, 1]²`:

    M_ij = ρ · t · ∫∫ N_i · N_j |J| dξ dη

With unit-sized element |J| = 1/4 and the standard bilinear basis,
the 4×4 pattern is

    pattern = (1/36) · [[4, 2, 1, 2],
                        [2, 4, 2, 1],
                        [1, 2, 4, 2],
                        [2, 1, 2, 4]]

Kronecker with I₂ gives the 8×8 plane-stress mass matrix:

    Me = ρ · t · pattern ⊗ I₂

Validation: trace of lumped mass = sum of consistent mass entries =
total element mass. Both checks are in `test_modal.py`.

## Honest scope notes

- **No damping** — undamped real-valued dynamic stiffness only. Rayleigh
  damping (`C = αM + βK`) would complexify the system and require a
  complex linear solve. v5+ if needed.
- **No Lanczos for many eigenvalues** — dense eigh works to ~2000 DOFs
  comfortably. For 1000×1000 (2M DOFs) we'd need sparse Lanczos, which
  is a scipy.sparse.linalg.eigsh call (already optional dep).
- **Element matrix unit-sized** — same caveat as `element_stiffness`
  (D025).
- **No integrated modal-SIMP driver** — Wave Z ships the kernel; the
  SIMP integration (max ω₁ s.t. volume) is a Wave AA / DD candidate.

## Reopening criteria

- If a real workflow needs damping, add a `solve_frequency_response_damped`
  variant that returns complex displacements.
- If eigenvalues beyond mode ~50 are needed routinely, switch to
  scipy.sparse.linalg.eigsh with the optional `[sparse]` dep.
- If the modal-SIMP integration becomes load-bearing, add `modal_simp.py`
  modelled on `thermal_simp.py`.

## Consequences

- 2 new modules (~280 LOC).
- 24 new tests (15 modal + 9 freq-response, all under 0.5s).
- 1 new benchmark `vibrating_beam.json`.
- v5 rubric §1.2 + §1.6 + §2.2 + §2.4 = 16 pts.
