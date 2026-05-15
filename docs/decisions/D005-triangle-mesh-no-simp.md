# D005 — Triangle mesh supports linear-elastic solve only, not SIMP (Wave I / v1.9)

**Status**: Accepted (v1.9.0, 2026-05-16)

## Context

Wave I adds `TriangleMesh` + meshio reader. Users have asked: "Can I import
my Gmsh mesh and run SIMP on it?" Theoretical answer: yes, the SIMP method
works on any element type. Practical answer: SIMP-on-triangles requires
re-deriving the sensitivity expression for CST elements + re-implementing
the density filter + manufacturing projections + design-mask machinery for
unstructured connectivity. That's a 1500+ LOC refactor with its own
correctness concerns (e.g. the design filter radius interpretation changes
for non-uniform mesh).

## Decision

For v1.9, `TriangleMesh` supports **linear-elastic solve only**:

- `solve_tri_linear_elastic(mesh, ..., densities=None)` — accepts a density
  vector and uses it as a linear scale on element stiffness (no SIMP penalty
  power).
- `run_simp` / `run_beso` remain quad-only.
- Manufacturing projections, design_mask, void_mask, frozen_solid_mask are
  **not** implemented for triangle meshes.
- The use case enabled: "import an external tri mesh, get compliance +
  von Mises stresses + sensitivities, analyze the design at hand".

Document this clearly in:
- The triangle module docstring
- CHANGELOG entry
- Tutorial section "Triangle meshes: what works in v1.9, what doesn't"

## Alternatives considered

1. **Full SIMP-on-triangle in Wave I**. Rejected: scope creep would push
   v2.0 by 2-3 months; better to ship the simpler version + document the
   gap honestly.
2. **Hide triangle support entirely**. Rejected: even read-only triangle
   solve is valuable (analysis, validation, comparison against existing
   FEA results).
3. **Generic Mesh ABC for both quad and tri, with SIMP routed through it**.
   Rejected: the abstraction itself is most of the work; without a clear
   user pulling on it, premature.

## Consequences

- Users with quad meshes have the full v2 feature set.
- Users with tri meshes can read + solve + analyze, but for optimization
  they need to either: (a) convert their geometry to a structured quad
  mesh, or (b) wait for SIMP-on-triangle in a future major version.
- The `TriangleMesh` type is intentionally minimal (just `nodes` + `elements`)
  so future SIMP-on-triangle work doesn't have to fight existing API surface.

## Reopening criteria

- ≥3 users hit this gap and can't work around it.
- A contributor brings an adjoint-method implementation for CST elements with
  ≥80% test coverage.
- The performance gap between sparse-on-quad and sparse-on-tri becomes
  small enough that quad's domain restriction is the actual bottleneck.
