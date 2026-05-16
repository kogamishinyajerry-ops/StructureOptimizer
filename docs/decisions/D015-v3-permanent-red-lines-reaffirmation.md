# D015 — v3.x permanent red-lines reaffirmation

- **Status**: accepted
- **Date**: 2026-05-16
- **Wave**: R (v3.0.0)

## Context

v1.x and v2.x established a set of permanent red lines (constraints
that no wave is allowed to break). The v3.x rubric §7 carries them
forward; this ADR explicitly restates them and verifies each.

## Red lines (carried from v1.0 onward; reaffirmed v3.0)

### 1. Runtime mandatory deps = NumPy only

`pyproject.toml` `[project].dependencies`:
```toml
dependencies = [
  "numpy>=2.0",
]
```

scipy / meshio remain in `optional-dependencies` (group `sparse` /
`mesh` / `dev`). Anything that needs scipy raises a clear error message
when absent (Sobol sampler, sparse solvers, sparse_cg solver).

**Verified by**: rubric §7.1 (`grep pyproject.toml`). PASS.

### 2. No GUI / no cloud / no full 3D / no commercial solver

- No tkinter / PySide / Qt / Streamlit
- No AWS / GCP / Azure / serverless
- All FEM is 2D plane-stress (z-direction in STL export is 2.5D extrusion only)
- No Abaqus / ANSYS / Nastran / LS-DYNA license dependencies

**Verified by**: rubric §7.2 (人工 + `grep`). PASS.

### 3. Failure surface = single-line stderr + status code

Verification failures emit `ConfigError("connectivity_failed")` etc.
with the status code in the message, not a Python traceback dump. CLI
exits non-zero. `verification.json` carries the status field.

**Verified by**: `tests/test_failure_statuses.py` (existing). PASS.

### 4. v1.x rubric: still 100/100

v1.4.0's 134 tests still green; v1.x core coverage ≥ 90%; v1.x docs
(README / architecture / tutorial / ADR / CHANGELOG) intact.

**Verified by**: `pytest tests/ -q` shows all 134 v1 tests pass alongside
the new v2/v3 tests. PASS.

### 5. v2.x rubric: still ≥ 95/100

v2.0.0-final's 264 tests still green; v2.x core coverage ≥ 90%.

**Verified by**: same pytest run; 264 v2 tests pass. PASS.

### 6. Demo HTML is self-contained, single static file

`demo.html` opens locally, no network fetch, no build step, no JS
framework dependency. Wave Q added pan/zoom JS — kept as inline
vanilla JS at end of body to preserve this red line.

**Verified by**: Wave Q tests (`tests/test_repr_html_and_interactive.py`)
check that the script is inline. PASS.

### 7. No build step for CLI / Python API

`pip install -e .` works without separate compile / npm / poetry step.
setuptools only. CLI is pure Python.

**Verified by**: CI vanilla install variant succeeds. PASS.

## Red lines added in v3.x

### 8. Cross-platform bit-exact is canonical-cell only

We do not promise strict bit-exact across all OS × Python × LAPACK
build combinations. The "canonical cell" (Linux + Python 3.12 +
with-extras) is bit-exact; other cells satisfy ≤1e-9 numerical
equivalence. This is documented in D011 + tests/test_fingerprints.py
gates strict mode behind `REQUIRE_BIT_EXACT_FINGERPRINT=1`.

**Verified by**: D011 + CI workflow split. PASS.

### 9. PNG / SVG / DXF / STL all encoded by hand (no Pillow / no matplotlib)

Wave Q's `_grayscale_png_bytes` uses zlib + struct only. Wave J's SVG /
DXF / STL exporters are pure Python string formatting. No image library
dependency at runtime.

**Verified by**: `grep pyproject.toml` (no Pillow / matplotlib). PASS.

## What is NOT a red line (intentionally)

These are listed to prevent over-interpretation:

- **scipy as optional**: optional-deps are fine; only mandatory deps
  are restricted
- **meshio as optional**: same
- **Tests using scipy**: tests can `pytest.importorskip("scipy")`
- **Coverage above 92%**: target, not red line (we exceed it at 94.2%)
- **Specific algorithm support**: BESO can be removed; SIMP can be
  refactored; what matters is the red lines above
- **Performance budgets**: 5-min 500×500 is a goal, not a red line

## Reopening criteria

Any of these red lines may be reopened only by:
1. A new ADR explicitly stating why the red line no longer applies
2. User-visible documentation explaining the change
3. Maintainer review (since red lines are by definition not casual changes)

In particular: red line 1 (NumPy-only) is the most load-bearing. Any
proposal to add a mandatory runtime dep needs to clear a high bar.
