# D001: Defer overhang manufacturing constraint to v2.x+

- **Date**: 2026-05-16
- **Status**: Decided — deferred indefinitely
- **Supersedes**: roadmap entry "v0.6.1 overhang manufacturing constraint"

## Context

The v0.6 milestone promised manufacturing constraints for symmetry, single-axis
extrusion, and minimum member size, with overhang (additive-manufacturing build
direction support) tracked as an open task for "v0.6.1+". This document
formally defers overhang to v2.x or later, with explicit reasoning so future
contributors don't reopen the topic without new evidence.

## What "overhang constraint" means

In additive manufacturing (FDM/SLA/SLS/etc.) parts are built layer-by-layer
along a build direction. Material printed into thin air ("overhang") will sag,
slump, or require sacrificial support structure. The standard manufacturing
constraint is: every material element must be supported by material directly
below it (within an angle cone, typically 45°, around the build-direction
normal).

In 3D this is a well-defined geometric / topological constraint with several
published projection formulations (Langelaar 2017, Gaynor & Guest 2016, etc.).

## Why it's deferred

### 1. The constraint is fundamentally 3D

In pure 2D the "build direction" reduces to "one of the two in-plane axes",
which is no longer about additive manufacturing — it becomes a degenerate
projection like extrusion or asymmetric directional growth. Implementing
"2D overhang" risks misleading users into believing it represents the real
3D constraint. The project's permanent invariant is "no false 3D claims".

### 2. The 2.5D mode in `simple_bracket` is not real 3D

`simple_bracket` uses a 2D mesh with a thickness scalar for mass computation.
There is no out-of-plane geometry to constrain. Implementing overhang on this
geometry would be a cosmetic feature that produces no real engineering signal.

### 3. The cost of a correct implementation is high

A defensible overhang projection requires either:
- A real 3D mesh + voxel-walk geometry (out of scope for v1.x — see permanent
  red lines in `docs/architecture.md` §5).
- A 2D toy implementation that pretends one axis is "build direction" while
  internally documenting that this is not real overhang. This invites
  misinterpretation; the engineering ethics red line in `README.md` already
  prohibits "AI auto-generates production-certifiable parts" — pseudo-3D
  overhang is in the same category.

### 4. Existing manufacturing constraints already cover most engineering value

`symmetry` covers cast / forged parts with planar symmetry.
`extrusion` covers parts manufactured by extrusion along one axis.
`min_member_size` covers DMLS / casting / machining minimum-feature-size
limits.

These three together address the manufacturing intents most relevant to the
project's 2D / 2.5D scope. Overhang fundamentally needs a 3D companion to
deliver real value.

## What would unblock revisiting this

Reopen the decision if all three of the following are true:

1. A 3D FEM core is added (which is itself a separate, large decision —
   currently a permanent red line).
2. A reviewer presents a 2D use case where overhang gives a genuine
   engineering signal not covered by symmetry / extrusion / min_member_size.
3. There is a peer-reviewed projection formulation that explicitly states
   correctness in a 2D / 2.5D restriction.

## Impact on `quality-rubric.md` §5.6

Rubric item 5.6 originally read:
> v0.6.1 overhang 制造约束 — 实装 OR 文档化为 "won't fix" 决策

This decision satisfies the second clause: overhang is deferred and the
deferral is documented. **5.6 = 3/3** as of v1.3.0.

## Impact on `CHANGELOG.md` / `README.md`

- README "已知限制" #6: "overhang 推迟到 v0.6.1" → 改为 "overhang 已正式
  deferred 到 v2.x+，见 docs/decisions/D001-overhang-deferred.md"
- CHANGELOG Unreleased "Planned" 项中删除 v0.6.1 overhang 条目；保留
  decision record 引用

## References

- Langelaar, M. (2017). "An additive manufacturing filter for topology
  optimization of print-ready designs."
- Gaynor, A. T., & Guest, J. K. (2016). "Topology optimization considering
  overhang constraints: Eliminating sacrificial support material in additive
  manufacturing through design."
- `docs/architecture.md` §5 — Permanent invariants (no full 3D in v1.x)
- `README.md` Known Limitations §6
