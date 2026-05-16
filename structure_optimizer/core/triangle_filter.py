"""Wave M: centroid-distance density filter for triangle (and other
unstructured) meshes.

The structured-quad filter in ``core/filtering.py`` exploits grid-coords
to keep neighbor lookups O(1) per element. For triangle meshes that
optimization is unavailable; we fall back to an explicit pairwise
neighbor scan over centroids. For modest mesh sizes (n_elem ≤ a few
thousand) this is competitive enough.

The filtering formula is the same Sigmund-style sensitivity filter:

    s̃_i = Σ_j w_ij ρ_j s_j   /   ( max(ρ_min, ρ_i) · Σ_j w_ij )
    w_ij = max(0, r − ‖c_i − c_j‖)

The denominator's ``max(ρ_min, ρ_i)`` term matches the quad filter so a
SIMP loop on triangles behaves identically when (in the limit) a
triangle mesh is the dual-of-quad split — the equivalence is verified
in the Wave M tests.
"""

from __future__ import annotations

import numpy as np

from structure_optimizer.core.triangle import TriangleMesh


def centroid_density_filter(
    mesh: TriangleMesh,
    densities: np.ndarray,
    sensitivities: np.ndarray,
    radius: float,
    min_density: float,
) -> np.ndarray:
    """Centroid-distance Sigmund sensitivity filter for triangle meshes."""
    centroids = mesh.element_centroids
    n_elem = mesh.n_elements
    filtered = np.zeros_like(sensitivities, dtype=float)
    for i in range(n_elem):
        dx = centroids[:, 0] - centroids[i, 0]
        dy = centroids[:, 1] - centroids[i, 1]
        dist = np.sqrt(dx * dx + dy * dy)
        weights = np.maximum(0.0, radius - dist)
        total_weight = float(weights.sum())
        value = float((weights * densities * sensitivities).sum())
        denominator = max(min_density, densities[i]) * max(total_weight, 1e-12)
        filtered[i] = value / denominator
    return filtered
