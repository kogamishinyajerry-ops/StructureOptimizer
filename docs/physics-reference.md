# StructureOptimizer Physics Reference

> Mathematical formulation of every objective, constraint, and algorithm
> implemented in v2.x. Each section names the relevant module and cites the
> reference paper(s).

---

## 1. Plane-stress linear elasticity

Element-level constitutive law (plane stress):

$$
\mathbf{D} = \frac{E}{1 - \nu^2}
\begin{bmatrix}
1 & \nu & 0 \\
\nu & 1 & 0 \\
0 & 0 & (1-\nu)/2
\end{bmatrix}
$$

Element stiffness matrix:

$$
\mathbf{K}_e = t \int_{\Omega_e} \mathbf{B}^T \mathbf{D} \mathbf{B} \, d\Omega
$$

where $\mathbf{B}$ is the strain-displacement matrix and $t$ is thickness.

**Quad (bilinear) element**: 8×8 kernel. Analytical integration assuming
unit cell. Module: `core/fem2d.py::element_stiffness`.

**Triangle (CST, Constant Strain Triangle)**: 6×6 kernel. Constant
$\mathbf{B}$ per element ⇒ single-point Gauss is exact.
Module: `core/triangle.py::triangle_stiffness`.

References:
- Bathe (1996), *Finite Element Procedures*, §5.3.
- Cook et al. (2002), *Concepts and Applications of Finite Element Analysis*, ch. 6.

---

## 2. SIMP topology optimization

**Objective**: minimize compliance (= twice the strain energy):

$$
c(\boldsymbol{\rho}) = \mathbf{u}^T \mathbf{K}(\boldsymbol{\rho}) \mathbf{u} \quad \text{s.t.} \quad \mathbf{K} \mathbf{u} = \mathbf{f}
$$

**SIMP penalty interpolation** (Bendsøe 1989):

$$
E_e(\rho_e) = E_{\min} + \rho_e^p (E_0 - E_{\min}), \quad \rho_e \in [\rho_{\min}, 1]
$$

where $p$ is the SIMP penalty (typically 3 for compliance minimization)
and $\rho_{\min}$ is the floor (small, non-zero) to avoid singular stiffness.

**Sensitivity** (per element):

$$
\frac{\partial c}{\partial \rho_e} = -p \rho_e^{p-1} \mathbf{u}_e^T \mathbf{K}_e^0 \mathbf{u}_e
$$

**Optimality criteria update** (Bendsøe & Sigmund 2003):

$$
\rho_e^{\text{new}} = \max\left(\rho_{\min},\, \max(\rho_e - m,\, \min(1, \min(\rho_e + m, \rho_e \sqrt{B_e}))) \right)
$$

with $B_e = -\frac{\partial c / \partial \rho_e}{\lambda \cdot \partial V / \partial \rho_e}$
and $\lambda$ found via bisection to satisfy the volume constraint.

**Density filter**: Sigmund (2001) density-weighted sensitivity filter with a
linear-hat (cone) weight kernel of radius $r_{\min}$, applied to the
sensitivities (see `core/filtering.py::density_filter`).

Module: `core/simp.py::run_simp`.

References:
- Bendsøe & Sigmund (2003), *Topology Optimization: Theory, Methods, and Applications*, Springer.
- Sigmund (2001), "A 99 line topology optimization code written in Matlab", *Structural and Multidisciplinary Optimization*.
- Bourdin (2001), "Filters in topology optimization", *IJNME*.

---

## 3. Multi-load-case aggregation (Wave E)

Given $K$ load cases $\{\mathbf{f}_k\}$ producing displacements $\{\mathbf{u}_k\}$:

**Weighted sum**:

$$
c_{\text{ws}}(\boldsymbol{\rho}) = \sum_{k=1}^{K} \frac{w_k}{\sum_j w_j} \mathbf{u}_k^T \mathbf{K} \mathbf{u}_k
$$

**Average** (degenerate weighted with all $w_k = 1$):

$$
c_{\text{avg}}(\boldsymbol{\rho}) = \frac{1}{K} \sum_k \mathbf{u}_k^T \mathbf{K} \mathbf{u}_k
$$

**Worst case** (min-max robust):

$$
c_{\text{wc}}(\boldsymbol{\rho}) = \max_k \mathbf{u}_k^T \mathbf{K} \mathbf{u}_k
$$

Sensitivity for worst case is a subgradient (non-smooth at argmax ties):
in practice we take the argmax-case sensitivity. This is a heuristic but
works well at OC step sizes; see Bendsøe & Sigmund §1.4 for theoretical
justification.

Module: `core/objectives.py::aggregate`.

References:
- Bendsøe & Sigmund (2003), §1.4 (robust formulation).
- Diaz & Bendsøe (1992), "Shape optimization of structures for multiple loading conditions", *Structural Optimization*.

