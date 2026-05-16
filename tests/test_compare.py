"""Wave V tests for comparative HTML report."""

from __future__ import annotations

from pathlib import Path

import pytest
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.compare import (
    ComparisonEntry,
    comparison_html,
    write_comparison_html,
)
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.simp import run_simp


@pytest.fixture
def two_runs():
    """Two SIMP runs on the same benchmark — used for comparison."""
    config = load_benchmark("cantilever", preset="smoke")
    mesh = create_structured_mesh(config)
    r1 = run_simp(config, mesh)
    r2 = run_simp(config, mesh)  # same config; identical result on deterministic SIMP
    return r1, r2


def test_comparison_html_requires_at_least_two_entries(two_runs):
    """Single entry → ValueError."""
    r1, _ = two_runs
    with pytest.raises(ValueError, match="≥2 entries"):
        comparison_html([ComparisonEntry(label="a", result=r1)])


def test_comparison_html_contains_labels(two_runs):
    """Labels must appear in the rendered HTML."""
    r1, r2 = two_runs
    html = comparison_html(
        [
            ComparisonEntry(label="run_alpha", result=r1),
            ComparisonEntry(label="run_beta", result=r2),
        ]
    )
    assert "run_alpha" in html
    assert "run_beta" in html


def test_comparison_html_includes_embedded_png(two_runs):
    """Density field thumbnail should be embedded as base64 PNG."""
    r1, r2 = two_runs
    html = comparison_html(
        [
            ComparisonEntry(label="A", result=r1),
            ComparisonEntry(label="B", result=r2),
        ]
    )
    # Two thumbnails → at least 2 data:image/png;base64 occurrences
    assert html.count("data:image/png;base64") == 2


def test_comparison_html_shows_metrics(two_runs):
    """Compliance, mass etc. must be rendered."""
    r1, r2 = two_runs
    html = comparison_html([ComparisonEntry(label="A", result=r1), ComparisonEntry(label="B", result=r2)])
    assert "compliance" in html
    assert "mass" in html
    assert "stop_reason" in html


def test_comparison_html_escapes_user_provided_label(two_runs):
    """A label containing <script> must be HTML-escaped."""
    r1, r2 = two_runs
    bad = "<script>alert('x')</script>"
    html = comparison_html(
        [
            ComparisonEntry(label=bad, result=r1),
            ComparisonEntry(label="safe", result=r2),
        ]
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_comparison_html_supports_notes(two_runs):
    """Notes per entry should render as italic text."""
    r1, r2 = two_runs
    html = comparison_html(
        [
            ComparisonEntry(label="A", result=r1, notes="hello note"),
            ComparisonEntry(label="B", result=r2, notes=""),
        ]
    )
    assert "hello note" in html


def test_write_comparison_html_writes_file(two_runs, tmp_path: Path):
    """File write produces a non-empty HTML document on disk."""
    r1, r2 = two_runs
    out = tmp_path / "compare.html"
    returned = write_comparison_html(
        [ComparisonEntry(label="A", result=r1), ComparisonEntry(label="B", result=r2)],
        str(out),
        title="Smoke Compare",
    )
    assert Path(returned) == out
    assert out.exists()
    text = out.read_text()
    assert "<title>Smoke Compare</title>" in text
    assert len(text) > 1000
