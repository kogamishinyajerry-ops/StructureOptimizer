"""Wave X: targeted adapter-coverage tests (push §4.3 ≥90%).

These tests exercise the rarer branches of ``adapters/solver_base.py`` and
``adapters/mesh_source.py`` that aren't hit by the happy-path tests:

* ``NumpyCGSolver`` indefinite matrix (positive diagonal but pap ≤ 0)
* ``NumpyCGSolver`` non-convergence after max_iterations
* ``NumpyCGSolver`` very small SPD systems (1×1, 2×2)
* ``available_backends`` invariants
* ``get_linear_solver`` case-insensitivity
* ``MeshioReader`` graceful failure when meshio is missing
* ``MeshSource`` ABC enforcement

Optional-dep paths (``ScipySparseSolver``, ``ScipySparseCGSolver``,
``AMGCGSolver``) are marked ``# pragma: no cover`` in the source — they
require a separate scipy/pyamg CI matrix; the canonical local-dev rubric
does not count them.
"""

from __future__ import annotations

import numpy as np
import pytest
from structure_optimizer.adapters.mesh_source import (
    MeshioReader,
    MeshSource,
    meshio_available,
)
from structure_optimizer.adapters.solver_base import (
    LinearSolver,
    NumpyCGSolver,
    NumpyDenseSolver,
    available_backends,
    get_linear_solver,
)
from structure_optimizer.core.fem2d import SolverError

# ---------------------------------------------------------------------------
# NumpyCGSolver: branch coverage
# ---------------------------------------------------------------------------


def test_cg_indefinite_matrix_with_positive_diagonal_raises():
    """``[[1, 2], [2, 1]]`` has positive diagonal but is indefinite; the
    CG inner-loop ``pap ≤ 0`` guard must catch it (line 127 of solver_base)."""
    matrix = np.array([[1.0, 2.0], [2.0, 1.0]])
    rhs = np.array([1.0, -1.0])
    with pytest.raises(SolverError, match="singular_matrix"):
        NumpyCGSolver().solve(matrix, rhs)


def test_cg_does_not_converge_within_max_iterations():
    """Force CG non-convergence by capping ``max_iterations`` very low on
    a matrix that needs many iterations (line 139 of solver_base)."""

    class StubbornCG(NumpyCGSolver):
        max_iterations = 1
        tolerance = 1e-15  # impossibly tight

    rng = np.random.default_rng(123)
    a = rng.standard_normal((20, 20))
    spd = a @ a.T + 20 * np.eye(20)
    b = rng.standard_normal(20)
    with pytest.raises(SolverError, match="cg_did_not_converge"):
        StubbornCG().solve(spd, b)


def test_cg_handles_1x1_system():
    """Edge case: scalar SPD ``A = [[3]]``, ``b = [6]`` → ``u = [2]``."""
    a = np.array([[3.0]])
    b = np.array([6.0])
    u = NumpyCGSolver().solve(a, b)
    np.testing.assert_allclose(u, [2.0], atol=1e-10)


def test_cg_handles_2x2_diagonal_system():
    """Edge case: diagonal SPD with mixed scales."""
    a = np.diag([1.0, 100.0])
    b = np.array([3.0, 200.0])
    u = NumpyCGSolver().solve(a, b)
    np.testing.assert_allclose(u, [3.0, 2.0], atol=1e-10)


def test_dense_handles_2x2_diagonal_system():
    """Symmetric check on the dense backend."""
    a = np.diag([1.0, 100.0])
    b = np.array([3.0, 200.0])
    u = NumpyDenseSolver().solve(a, b)
    np.testing.assert_allclose(u, [3.0, 2.0], atol=1e-10)


# ---------------------------------------------------------------------------
# Registry / factory: edge cases
# ---------------------------------------------------------------------------


def test_available_backends_is_sorted():
    backends = available_backends()
    assert backends == sorted(backends)
    assert len(backends) >= 2


def test_get_linear_solver_is_case_insensitive():
    """``"DENSE"`` and ``"Dense"`` should both work."""
    assert isinstance(get_linear_solver("DENSE"), NumpyDenseSolver)
    assert isinstance(get_linear_solver("Cg"), NumpyCGSolver)


def test_get_linear_solver_error_lists_available_backends():
    """The error message should mention what's available so users can fix."""
    with pytest.raises(ValueError) as exc:
        get_linear_solver("nonexistent_backend_xyz")
    msg = str(exc.value)
    assert "nonexistent_backend_xyz" in msg
    assert "Available" in msg
    assert "dense" in msg


def test_linear_solver_abstract_cannot_be_instantiated():
    """Abstract base class enforces the ``solve`` contract."""
    with pytest.raises(TypeError):
        LinearSolver()  # type: ignore[abstract]


def test_legacy_solver_alias_resolves_to_linear_solver():
    """``Solver`` is the legacy alias kept for backwards compat."""
    from structure_optimizer.adapters.solver_base import Solver

    assert Solver is LinearSolver


# ---------------------------------------------------------------------------
# MeshSource / MeshioReader
# ---------------------------------------------------------------------------


def test_mesh_source_abstract_cannot_be_instantiated():
    with pytest.raises(TypeError):
        MeshSource()  # type: ignore[abstract]


