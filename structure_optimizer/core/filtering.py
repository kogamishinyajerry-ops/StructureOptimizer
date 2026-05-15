from __future__ import annotations

import numpy as np

from structure_optimizer.core.mesh import StructuredMesh


def density_filter(
    mesh: StructuredMesh,
    densities: np.ndarray,
    sensitivities: np.ndarray,
    radius: float,
    min_density: float,
) -> np.ndarray:
    filtered = np.zeros_like(sensitivities, dtype=float)
    for i in range(mesh.elements.shape[0]):
        ix, iy = mesh.element_grid_index(i)
        total_weight = 0.0
        value = 0.0
        for jy in range(max(0, int(iy - radius)), min(mesh.nely, int(iy + radius + 1))):
            for jx in range(max(0, int(ix - radius)), min(mesh.nelx, int(ix + radius + 1))):
                j = mesh.element_index(jx, jy)
                distance = float(np.sqrt((ix - jx) ** 2 + (iy - jy) ** 2))
                weight = max(0.0, radius - distance)
                total_weight += weight
                value += weight * densities[j] * sensitivities[j]
        denominator = max(min_density, densities[i]) * max(total_weight, 1e-12)
        filtered[i] = value / denominator
    return filtered

