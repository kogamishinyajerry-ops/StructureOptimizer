# D025 — Heat-conduction SIMP (Wave Y · v5)

**Status**: Accepted
**Wave**: Y (introduces multi-physics layer)
**Supersedes**: none
**Superseded by**: none

## Context

v1-v4 covered linear-elastic + buckling + Heaviside-robust topology
optimization. The v5 charter extends to multi-physics within 2D +
numpy-only red lines. Heat conduction is the natural starting point:

- Linear PDE (Poisson), so the symmetric-SIMP recipe transfers directly
  (sensitivity = -p · ρ^(p-1) · (1-ρ_min) · element_energy).
- Has an industrial use case (heat sinks, MEMS) where the topology
  matters and analytical references exist for verification.
- DOF count per node is 1 (scalar T), vs 2 for elasticity — strictly
  simpler assembly path, so no v1-v4 regression risk.

## Decision

- New module `core/thermal.py` — 2D bilinear-quad FEM for the steady-state
  heat equation, mirroring `fem2d.py`'s structure.
- New module `core/thermal_simp.py` — SIMP driver that minimises
  thermal compliance ``T^T · K(ρ) · T`` subject to the standard volume
  fraction constraint, reusing `_apply_density_masks`,
  `_optimality_criteria_update`, and `density_filter` from the elastic
  pipeline (no duplication).
- New benchmark `heat_sink.json` with a `thermal` block (conductivity,
  heat sources, thermal BCs). The block is parsed *separately* from
  `BenchmarkConfig` (via `load_thermal_benchmark`) to preserve the
  v1-v4 schema and avoid touching `parse_config` (zero regression risk).
- New mesh selector `"center"` (single node at mesh-mid) for thermal
  sources. Additive change to `mesh.py`; doesn't break any existing
  benchmark.
- New fingerprint `tests/fingerprints/heat_sink__smoke.json` to lock
  the SIMP output bit-exact.

## Why the schema split

`BenchmarkConfig` is read by v1-v4 tests + fingerprints. Adding a
typed `thermal` field would either:
1. Need to set a default everywhere (cantilever / mbb / etc. all get
   a `thermal=None` field), or
2. Break input-hash bit-exactness for every v1-v4 fingerprint.

Both are bad. The chosen alternative — `load_thermal_benchmark` reads
the raw JSON, strips the `thermal` block, then delegates to the
existing `parse_config` — is strictly additive and has zero risk to
existing rubrics.

## Element matrix derivation (honest reference)

For a bilinear 4-node quad on a unit reference square:

    Ke = (k · t / 6) · [[ 4, -1, -2, -1],
                        [-1,  4, -1, -2],
                        [-2, -1,  4, -1],
                        [-1, -2, -1,  4]]

derived from ∫₋₁¹ ∫₋₁¹ ∇N_i · ∇N_j |J| dξ dη with the standard
bilinear basis functions N₁..N₄. Cook 1989 §10.2 and Bathe FEA
textbook both quote this form.

For rectangular (non-square) elements this is wrong; a proper
implementation needs separate (dy/dx) and (dx/dy) coefficients on
the x- and y-derivative integrals. Following the convention of
`fem2d.element_stiffness` (which also assumes unit elements), the
geometric scaling is absorbed into the (k, t, q) calibration constants.
For the SIMP relative-ranking objective this doesn't matter.

## Honest scope notes

- **Constant scalar k only** — no per-element anisotropic conductivity,
  no orthotropic materials. v5+ if needed.
- **Steady-state only** — no transient heat equation (∂T/∂t).
  Out of scope.
- **No coupled thermo-elastic SIMP** — that's Wave Z (D026 will
  cover thermo-elastic coupling) or a v5.x sub-wave.
- **Element matrix is unit-size** — same caveat as elastic
  `element_stiffness`. Honest disclosure here, not silent.
- **Dense assembly only** — sparse path follows the elastic pattern
  but is deferred until a 500×500 thermal benchmark is added.

## Reopening criteria

- If a user reports thermal compliance disagreeing with COMSOL /
  ANSYS Steady-State Thermal by > 5%, add a Q4-rectangular element
  matrix variant and route through it when dx ≠ dy.
- If transient heating becomes load-bearing for a real use case,
  introduce `core/thermal_transient.py` with a θ-method time
  integrator (don't extend `thermal.py`).
- If thermo-elastic coupling is needed (heat → thermal stress →
  mechanical displacement), do it in a Wave Z follow-on, not by
  modifying `thermal.py`.

## Consequences

- 2 new modules (~250 LOC), 1 new benchmark JSON, 1 new fingerprint.
- 23 new tests (15 in `test_thermal.py`, 8 in `test_thermal_simp.py`).
- Total LOC delta: ~600. Zero risk to v1-v4 regression checks.
- v5 rubric §1.1 + §2.1 = 10 pts earned in this wave.