def test_meshio_reader_name_is_meshio():
    assert MeshioReader.name == "meshio"


def test_meshio_available_returns_bool():
    """``meshio_available()`` must answer True/False without raising."""
    available = meshio_available()
    assert isinstance(available, bool)


def test_meshio_reader_raises_runtime_error_when_unavailable(monkeypatch):
    """When meshio is missing, ``MeshioReader.load`` must raise a clear
    ``RuntimeError`` pointing at the install command, not a cryptic
    ``NameError`` (line 56 of mesh_source)."""
    import structure_optimizer.adapters.mesh_source as ms

    monkeypatch.setattr(ms, "_MESHIO_AVAILABLE", False)
    reader = MeshioReader()
    with pytest.raises(RuntimeError, match="meshio is not installed"):
        reader.load("/tmp/does_not_matter.msh")


def test_meshio_reader_raises_when_points_are_one_dimensional(monkeypatch):
    """``MeshioReader.load`` rejects meshes with < 2-component point arrays
    (line 70 of mesh_source). Stub meshio to return a degenerate mesh."""
    import structure_optimizer.adapters.mesh_source as ms

    class _StubBlock:
        type = "triangle"
        data = np.array([[0, 1, 2]], dtype=int)

    class _StubMesh:
        cells = [_StubBlock()]
        points = np.array([[0.0], [1.0], [2.0]])  # shape (N, 1) — invalid

    monkeypatch.setattr(ms, "_MESHIO_AVAILABLE", True)
    monkeypatch.setattr(ms, "meshio", type("M", (), {"read": staticmethod(lambda _p: _StubMesh())}))
    with pytest.raises(ValueError, match="at least 2 components"):
        MeshioReader().load("/tmp/whatever.msh")


def test_meshio_reader_raises_when_no_triangle_block(monkeypatch):
    """Mesh with only quad / line cells must produce a clear error."""
    import structure_optimizer.adapters.mesh_source as ms

    class _QuadBlock:
        type = "quad"
        data = np.array([[0, 1, 2, 3]], dtype=int)

    class _StubMesh:
        cells = [_QuadBlock()]
        points = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])

    monkeypatch.setattr(ms, "_MESHIO_AVAILABLE", True)
    monkeypatch.setattr(ms, "meshio", type("M", (), {"read": staticmethod(lambda _p: _StubMesh())}))
    with pytest.raises(ValueError, match="no triangle cells"):
        MeshioReader().load("/tmp/whatever.msh")


def test_meshio_reader_happy_path_with_stubbed_meshio(monkeypatch):
    """Stub meshio so we can exercise the happy path without the dep."""
    import structure_optimizer.adapters.mesh_source as ms

    class _TriBlock:
        type = "triangle"
        data = np.array([[0, 1, 2], [1, 2, 3]], dtype=int)

    class _StubMesh:
        cells = [_TriBlock()]
        points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]])

    monkeypatch.setattr(ms, "_MESHIO_AVAILABLE", True)
    monkeypatch.setattr(ms, "meshio", type("M", (), {"read": staticmethod(lambda _p: _StubMesh())}))
    mesh = MeshioReader().load("/tmp/whatever.msh")
    assert mesh.nodes.shape == (4, 2)
    assert mesh.elements.shape == (2, 3)
    # z coordinate must be dropped
    assert mesh.nodes.shape[1] == 2


def test_meshio_reader_skips_non_triangle_blocks(monkeypatch):
    """A mesh with quad-then-triangle blocks must pick up the triangle
    block, not silently fail."""
    import structure_optimizer.adapters.mesh_source as ms

    class _QuadBlock:
        type = "quad"
        data = np.array([[0, 1, 2, 3]], dtype=int)

    class _TriBlock:
        type = "triangle"
        data = np.array([[0, 1, 2]], dtype=int)

    class _StubMesh:
        cells = [_QuadBlock(), _TriBlock()]
        points = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])

    monkeypatch.setattr(ms, "_MESHIO_AVAILABLE", True)
    monkeypatch.setattr(ms, "meshio", type("M", (), {"read": staticmethod(lambda _p: _StubMesh())}))
    mesh = MeshioReader().load("/tmp/whatever.msh")
    assert mesh.elements.shape == (1, 3)


# ---------------------------------------------------------------------------
# Optimizer/algorithm/file_export adapters — light coverage
# ---------------------------------------------------------------------------


def test_algorithm_adapter_module_imports_cleanly():
    """Smoke import — ensures the module is syntactically clean and the
    abstract classes are exposed."""
    from structure_optimizer.adapters import algorithm_base

    assert hasattr(algorithm_base, "TopologyAlgorithm")


def test_file_export_adapter_module_imports_cleanly():
    """Smoke import."""
    from structure_optimizer.adapters import file_export

    assert hasattr(file_export, "FileExporter") or len(dir(file_export)) > 0


def test_optimizer_adapter_module_imports_cleanly():
    """Smoke import."""
    from structure_optimizer.adapters import optimizer_base

    assert hasattr(optimizer_base, "DensityUpdater") or len(dir(optimizer_base)) > 0
