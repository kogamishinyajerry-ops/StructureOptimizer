# D047 — damped frequency-response TO: dynamic compliance (Wave RR)

**Status**: Accepted
**Wave**: RR (v7)
**Supersedes**: none (consumes D035's damped forward solve as a TO driver)
**Superseded by**: none

## Context

v6 Wave FF (D035) added the Rayleigh-damped complex harmonic solve
`solve_damped_frequency_response`: (K − ω²M + iωC)û = f, C = αM + βK, verified
via the half-power bandwidth. Its reopening criterion named the driver: minimise
**dynamic compliance** with the damped forward solve. v7 Wave RR delivers the
sensitivity + a compact resonance-avoidance driver.

## Decision

`core/freq_response.py`:

- `_build_harmonic_load(config, mesh)` — the real load amplitude f̂ (factored out
  of the existing solver's inline build; the solver itself is untouched).
- `dynamic_compliance_sensitivity(config, mesh, densities, omega, alpha, beta,
  mass_type)` → `DynamicComplianceResult(dynamic_compliance c, objective J,
  sensitivity, …)`. Objective J = |c|², c = fᵀû. Because K, M, C (hence
  D = K − ω²M + iωC) are **symmetric** (not Hermitian) and the output load
  equals the input load, the adjoint is **self-adjoint**:

      dc/dρ_e = −û_eᵀ (dD_e/dρ_e) û_e,
      dD_e/dρ_e = (dk_scale/dρ_e)(1 + iωβ)·ke + (dm_scale/dρ_e)(−ω² + iωα)·me,
      dJ/dρ_e   = 2·Re(c̄ · dc/dρ_e),

  with dk_scale/dρ_e = p·ρ_e^(p−1)·(1−ρ_min) and dm_scale/dρ_e = (1−ρ_min)
  (mass is linearly interpolated, stiffness is SIMP-penalised). Void elements
  skipped.
- `minimize_dynamic_compliance(config, mesh, omega, alpha, beta, n_steps, move,
  …)` → `DynamicTOResult(densities, objective_history, omega)`: volume-preserving
  projected-gradient descent on J at a fixed ω (resonance avoidance).

## Verification (quantitative)

- **Sensitivity vs central-FD** (`test_dynamic_compliance_sensitivity_matches_central_fd`):
  the self-adjoint sensitivity matches central differences of J to rel 1e-5 on
  the 6 most-sensitive design elements (observed ≈1e-7) — the §6 headline anchor.
- **Undamped reduction** (`test_undamped_dynamic_compliance_is_real_and_matches_real_solver`):
  with α=β=0, D is real → c is real (imag < 1e-6·|real|) and J = (fᵀu)² of the
  existing real `solve_frequency_response` to rel 1e-8 — ties the new objective to
  the v5 solver.
- **Monotone descent** (`test_descent_lowers_dynamic_compliance_monotonically`):
  J is non-increasing over all 20 steps and ends below 0.5·J₀ (observed ≈0.14·J₀).
- **Resonance avoidance** (`test_descent_cuts_the_resonance_peak`): the peak
  magnitude over a 10–120 rad/s sweep drops for the optimised design (observed
  2.60 → 0.97), with the target volume fraction preserved to rel 1e-6.
- **Contracts** (`test_contracts`): density mismatch / negative ω / negative
  damping → `SolverError`. 5 tests, all green. Adjacent `test_damped_freq_response`
  + `test_freq_response` + `test_modal` (30) unchanged.

## Honest scope notes

- The objective is the **squared dynamic compliance** J = |fᵀû|² at a *single*
  excitation frequency. A multi-frequency (band-averaged) objective would sum the
  per-ω sensitivities — straightforward but a larger driver, left to reopening.
- `minimize_dynamic_compliance` is a **compact projected-gradient descent** with
  volume rescaling, not an MMA/OC solver with filtering. The verifiable claim is
  that the *analytic sensitivity drives J down* and cuts the resonant peak — not
  that this is a production dynamic-TO optimiser. No density filter is applied, so
  the resulting field can be checkerboard-prone; a filtered MMA loop is the
  production path.
- Self-adjointness relies on the output functional being fᵀû with the *same* f as
  the load. A different output (e.g. displacement at a sensor DOF) would need a
  distinct adjoint load and is out of scope.

## Reopening criteria

- Band-averaged / multi-ω dynamic compliance with summed sensitivities.
- A filtered MMA/OC dynamic-TO loop with a documented checkerboard-free result
  and a frequency-sweep before/after comparison.
- Eigenfrequency-gap or mode-tracking objectives (push resonances away from a
  forbidden band) built on the modal solver.

## Red lines

numpy-only (`np.linalg.solve` on the complex free-DOF block), 2D, single-line
stderr (`SolverError`). `solve_damped_frequency_response`,
`solve_frequency_response`, `half_power_bandwidth` and the modal assemblers are
unchanged; the new code only consumes them.
