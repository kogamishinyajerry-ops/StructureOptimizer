# D028 — Multi-material SIMP (Wave BB · v5)

**Status**: Accepted
**Wave**: BB
**Supersedes**: none
**Superseded by**: none

## Context

Real engineered structures often combine multiple materials —
fibre-reinforced composites, bi-metallic brackets, lattice + bulk,
adhesive joints. Single-material SIMP (v1-v4) cannot represent these.

Two literature approaches:

1. **Ordered SIMP** (Pareto et al. 2012): single density variable per
   element, mapped through a smoothed Heaviside ladder to M discrete
   materials.
2. **Sigmund-Tortorelli** (Bendsøe-Sigmund "Topology Optimization", §1.6):
   M independent density fields per element, each penalised by SIMP,
   summed into the element's effective Young's modulus.

The Sigmund form is M × the memory but cleaner: each material's
volume constraint is independent, the OC update is independent, and
the sensitivity decomposes per-material.

## Decision

Implement the **Sigmund-Tortorelli** form:

- `core/multi_material.py`:
  - `MaterialProperty` dataclass — (name, E, ν, ρ) per material
  - `effective_modulus_per_element(densities, materials, p, e_min)` —
    `E_eff = E_min + Σᵢ ρ_{i,e}^p · (Eᵢ - E_min)`
  - `solve_multi_material(...)` — assemble K from E_eff, solve, return
    per-material element energies for SIMP sensitivity
  - `run_multi_material_simp(...)` — SIMP main loop with M density
    fields, M-way OC update, per-material volume constraints

Volume constraints are **per-material**: each ρ_i has its own
`mean(ρ_i) ≤ V_i_target`. The optimiser doesn't enforce
``Σᵢ V_i_target ≤ 1`` — the caller is responsible.

## Why Sigmund-Tortorelli vs Ordered SIMP

| | Sigmund-Tortorelli | Ordered SIMP |
|---|---|---|
| Density variables per element | M | 1 |
| OC update | per-material independent | requires Heaviside-aware OC |
| Sensitivity | linear decomposition | requires chain rule through smooth ladder |
| Pure-numpy complexity | low | medium |
| Volume constraint structure | per-material | aggregate with mapping |
| Risk of phase-mixing | none (each material is independent) | small (smooth ladder allows interpolated states) |

Sigmund-Tortorelli wins on implementation simplicity and test clarity.
Ordered SIMP is a future option if a workflow needs the single-variable
formulation for an external optimiser.

## Honest scope notes

- **Single shared Poisson ratio** — we use the first material's ν for
  the element-stiffness template. Differences in ν are usually 2nd-order
  and ignored at this scope. If a real workflow needs per-material ν,
  the assembly path needs to loop over materials and accumulate.
- **No volume coupling** — caller is responsible for `Σᵢ Vᵢ ≤ 1` if
  physical realisability matters.
- **Linear elastic only** — no thermal / nonlinear / buckling extensions
  in Wave BB (would compose with D025/D026/D027 if needed).
- **No anti-cheating term** — the literature has variants that penalise
  multi-material mixtures at the same element (forcing pure materials).
  We don't add this; the OC update + filter + ρ ∈ [ρ_min, 1] bounds
  give sufficiently pure outcomes in practice.

## Reopening criteria

- If anti-cheating becomes necessary, add a `mixture_penalty(densities)`
  term to the sensitivity.
- If ordered SIMP is preferred by users, implement it as a separate
  module `core/multi_material_ordered.py` rather than coupling the
  two formulations.
- If 4+ materials become a routine workflow, profile memory and
  consider sparse density storage.

## Consequences

- 1 new module (~270 LOC).
- 14 new tests (covering effective-modulus, FEM solve, SIMP main loop,
  and 2 property tests).
- 1 new benchmark `bimaterial_beam.json`.
- v5 rubric §1.4 = 5 pts.
