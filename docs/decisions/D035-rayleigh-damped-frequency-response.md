# D035 — Rayleigh-damped complex frequency response (Wave FF)

**Status**: Accepted
**Wave**: FF (v6)
**Supersedes**: none (deepens D026's undamped freq response; reopens its "Reopening criteria")
**Superseded by**: none

## Context

v5 Wave Z (D026) shipped an **undamped** harmonic-response solver
(`core/freq_response.py`): it solves the real system `(K − ω²M) û = f̂`. Its
docstring + D026's "Reopening criteria" flagged Rayleigh damping
(`C = αM + βK`) and the resulting complex system as the v5+ extension. The
undamped form is singular at every natural frequency, so it cannot evaluate
the response *at* resonance — exactly where damping matters. v6's charter is
to turn these simplifications into production-grade formulations.

## Decision

Add `solve_damped_frequency_response(...)` to `core/freq_response.py` solving

    (K − ω²M + iωC) û = f̂ ,   C = α M + β K   (Rayleigh)

as a complex linear system. Returns the complex amplitude `û`, its per-DOF
magnitude and phase, the peak magnitude, and the Rayleigh coefficients. Plus:

- `rayleigh_modal_damping_ratio(α, β, ω) = ½(α/ω + βω)` — the modal damping
  ratio identity for Rayleigh damping.
- `half_power_bandwidth(omega_arr, magnitude)` — extracts the −3 dB bandwidth
  of a resonance peak from a magnitude sweep and returns the implied ζ.

Reuses the same SIMP-scaled `K`, `M` assembly as the undamped path and the
modal mass-matrix helpers; single-line `SolverError`.

## Verification (analytical anchor)

- **Reduces to undamped** (`test_damped_reduces_to_undamped_when_zero_damping`):
  with α = β = 0 the damped magnitude equals the undamped real solve (rtol 1e-9).
- **Finite at resonance** (`test_damped_response_finite_at_resonance`): at ω = ω₁
  the damped peak is finite (the undamped solve is singular there) — the headline
  capability gain.
- **Half-power bandwidth** (`test_rayleigh_half_power_bandwidth_matches_analytical`,
  rubric §2.5): mass-proportional damping (β = 0) with ζ = 0.05 produces a −3 dB
  bandwidth whose implied ζ ≈ 0.05 (within 25%, the continuum-vs-SDOF margin),
  and the peak sits at ω₁ (within 5%). ω₁ comes from `solve_modal`.
- ζ-formula identity test; "heavier damping → smaller peak" property; negative
  coefficients raise.

6 tests, all green.

## Honest scope notes

- Rayleigh (proportional) damping only — α, β are global. Non-proportional /
  modal-specific damping matrices are a later option.
- Single-frequency complex solve (dense). A batched/swept complex solver and a
  damped-response topology-optimization driver are future options.
- The half-power identity Δω ≈ 2ζω holds for light damping; the test pins
  ζ = 0.05 where it is accurate.

## Reopening criteria

- A workflow needing non-proportional damping → accept a user-supplied C.
- Damped anti-resonance topology optimization → add the complex adjoint.

## Red lines

numpy-only, 2D, dense, single-line stderr — all held.
