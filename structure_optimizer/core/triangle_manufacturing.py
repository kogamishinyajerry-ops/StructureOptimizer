"""Wave T: manufacturing projections on triangle meshes.

Closes D008 留白 (manufacturing on triangle defer from Wave M). On a
structured quad, manufacturing projections operate on a regular grid —
mirror across an axis is a simple swap of grid columns/rows. On an
unstructured triangle mesh, we use centroid-based geometric matching:

- **symmetry**: for each design element, find its centroid's mirror
  position; locate the nearest design element to that mirror; average
  densities.
- **extrusion**: bucket centroid coordinates along the perpendicular
  axis; average densities within each bucket.

Both projections preserve the symmetry/extrusion property approximately
on irregular meshes (exact on a mesh that itself has the relevant
symmetry); residuals are caught by the existing post-hoc
manufacturability checks.

This module deliberately keeps the API surface small: a single
``apply_triangle_manufacturing_projections`` entry point that mirrors
the quad-mesh ``apply_manufacturing_projections``. Reference geometry
is read from the ``TriangleMesh`` itself (no extra config beyond the
existing ``ManufacturingConstraintsConfig`` dataclasses).
"""

from __future__ import annotations

import numpy as np

from structure_optimizer.core.config import (
    ExtrusionConstraintConfig,
    ManufacturingConstraintsConfig,
    SymmetryConstraintConfig,
)
from structure_optimizer.core.triangle import TriangleMesh


def apply_triangle_manufacturing_projections(
    constraints: ManufacturingConstraintsConfig,
    mesh: TriangleMesh,
    densities: np.ndarray,
) -> np.ndarray:
    """Apply active manufacturing projections to a triangle-mesh density field.

    Order: symmetry → extrusion (matching the structured-quad path).
    Returns a new array; input is not mutated.
    """
    result = np.asarray(densities, dtype=float).copy()
    if constraints.symmetry is not None:
        result = apply_triangle_symmetry_projection(mesh, result, constraints.symmetry)
    if constraints.extrusion is not None:
        result = apply_triangle_extrusion_projection(mesh, result, constraints.extrusion)
    return result


def apply_triangle_symmetry_projection(
    mesh: TriangleMesh,
    densities: np.ndarray,
    symmetry: SymmetryConstraintConfig,
) -> np.ndarray:
    """Average densities across the symmetry line via nearest-centroid pairing.

    For ``axis='x'``: line is vertical at ``x = position * (x_max - x_min) + x_min``;
    each element's centroid is reflected and the nearest element is the pair.
    For ``axis='y'``: analogous with horizontal line.

    Pairs are mutual: if element A maps to B, B maps to A (we average both
    once and write back). Self-pairs (centroid on the line) are left alone.
    """
    centroids = mesh.element_centroids  # (n_elem, 2)
    x_min, x_max = float(centroids[:, 0].min()), float(centroids[:, 0].max())
    y_min, y_max = float(centroids[:, 1].min()), float(centroids[:, 1].max())
    if symmetry.axis == "x":
        line = x_min + symmetry.position * (x_max - x_min)
        mirrored = centroids.copy()
        mirrored[:, 0] = 2 * line - centroids[:, 0]
    else:  # axis == "y"
        line = y_min + symmetry.position * (y_max - y_min)
        mirrored = centroids.copy()
        mirrored[:, 1] = 2 * line - centroids[:, 1]

    # For each element, find nearest by Euclidean distance from its mirror to
    # other elements' centroids.
    n_elem = centroids.shape[0]
    pair = np.full(n_elem, -1, dtype=int)
    for i in range(n_elem):
        dist = np.sum((centroids - mirrored[i]) ** 2, axis=1)
        pair[i] = int(np.argmin(dist))

    # Average each mutual pair once
    new_densities = densities.copy()
    averaged = np.zeros(n_elem, dtype=bool)
    for i in range(n_elem):
        j = int(pair[i])
        if averaged[i] or averaged[j]:
            continue
        if i == j:
            # Self-pair (centroid on or near line) — leave as-is
            averaged[i] = True
            continue
        mean = 0.5 * (densities[i] + densities[j])
        new_densities[i] = mean
        new_densities[j] = mean
        averaged[i] = True
        averaged[j] = True
    return new_densities


def apply_triangle_extrusion_projection(
    mesh: TriangleMesh,
    densities: np.ndarray,
    extrusion: ExtrusionConstraintConfig,
    n_buckets: int | None = None,
) -> np.ndarray:
    """Average densities along the extrusion axis via centroid bucketing.

    For ``axis='x'``: result depends only on y (densities uniform along x).
    For ``axis='y'``: result depends only on x.

    Buckets are sized so each bucket has ~ same number of elements (default
    bucket count = ``max(4, sqrt(n_elem))``). Within each bucket, the mean
    density is broadcast back.
    """
    centroids = mesh.element_centroids
    n_elem = centroids.shape[0]
    if n_buckets is None:
        n_buckets = max(4, int(np.sqrt(n_elem)))

    # Bucket along the *perpendicular* of the extrusion axis
    coord = centroids[:, 1] if extrusion.axis == "x" else centroids[:, 0]

    lo, hi = float(coord.min()), float(coord.max())
    if hi <= lo + 1e-12:
        return densities.copy()  # degenerate: all centroids collinear
    edges = np.linspace(lo, hi + 1e-12, n_buckets + 1)
    bucket = np.clip(np.searchsorted(edges, coord, side="right") - 1, 0, n_buckets - 1)

    new_densities = densities.copy()
    for b in range(n_buckets):
        mask = bucket == b
        if not np.any(mask):
            continue
        mean = float(np.mean(densities[mask]))
        new_densities[mask] = mean
    return new_densities


def measure_triangle_symmetry_residual(
    mesh: TriangleMesh,
    densities: np.ndarray,
    symmetry: SymmetryConstraintConfig,
) -> float:
    """Return the max |ρ - ρ_mirror| over mirror-paired elements.

    Useful for post-hoc verification: 0 = perfect symmetry, > 0 means
    residual (mesh asymmetry or non-projected density). Reports the
    geometric quantity, not a normalized fraction.
    """
    projected = apply_triangle_symmetry_projection(mesh, densities, symmetry)
    return float(np.max(np.abs(projected - densities)))


def measure_triangle_extrusion_residual(
    mesh: TriangleMesh,
    densities: np.ndarray,
    extrusion: ExtrusionConstraintConfig,
    n_buckets: int | None = None,
) -> float:
    """Return the max |ρ - ρ_bucket_mean| over the mesh."""
    projected = apply_triangle_extrusion_projection(mesh, densities, extrusion, n_buckets)
    return float(np.max(np.abs(projected - densities)))
