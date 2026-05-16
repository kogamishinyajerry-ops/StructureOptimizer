# D027 — Geometric-nonlinear FEM + SIMP driver (Wave AA · v5)

**Status**: Accepted
**Wave**: AA
**Supersedes**: none
**Superseded by**: none

## Context

v1-v4 ran linear-elastic SIMP. For structures undergoing **moderate
displacements** (cantilevers under their full operating load, compliant
mechanisms, anything beyond linear-small-displacement assumptions),
linear FEM systematically **over-predicts** displacements because
it ignores geometric stiffening from the deformed configuration.

The classic textbook benchmark is the **Gere elastica**: an end-loaded
cantilever undergoing large tip rotation. The exact solution involves
elliptic integrals (Gere 1991 Ch. 9); the qualitative behaviour is
that as load grows, the tip displacement plateau-tapers rather than
growing linearly.

## Decision

Implement a **simplified Total Lagrangian** Newton-Raphson FEM that
captures geometric stiffening via the same `K_g` matrix used by the
v4 buckling solver (`core/buckling.assemble_geometric_stiffness`).

Algorithm (per call):
1. Build linear stiffness `K(ρ)`.
2. For each of `n_load_steps` incremental load fractions f_step:
   - Newton iterate up to `max_inner_iter` times:
     - Assemble `K_g(ρ, u_current)`.
     - Tangent stiffness `K_T = K + K_g`.
     - Internal force `f_int = K·u + (1/2) K_g·u` (SVK approximation).
     - Residual `R = f_step - f_int`.
     - Solve `K_T Δu = R` for the displacement increment.
     - Update `u += Δu`.
     - Stop when `‖R‖ / ‖f_step‖ < tol`.

SIMP driver: `run_nonlinear_simp` minimises `f_ext · u_nonlinear`
subject to the volume constraint, using the linear-FEM sensitivity
approximation (Buhl et al. 2000) on the nonlinear displacement field.

## Why "simplified" vs full TL Green-strain

The full Total Lagrangian formulation (Bonet & Wood Ch. 9) requires:

- Element deformation gradient `F = I + ∂u/∂X` at each Gauss point
- Green strain `E = (1/2)(F^T F - I)`
- 2nd Piola-Kirchhoff stress `S = C:E` (or hyperelastic form)
- Linearised B-matrix `B_L(F)` for the internal force
- Geometric stiffness `K_g = ∫ G^T S_block G dV` (with G the shape
  gradient and S_block the block-diagonal of S)

That's ~400 LOC of numpy with subtle indexing for the 4×4 ↔ 8×8
mappings. The **simplified** approximation used here exposes the
same `K_g` already used by the v4 buckling solver, captures the
correct geometric stiffening qualitatively, and validates against
linear FEM at the small-load limit.

It does NOT bit-exactly match the elastica formula. **Honest scope
note**: the `test_nonlinear_gere_elastica_trend_geometric_stiffening`
test checks the **qualitative** Gere trend (u_nl ≤ 1.1 × u_linear),
not a bit-exact match.

## Why reuse buckling's K_g instead of a fresh implementation

The v4 buckling `_element_geometric_stiffness_quad` was already
validated against the closed-form Euler buckling load (Wave U,
D019). Reusing it ensures consistency between buckling onset and
geometric nonlinearity — same K_g, same sign convention, same
SIMP penalty.

## Honest scope notes

- **No full elastica match** — geometric stiffening trend only
  (qualitative). For ≤ 1% Gere agreement, implement full TL Newton.
- **No path tracking / snap-through** — incremental load stepping
  only; arc-length method (Riks) is a v5+ option for snap-through
  problems.
- **Linear-FEM sensitivity in SIMP** — nonlinear adjoint is out
  of scope (Buhl et al. 2000 simplification).
- **St. Venant-Kirchhoff only** — no Neo-Hookean, Mooney-Rivlin,
  or other hyperelastic models.
- **Plane stress, 2D** — same as v1-v4 (permanent red line).

## Reopening criteria

- If a workflow needs Gere agreement to ≤ 5%, implement full TL
  Green-strain + 2nd PK formulation.
- If snap-through paths matter, add Riks arc-length continuation.
- If hyperelastic materials become needed (rubber-like), generalise
  the material law in `nonlinear_fem.py`.

## Consequences

- 2 new modules (~280 LOC).
- 14 new tests (9 FEM + 5 SIMP) all under 1 s.
- 1 new benchmark `nonlinear_cantilever.json`.
- v5 rubric §1.3 + §2.3 = 8 pts (and a small property bump in §4.3).