---

## 4. Stress aggregation (Wave F)

Per-element von Mises stress (plane stress):

$$
\sigma_{vm,e} = \sqrt{\sigma_x^2 - \sigma_x \sigma_y + \sigma_y^2 + 3 \tau_{xy}^2}
$$

**p-norm aggregation** (smooth max approximation):

$$
\sigma_{PN}(p) = \left( \sum_e \sigma_{vm,e}^p \right)^{1/p}
$$

As $p \to \infty$, $\sigma_{PN} \to \max_e \sigma_{vm,e}$. Typical $p = 8$–$12$.

**KS aggregation** (Kreisselmeier-Steinhauser):

$$
\sigma_{KS}(p) = \max_e \sigma_{vm,e} + \frac{1}{p} \ln \sum_e \exp\!\left( p (\sigma_{vm,e} - \max_e \sigma_{vm,e}) \right)
$$

The shift form is numerically stable for large $p$. KS is always an upper
bound on $\max \sigma$. Typical $p = 50$–$100$.

We use the masked variant: only elements with $\rho_e \geq \rho_{\text{threshold}}$
contribute, to avoid spurious stress concentrations in low-density zones.

Module: `core/stress.py`.

References:
- Duysinx & Bendsøe (1998), "Topology optimization of continuum structures with local stress constraints", *IJNME*.
- Le, Norato, Bruns, Ha & Tortorelli (2010), "Stress-based topology optimization for continua", *SMO*.

---

## 5. BESO algorithm (Wave G)

Bidirectional Evolutionary Structural Optimization:

**Update rule**: at iteration $t$, target volume fraction is
$V^t = \max(V_{\text{target}}, V^{t-1} (1 - e_r))$
where $e_r$ is the evolutionary ratio (typical 0.01–0.05).

**Sensitivity**: $\alpha_e = \mathbf{u}_e^T \mathbf{K}_e^0 \mathbf{u}_e$
(strain energy density, no SIMP penalty term — BESO is discrete).

**Element status update**: rank all elements by filtered $\alpha_e$;
the top $\lceil V^t \cdot N_{\text{design}} \rceil$ become solid
($\rho_e = 1.0$), the rest become void ($\rho_e = \rho_{\min}$).

This is **hard kill** BESO (no soft-kill ramp). See module docstring for
the algorithmic details + how it shares utilities with SIMP.

Module: `core/beso.py::run_beso`.

Reference:
- Huang & Xie (2010), *Evolutionary Topology Optimization of Continuum Structures*, Wiley.

---

## 6. Linear solvers (Waves H and earlier)

Four backends share one interface (`adapters/solver_base.LinearSolver`):

| name | algorithm | matrix type | best for |
|---|---|---|---|
| `dense` | LAPACK `gesv` (np.linalg.solve) | numpy ndarray | small N |
| `cg` | preconditioned CG (pure NumPy) | numpy ndarray | medium N, lower memory |
| `sparse` | SuperLU (scipy.sparse.linalg.spsolve) | scipy.sparse.csr_matrix | large N, fastest |
| `sparse_cg` | scipy.sparse.linalg.cg | scipy.sparse.csr_matrix | very large N, lowest memory |

CG uses Jacobi (diagonal) preconditioning. Tolerance / max iterations are
fixed (1e-10 / 5000); make them configurable if real workflows need it.

On a 6262 DOF problem, `sparse` is **24×** faster than `dense` (see
`docs/performance.md` §v1.8).

Reference:
- Saad (2003), *Iterative Methods for Sparse Linear Systems*, SIAM.

---

## 7. Geometry export (Wave J)

**Boundary extraction**: cell-edge marching squares simplification —
emit one axis-aligned segment per (solid, void) neighbor pair or per
(solid, domain-edge) boundary. This is **not** node-value marching squares;
see `docs/decisions/D006-geometry-export-scope.md` for the design rationale.

**SVG / DXF**: each boundary segment becomes a `<line>` / `LINE` entity.

**STL** (ASCII, 2.5D extrusion): each solid cell becomes a hexahedral
prism, decomposed into 12 triangles, with interior faces suppressed for
adjacent solid cells.

Module: `core/geometry_export.py`.

Reference:
- Lorensen & Cline (1987), "Marching cubes: A high resolution 3D surface construction algorithm", *SIGGRAPH*.

---

## 8. Conventions

- **Mesh coordinates**: bottom-up (origin at lower-left), `y` increases
  upward. SVG export flips internally for screen convention.
- **Units**: model-natural (mm/N/MPa typically; `units` is metadata, no
  unit conversion applied).
- **Density**: $\rho_e \in [\rho_{\min}, 1]$; never zero (singular stiffness).
- **DOF ordering**: `[ux_0, uy_0, ux_1, uy_1, ...]` (interleaved per node).
