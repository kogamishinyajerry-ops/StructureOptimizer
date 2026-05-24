# D059 — eigenfrequency band-gap objective on the modal solver (Wave DDD)

**Status**: Accepted
**Wave**: DDD (v9)
**Supersedes**: none (extends D051's dynamic-compliance TO + builds on the D-Z modal solver)
**Superseded by**: none

## Context

D051 (Wave VV) delivered filtered multi-ω dynamic-compliance TO. Its reopening
criteria named an **"eigenfrequency-gap (band-stop) objective built on the modal
solver"**. A band gap `g = ω²_{m+1} − ω²_m` between consecutive natural
frequencies is the phononic band-stop figure of merit; maximising it pushes two
adjacent modes apart. Wave DDD delivers the band-gap sensitivity (textbook
eigenvalue sensitivity) and a volume-preserving ascent driver, both built on the
existing `core/modal.py` generalised-eigenvalue solver.

## Decision

`core/freq_response.py` (frequency-domain TO lives here):

- `_eigenvalue_sensitivities(config, mesh, densities, n_modes, mass_type)` →
  `(omega2[n_modes], dlambda[n_modes, n_elem])`. For mass-normalised modes
  (`solve_modal` whitens with the mass Cholesky factor, so `φᵀMφ = 1`) the
  textbook eigenvalue sensitivity is
  `dλ_i/dρ_e = φ_e,iᵀ(dk_scale_e·ke − λ_i·dm_scale_e·me)φ_e,i`, with the same
  SIMP scale derivatives as the rest of the module (`dk = p·active^{p-1}(1−ρmin)`,
  `dm = (1−ρmin)`; mass uses the unpenalised linear scaling). Eigenvectors are
  scattered to the full DOF vector (0 on fixed DOFs) via the standard Q4 DOF map.
- `band_gap_sensitivity(config, mesh, densities, lower_mode=0, mass_type)` →
  `(gap, dgap_drho)` where `gap = ω²_{m+1} − ω²_m`, `dgap = dλ_{m+1} − dλ_m`.
- `maximize_band_gap(config, mesh, lower_mode=0, n_steps=20, move=0.1, ...)` →
  `BandGapResult`: volume-preserving projected-gradient **ascent** on the gap,
  reusing the Sigmund density filter and the same move-limited, volume-rescaled
  step as `dynamic_compliance_to`.

## Verification (quantitative)

- **Sensitivity vs central FD** (`test_property_band_gap_sensitivity_matches_central_fd`):
  over a random density field, `dgap/dρ_e` matches central differences of the gap
  on the top-|dgap| design elements to **rel 1e-4** (observed max 1.76e-6) — the
  textbook eigenvalue sensitivity is exact. (This is also a property test.)
- **Ascent widens the gap** (`test_maximize_band_gap_widens_gap`): the gap grows
  by >1.1× (observed ~2.2×) and stays positive (modes ordered) throughout.
- **Modes pushed apart** (`test_band_gap_pushes_modes_apart`): the final ω₂−ω₁
  exceeds the initial.
- **Determinism** (`test_band_gap_deterministic`): no RNG → bit-identical.
- **Contracts** (`test_contracts`): `band_gap_negative_mode`,
  `density_count_mismatch`. 5 tests, all green. Adjacent `test_modal` +
  `test_freq_response` + `test_damped_freq_response` + `test_dynamic_compliance_to`
  + `test_dynamic_band_to` (38) unchanged.

## Honest scope notes

- The sensitivity assumes **simple (non-repeated) eigenvalues**: for a repeated
  eigenvalue `dλ/dρ` is set-valued (the formula gives one subgradient). On the
  smoke meshes the lowest modes are well separated; near a mode crossing the
  ascent can stall or the gap definition (fixed mode index) can switch which
  physical mode it tracks. The test asserts the gap stays positive (no crossing
  in the recorded run), not that crossings are handled.
- The driver is a **projected-gradient ascent** with a volume rescale, not MMA/OC
  and not a true band-stop optimiser with a target frequency window — it widens
  the gap, it does not place it at a prescribed band (a reopening item).
- Only the consecutive-mode gap is implemented; a weighted multi-gap or a
  target-band minimax objective is future work.

## Reopening criteria

- Repeated-eigenvalue handling (sub-differential / bundle method) for symmetric
  designs where modes coalesce.
- Target-band placement: maximise the gap *around* a prescribed frequency, not
  just between mode m and m+1.
- MMA/OC-driven band-gap (replace projected-gradient ascent) and a
  frequency-weighted minimax band objective (the other two D051 reopening items).

## Red lines

numpy-only (`solve_modal` uses `np.linalg.eigh`), 2D/2.5D, single-line stderr
(`SolverError`: `band_gap_negative_mode`, plus `density_count_mismatch` /
`modal_*` from the modal solver). The modal solver and all D051 dynamic-compliance
paths are unchanged; the band-gap code is additive.
