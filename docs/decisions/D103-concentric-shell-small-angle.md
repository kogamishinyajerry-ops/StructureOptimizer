# D103 — Ruppert concentric-shell small-input-angle handling (Wave FFFFFF, v14)

**Status**: Accepted
**Wave**: FFFFFF (v14)
**Supersedes**: none (extends D096 ruppert_refine / D100 refined STL cap)
**Superseded by**: none

## Context

D096 (v13 Wave GGGGG) added Ruppert Delaunay refinement and recorded as a reopening
criterion:

> *"small-input-angle handling (concentric-shell)."*

Ruppert's midpoint splitting only **terminates for inputs without acute boundary
angles**. When two input segments meet at a small angle (below ~60°), splitting one
subsegment incident to that apex places a vertex whose diametral circle encroaches the
*neighbouring* subsegment — which is then split, placing a vertex that encroaches the
first, *ad infinitum*. D096 leaned on the `max_steiner` backstop, which only papers over
the non-termination: the probe in this wave shows plain midpoint Ruppert on a 30×10 body
with a 4.8° spike inserts dozens of points and then **breaks watertightness**
(`ruppert_not_watertight`) rather than converging.

## Decision

Two coordinated additions to `stl_export.ruppert_refine`, both gated behind a new
opt-in `concentric_shells: bool = False` (with `shell_angle_deg: float = 60.0`):

1. **Concentric-shell segment splitting** — `_small_angle_apexes` finds input vertices
   where two input segments meet below `shell_angle_deg`. A subsegment incident to such
   an apex is split at a **power-of-two radius from the apex**
   (`r = 2**round(log2(L/2))`, so `r/L ∈ [2^-0.5, 2^0.5]/2 ≈ [0.354, 0.707]` — always a
   valid interior split) instead of the midpoint. Split points on the two incident
   segments then land on the **same concentric circle**: the isosceles triangle they
   form has apex-side angles `90° − θ/2 < 90°`, so they do **not** mutually encroach —
   the ping-pong stops.

2. **Apex-lock skip** — `_apex_locked` identifies the unavoidable wedge triangle at a
   small-angle apex (a vertex in the apex set whose two triangle edges are both
   constraint subsegments). Its smallest angle **is** the input angle and cannot be
   removed by any refinement, so the skinny-triangle loop skips it. Without this, the
   loop would chase that triangle's circumcentre forever.

Together they make refinement **terminate** on acute input without relying on
`max_steiner`. `constrained_delaunay_ruppert` gains the same opt-in pass-through.
`concentric_shells=False` (default) reproduces D096's midpoint behaviour exactly.

## Verification (quantitative anchors)

`tests/test_concentric_shell.py` (6 passed; adjacent regression on
`test_ruppert_refinement` + `test_ruppert_stl_export` + `test_cdt_flip_recovery`, 18 pass):

1. **termination independent of budget**: with shells, `n_steiner` is identical at
   `max_steiner=300` and `600` (=2) and `< 300` — converged naturally, not budget-capped.
2. **plain midpoint fails (the deferred defect)**: `constrained_delaunay_ruppert(spike,
   concentric_shells=False)` raises `ruppert_not_watertight`.
3. **watertight + bound away from apex**: `concentric_shells=True` returns a watertight
   cap whose every non-apex-locked triangle has min angle `≥ 20°` (probe: 33.7°).
4. **backward-compat byte-exact (integration铁律)**: on a square (no small angle) the
   flag is a no-op — `shells=True` reproduces `shells=False` byte-for-byte
   (`np.array_equal` on points, equal tris / constraints / `n_steiner`).
5. **apex detection**: `_small_angle_apexes` flags only the sub-threshold spike vertex
   `{4}`, not 90° square corners (`∅`).
6. **guard unchanged**: the `ruppert_angle_bound_unsafe` (>20.7°) guard still fires with
   shells enabled.

## Honest scope notes

- **The input angle itself is never removed.** Geometry forbids it — the apex wedge
  triangle stays at the input angle (4.8°/11.3°/etc.). The deliverable is *termination*
  + *watertightness* + *the bound met everywhere it can be*, not "all triangles ≥ 20°".
  The tests measure the bound on the **non-apex-locked** region precisely for this reason.
- **`shell_angle_deg=60°` is the classical Ruppert/Shewchuk threshold**, not tuned per
  input. Apexes between 60° and the requested bound are handled by ordinary splitting.
- **Power-of-two shells are a heuristic toward isosceles, not a hard guarantee for every
  pathological input.** It provably avoids mutual encroachment for the
  equal-radius case and terminates on the tested wedges/spikes; I do **not** claim a
  formal termination proof for arbitrary multi-apex inputs — the `max_steiner` backstop
  remains as a safety net.
- **Not wired into `write_stl_cdt_multi_hole`'s `refine=True` path.** That writer still
  calls `constrained_delaunay_ruppert` with `concentric_shells=False` (byte-identical to
  D100); enabling shells end-to-end in the STL writer is a follow-up.
- **2.5-D extrusion**, not 3-D remeshing.

## Reopening criteria

- **Expose `concentric_shells` through `write_stl_cdt_multi_hole`** so acute-cornered
  cross-sections can be exported refined end-to-end.
- **Formal termination proof / Shewchuk "Terminator" full rule** (off-centre Steiner
  points, local-feature-size-aware) for arbitrary multi-apex inputs.
- **Multi-apex interaction** where two small-angle apexes are close enough that their
  shells interfere.

## Red lines

All permanent red lines hold: numpy-only mandatory runtime (scipy/pyamg/meshio
optional), 2D/2.5D only, local `pytest -q` (no network), single-line stderr +
`SolverError` status strings, no CAD/GUI/cloud/full-3D/commercial solvers/LLM,
self-deprecation over self-promotion.
