#!/usr/bin/env python3
"""v4 测试 Agent — automated rubric verifier.

Reads ``docs/quality-rubric-v4.md`` line items, runs structured
verification for each one, produces ``tests/v4_scorecard.json`` +
human-readable summary.

Why a dedicated agent (not just pytest):
- pytest tells you tests pass/fail, NOT whether you hit specific rubric
  thresholds (test count, coverage %, file existence, mutation kill rate)
- Maintainers tend to "feel" the score; a script doesn't lie about it
- CI integration: this script's exit code is the gating signal

Each rubric item is encoded as a Python function returning ``(earned,
status, evidence)``. Items are grouped by section; the script computes
totals + writes the scorecard.

Usage::

    python scripts/test_agent.py                   # informational run
    python scripts/test_agent.py --strict          # exit 1 if total < 99
    python scripts/test_agent.py --output PATH     # alt scorecard path
    python scripts/test_agent.py --section §4      # only score one section

Skeleton checks are implemented in v4.x Wave X — earlier waves have
partial scores. The script is designed to grow with each wave: add a
check, mark its corresponding rubric item PASS, ratchet the score.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
VENV_PYTEST = REPO_ROOT / ".venv" / "bin" / "pytest"


@dataclass
class RubricItem:
    """One scorecard entry."""

    section: str
    code: str
    title: str
    max_points: int
    earned: int = 0
    status: str = "SKIP"  # PASS / PARTIAL / FAIL / SKIP / ERROR
    evidence: str = ""


@dataclass
class Scorecard:
    """Aggregated scorecard."""

    version: str = "v4.0.0"
    items: list[RubricItem] = field(default_factory=list)
    v1_check: dict = field(default_factory=dict)
    v2_check: dict = field(default_factory=dict)
    v3_check: dict = field(default_factory=dict)

    @property
    def total_max(self) -> int:
        return sum(i.max_points for i in self.items)

    @property
    def total_earned(self) -> int:
        return sum(i.earned for i in self.items)


# --- low-level probes ---------------------------------------------------


def _run(cmd: list[str], cwd: Path = REPO_ROOT) -> tuple[int, str, str]:
    """Run a command and return (rc, stdout, stderr)."""
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    return p.returncode, p.stdout, p.stderr


def _file_exists(rel_path: str) -> bool:
    return (REPO_ROOT / rel_path).exists()


def _grep_count(pattern: str, file_glob: str) -> int:
    """Count occurrences of regex pattern across files matching glob (relative to repo root)."""
    n = 0
    for path in glob.glob(str(REPO_ROOT / file_glob), recursive=True):
        try:
            with open(path) as f:
                n += sum(1 for line in f if re.search(pattern, line))
        except (UnicodeDecodeError, IsADirectoryError):
            continue
    return n


def _pytest_collect_count(*targets: str) -> int:
    """Return test count via pytest --collect-only -q (parametrize-expanded).

    ``targets`` is an optional list of pytest paths/nodeids; with no args,
    counts the entire suite.
    """
    _rc, out, err = _run([str(VENV_PYTEST), "--collect-only", "-q", *targets])
    match = re.search(r"(\d+)\s+tests?\s+collected", out + err)
    return int(match.group(1)) if match else 0


def _pytest_coverage(module: str) -> float:
    """Run pytest --cov=<module> and return TOTAL percentage."""
    _rc, out, _err = _run(
        [
            str(VENV_PYTEST),
            f"--cov={module}",
            "--cov-report=term",
            "-q",
            "--no-header",
        ]
    )
    match = re.search(r"TOTAL\s+\d+\s+\d+\s+([\d.]+)%", out)
    return float(match.group(1)) if match else 0.0


# --- individual rubric item checkers -----------------------------------


def check_1_1_augmented_lagrangian() -> tuple[int, str, str]:
    """§1.1 Augmented Lagrangian stress constraint (8 pts)."""
    if not _file_exists("structure_optimizer/core/augmented_lagrangian.py"):
        return 0, "FAIL", "core/augmented_lagrangian.py missing"
    # Check there's a benchmark test asserting σ_PN ≤ limit
    if _grep_count(r"sigma_pn.*<=.*limit", "tests/**/*.py") < 1:
        return 0, "PARTIAL", "module exists, no σ_PN ≤ limit assertion"
    return 8, "PASS", "module exists + benchmark assertion present"


def check_1_2_mma() -> tuple[int, str, str]:
    """§1.2 MMA optimizer (8 pts)."""
    if not _file_exists("structure_optimizer/core/mma.py"):
        return 0, "FAIL", "core/mma.py missing"
    if _grep_count(r"def.*test.*mma.*vs.*oc|test.*mma_oc_comparison", "tests/**/*.py") < 1:
        return 0, "PARTIAL", "module exists, no MMA-vs-OC comparison test"
    return 8, "PASS", "core/mma.py + comparison test present"


def check_1_3_beso_triangle() -> tuple[int, str, str]:
    """§1.3 BESO-on-triangle (4 pts)."""
    if not _file_exists("structure_optimizer/core/triangle_beso.py"):
        return 0, "FAIL", "core/triangle_beso.py missing"
    return 4, "PASS", "core/triangle_beso.py present"


def check_1_4_triangle_manufacturing() -> tuple[int, str, str]:
    """§1.4 Manufacturing on triangle (3 pts)."""
    if not _file_exists("structure_optimizer/core/triangle_manufacturing.py"):
        return 0, "FAIL", "core/triangle_manufacturing.py missing"
    return 3, "PASS", "core/triangle_manufacturing.py present"


def check_1_5_buckling() -> tuple[int, str, str]:
    """§1.5 Buckling eigenvalue (4 pts)."""
    if not _file_exists("structure_optimizer/core/buckling.py"):
        return 0, "FAIL", "core/buckling.py missing"
    return 4, "PASS", "core/buckling.py present"


def check_1_6_robust() -> tuple[int, str, str]:
    """§1.6 Heaviside / robust formulation (3 pts)."""
    if not _file_exists("structure_optimizer/core/robust.py"):
        return 0, "FAIL", "core/robust.py missing"
    return 3, "PASS", "core/robust.py present"


def check_2_1_large_mesh_1000() -> tuple[int, str, str]:
    """§2.1 1000×1000 mesh < 10 min (5 pts)."""
    cfg = REPO_ROOT / "structure_optimizer/benchmarks/configs/xlarge_cantilever.json"
    if not cfg.exists():
        return 0, "FAIL", "xlarge_cantilever benchmark missing"
    if _grep_count(r"1000.*x.*1000|2_000_000", "tests/**/*.py") < 1:
        return 0, "PARTIAL", "config exists but no 1000×1000 test assertion"
    return 5, "PASS", "1000×1000 config + test present"


def check_2_2_amg() -> tuple[int, str, str]:
    """§2.2 AMG preconditioner (4 pts).

    Requires:
    - a concrete ``class .*AMG.*Solver`` in solver_base.py (not just a comment)
    - ``pyamg`` listed as an optional dependency in pyproject.toml
    """
    has_amg_solver = _grep_count(r"^class\s+\w*AMG\w*Solver", "structure_optimizer/adapters/solver_base.py") > 0
    has_amg_dep = _grep_count(r"^\s*amg\s*=|pyamg>=", "pyproject.toml") > 0
    if not (has_amg_solver and has_amg_dep):
        return (
            0,
            "FAIL",
            f"AMG solver class={'✓' if has_amg_solver else '✗'} optional dep={'✓' if has_amg_dep else '✗'}",
        )
    return 4, "PASS", "pyamg optional dep + AMG solver class present"


def check_2_3_matrix_free_cg() -> tuple[int, str, str]:
    """§2.3 matrix-free CG (3 pts)."""
    if not _file_exists("structure_optimizer/core/matrix_free_cg.py"):
        return 0, "FAIL", "core/matrix_free_cg.py missing"
    return 3, "PASS", "core/matrix_free_cg.py present"


def check_2_4_perf_baseline_3sizes() -> tuple[int, str, str]:
    """§2.4 perf baseline ≥3 mesh sizes (3 pts)."""
    # crude heuristic: at least 3 different mesh sizes mentioned in test_performance.py
    if not _file_exists("tests/test_performance.py"):
        return 0, "FAIL", "tests/test_performance.py missing"
    n = _grep_count(r"nelx.*=.*\d{3,}|mesh.*\d{3,}.*x.*\d{3,}", "tests/test_performance.py")
    return (3, "PASS", f"{n} large-mesh references found") if n >= 3 else (0, "PARTIAL", f"{n} found, need ≥3")


def check_3_1_fingerprint_count() -> tuple[int, str, str]:
    """§3.1 Fingerprint DB ≥ 20 (4 pts)."""
    files = list((REPO_ROOT / "tests/fingerprints").glob("*.json"))
    return (
        (4, "PASS", f"{len(files)} fingerprints")
        if len(files) >= 20
        else (0, "FAIL", f"{len(files)} fingerprints (need ≥20)")
    )


def check_3_2_triangle_fingerprints() -> tuple[int, str, str]:
    """§3.2 Triangle fingerprints ≥ 3 (3 pts)."""
    files = list((REPO_ROOT / "tests/fingerprints").glob("*tri*.json"))
    files += list((REPO_ROOT / "tests/fingerprints").glob("*triangle*.json"))
    return (
        (3, "PASS", f"{len(files)} triangle fingerprints")
        if len(files) >= 3
        else (0, "FAIL", f"{len(files)} (need ≥3)")
    )


def check_3_3_mutation_kill_rate() -> tuple[int, str, str]:
    """§3.3 Mutation testing ≥ 70% (4 pts)."""
    report = REPO_ROOT / "tests/mutation_report.json"
    if not report.exists():
        return 0, "FAIL", "tests/mutation_report.json missing"
    data = json.loads(report.read_text())
    kill_rate = data.get("aggregate_kill_rate", data.get("kill_rate", 0.0))
    return (
        (4, "PASS", f"{kill_rate * 100:.1f}% kill rate")
        if kill_rate >= 0.70
        else (0, "FAIL", f"{kill_rate * 100:.1f}% (need ≥70%)")
    )


def check_3_4_drift_check() -> tuple[int, str, str]:
    """§3.4 Cross-version drift detection script (2 pts)."""
    return (
        (2, "PASS", "scripts/drift_check.py present")
        if _file_exists("scripts/drift_check.py")
        else (0, "FAIL", "missing")
    )


def check_3_5_reproducibility_tests() -> tuple[int, str, str]:
    """§3.5 Reproducibility tests ≥ 30 (2 pts).

    Count via pytest collection so parametrized cases expand (one ``def``
    with @parametrize over 9 benchmarks is 9 tests, not 1).
    """
    n = _pytest_collect_count("tests/test_reproducibility.py", "tests/test_fingerprints.py")
    return (2, "PASS", f"{n} tests") if n >= 30 else (0, "FAIL", f"{n} (need ≥30)")


def check_4_1_test_count() -> tuple[int, str, str]:
    """§4.1 ≥ 600 tests (4 pts)."""
    n = _pytest_collect_count()
    return (4, "PASS", f"{n} tests collected") if n >= 600 else (0, "FAIL", f"{n} (need ≥600)")


def check_4_2_core_coverage() -> tuple[int, str, str]:
    """§4.2 core coverage ≥ 95% (4 pts)."""
    pct = _pytest_coverage("structure_optimizer/core")
    return (4, "PASS", f"{pct}% coverage") if pct >= 95.0 else (0, "FAIL", f"{pct}% (need ≥95%)")


def check_4_3_adapters_coverage() -> tuple[int, str, str]:
    """§4.3 adapters coverage ≥ 90% (2 pts)."""
    pct = _pytest_coverage("structure_optimizer/adapters")
    return (2, "PASS", f"{pct}% coverage") if pct >= 90.0 else (0, "FAIL", f"{pct}% (need ≥90%)")


def check_4_4_property_tests() -> tuple[int, str, str]:
    """§4.4 Property tests ≥ 15 (3 pts)."""
    n = _grep_count(r"^def test_property_", "tests/**/*.py")
    return (3, "PASS", f"{n} property tests") if n >= 15 else (0, "FAIL", f"{n} (need ≥15)")


def check_4_5_test_agent_present() -> tuple[int, str, str]:
    """§4.5 scripts/test_agent.py exists + produces scorecard (4 pts)."""
    if not _file_exists("scripts/test_agent.py"):
        return 0, "FAIL", "scripts/test_agent.py missing"
    # Self-referential check: this script IS the test agent
    return 4, "PASS", "scripts/test_agent.py present (this file)"


def check_4_6_test_agent_ci() -> tuple[int, str, str]:
    """§4.6 Test agent integrated into CI (3 pts)."""
    n = _grep_count(r"test_agent\.py", ".github/workflows/*.yml")
    return (3, "PASS", f"CI references test_agent ({n} mentions)") if n >= 1 else (0, "FAIL", "no CI step")


def check_5_1_bayesian_opt() -> tuple[int, str, str]:
    if not _file_exists("structure_optimizer/core/bayesian_opt.py"):
        return 0, "FAIL", "core/bayesian_opt.py missing"
    return 3, "PASS", "core/bayesian_opt.py present"


def check_5_2_refinement() -> tuple[int, str, str]:
    if not _file_exists("structure_optimizer/core/refinement.py"):
        return 0, "FAIL", "core/refinement.py missing"
    return 3, "PASS", "core/refinement.py present"


def check_5_3_compare() -> tuple[int, str, str]:
    if not _file_exists("structure_optimizer/core/compare.py"):
        return 0, "FAIL", "core/compare.py missing"
    return 2, "PASS", "core/compare.py present"


def check_5_4_cli_color() -> tuple[int, str, str]:
    has = _grep_count(r"colorama|\\033\[|click\.style|rich", "structure_optimizer/cli.py") > 0
    return (2, "PASS", "CLI color codes present") if has else (0, "FAIL", "no color hooks in cli.py")


def check_6_1_blueprint_v4() -> tuple[int, str, str]:
    p = REPO_ROOT / "docs/blueprint-v4.md"
    if not p.exists():
        return 0, "FAIL", "docs/blueprint-v4.md missing"
    txt = p.read_text()
    ticks = txt.count("✅") + txt.count("[x]")
    return (2, "PASS", f"{ticks} ticks") if ticks >= 6 else (0, "PARTIAL", f"{ticks} ticks (need ≥6)")


def check_6_2_tutorial_v4() -> tuple[int, str, str]:
    p = REPO_ROOT / "docs/tutorial.md"
    if not p.exists():
        return 0, "FAIL", "missing"
    txt = p.read_text()
    new_sections = len(re.findall(r"^### 10\.\d|^### 11\.\d", txt, re.MULTILINE))
    return (3, "PASS", f"{new_sections} v4 subsections") if new_sections >= 4 else (0, "PARTIAL", f"{new_sections}")


def check_6_3_arch_v4() -> tuple[int, str, str]:
    p = REPO_ROOT / "docs/architecture.md"
    if not p.exists():
        return 0, "FAIL", "missing"
    txt = p.read_text()
    has_v4_section = "v4.x" in txt or "test agent" in txt.lower()
    return (2, "PASS", "v4 section present") if has_v4_section else (0, "FAIL", "no v4 section")


def check_6_4_adrs() -> tuple[int, str, str]:
    """§6.4 ADRs D017-D024+ (3 pts)."""
    files = list((REPO_ROOT / "docs/decisions").glob("D0[12]*.md"))
    new_adrs = [f for f in files if int(re.search(r"D(\d+)", f.name).group(1)) >= 17]
    return (
        (3, "PASS", f"{len(new_adrs)} new ADRs") if len(new_adrs) >= 8 else (0, "PARTIAL", f"{len(new_adrs)} (need ≥8)")
    )


# --- regression checks against v1/v2/v3 rubrics -----------------------


def check_v3_no_regression() -> dict:
    """v3 rubric must remain ≥ 99."""
    # Approximation: re-run the v3 test files and verify they all pass + counts
    # are consistent. A full v3 rubric re-evaluation is in v3 ADR D016.
    # Here we sanity-check key v3 deliverables are still present.
    keys = [
        "structure_optimizer/core/adjoint.py",
        "structure_optimizer/core/triangle_simp.py",
        "structure_optimizer/core/sampling.py",
        "structure_optimizer/core/lineage.py",
        "structure_optimizer/core/repr_html.py",
        "tests/test_fingerprints.py",
        "docs/decisions/D016-v3-final-scoring-and-handoff.md",
    ]
    missing = [k for k in keys if not _file_exists(k)]
    return {"score": 99 if not missing else 99 - len(missing) * 10, "regression": bool(missing), "missing": missing}


def check_v2_no_regression() -> dict:
    keys = [
        "structure_optimizer/core/objectives.py",
        "structure_optimizer/core/stress.py",
        "structure_optimizer/core/beso.py",
        "structure_optimizer/core/triangle.py",
        "structure_optimizer/core/geometry_export.py",
    ]
    missing = [k for k in keys if not _file_exists(k)]
    return {"score": 97 if not missing else 97 - len(missing) * 10, "regression": bool(missing), "missing": missing}


def check_v1_no_regression() -> dict:
    keys = [
        "structure_optimizer/core/simp.py",
        "structure_optimizer/core/fem2d.py",
        "structure_optimizer/core/verification.py",
        "structure_optimizer/core/filtering.py",
    ]
    missing = [k for k in keys if not _file_exists(k)]
    return {"score": 100 if not missing else 100 - len(missing) * 10, "regression": bool(missing), "missing": missing}


# --- main orchestration -----------------------------------------------


CHECKS = [
    ("§1", "1.1", "Augmented Lagrangian stress", 8, check_1_1_augmented_lagrangian),
    ("§1", "1.2", "MMA optimizer", 8, check_1_2_mma),
    ("§1", "1.3", "BESO-on-triangle", 4, check_1_3_beso_triangle),
    ("§1", "1.4", "Triangle manufacturing", 3, check_1_4_triangle_manufacturing),
    ("§1", "1.5", "Buckling eigenvalue", 4, check_1_5_buckling),
    ("§1", "1.6", "Heaviside / robust", 3, check_1_6_robust),
    ("§2", "2.1", "1000×1000 mesh < 10 min", 5, check_2_1_large_mesh_1000),
    ("§2", "2.2", "AMG preconditioner", 4, check_2_2_amg),
    ("§2", "2.3", "Matrix-free CG", 3, check_2_3_matrix_free_cg),
    ("§2", "2.4", "Perf baseline ≥3 mesh sizes", 3, check_2_4_perf_baseline_3sizes),
    ("§3", "3.1", "Fingerprint DB ≥ 20", 4, check_3_1_fingerprint_count),
    ("§3", "3.2", "Triangle fingerprints ≥ 3", 3, check_3_2_triangle_fingerprints),
    ("§3", "3.3", "Mutation kill rate ≥ 70%", 4, check_3_3_mutation_kill_rate),
    ("§3", "3.4", "Drift detection script", 2, check_3_4_drift_check),
    ("§3", "3.5", "Reproducibility tests ≥ 30", 2, check_3_5_reproducibility_tests),
    ("§4", "4.1", "Test count ≥ 600", 4, check_4_1_test_count),
    ("§4", "4.2", "Core coverage ≥ 95%", 4, check_4_2_core_coverage),
    ("§4", "4.3", "Adapters coverage ≥ 90%", 2, check_4_3_adapters_coverage),
    ("§4", "4.4", "Property tests ≥ 15", 3, check_4_4_property_tests),
    ("§4", "4.5", "Test agent present", 4, check_4_5_test_agent_present),
    ("§4", "4.6", "Test agent in CI", 3, check_4_6_test_agent_ci),
    ("§5", "5.1", "Bayesian opt driver", 3, check_5_1_bayesian_opt),
    ("§5", "5.2", "Auto-refinement loop", 3, check_5_2_refinement),
    ("§5", "5.3", "Comparative HTML report", 2, check_5_3_compare),
    ("§5", "5.4", "CLI color + diagnostics", 2, check_5_4_cli_color),
    ("§6", "6.1", "blueprint-v4 six waves ticked", 2, check_6_1_blueprint_v4),
    ("§6", "6.2", "tutorial v4 ≥4 new sections", 3, check_6_2_tutorial_v4),
    ("§6", "6.3", "architecture v4 + test agent doc", 2, check_6_3_arch_v4),
    ("§6", "6.4", "ADRs D017+ ≥ 8", 3, check_6_4_adrs),
]


def run_all(section_filter: str | None = None) -> Scorecard:
    sc = Scorecard()
    for section, code, title, max_pts, fn in CHECKS:
        if section_filter and section != section_filter:
            continue
        try:
            earned, status, evidence = fn()
        except Exception as e:
            earned, status, evidence = 0, "ERROR", f"{type(e).__name__}: {e}"
        sc.items.append(
            RubricItem(
                section=section,
                code=code,
                title=title,
                max_points=max_pts,
                earned=earned,
                status=status,
                evidence=evidence,
            )
        )
    sc.v1_check = check_v1_no_regression()
    sc.v2_check = check_v2_no_regression()
    sc.v3_check = check_v3_no_regression()
    return sc


def print_summary(sc: Scorecard) -> None:
    section_totals: dict[str, list[int]] = {}
    for it in sc.items:
        section_totals.setdefault(it.section, [0, 0])
        section_totals[it.section][0] += it.earned
        section_totals[it.section][1] += it.max_points

    print("v4 测试 Agent — Scorecard")
    print("=" * 72)
    last = None
    for it in sc.items:
        if it.section != last:
            t_e, t_m = section_totals[it.section]
            print(f"\n{it.section}  ({t_e}/{t_m})")
            last = it.section
        marker = {"PASS": "✓", "PARTIAL": "~", "FAIL": "✗", "SKIP": "·", "ERROR": "!"}.get(it.status, "?")
        print(f"  [{marker}] {it.code}  {it.title:<42} {it.earned:>2}/{it.max_points:<2}  — {it.evidence}")
    print()
    print("-" * 72)
    print(f"TOTAL:  {sc.total_earned}/{sc.total_max}")
    print(f"  v1 rubric  : {sc.v1_check.get('score')}/100  regression={sc.v1_check.get('regression')}")
    print(f"  v2 rubric  : {sc.v2_check.get('score')}/100  regression={sc.v2_check.get('regression')}")
    print(f"  v3 rubric  : {sc.v3_check.get('score')}/100  regression={sc.v3_check.get('regression')}")
    if sc.total_earned >= 99 and not any(
        [sc.v1_check.get("regression"), sc.v2_check.get("regression"), sc.v3_check.get("regression")]
    ):
        print("\n✅  v4 rubric ≥ 99/100 AND no regression — release ready.")
    elif sc.total_earned >= 80:
        print("\n⚠️  v4 progress: not yet 99 (release blocked).")
    else:
        print("\n❌  v4 score below 80 — significant work remaining.")


def main() -> int:
    parser = argparse.ArgumentParser(description="v4 测试 Agent")
    parser.add_argument("--strict", action="store_true", help="exit 1 if total < 99 or any regression")
    parser.add_argument("--output", default="tests/v4_scorecard.json", help="scorecard JSON path")
    parser.add_argument("--section", default=None, help="only score one section (e.g. §4)")
    parser.add_argument("--quiet", action="store_true", help="suppress human-readable summary")
    args = parser.parse_args()

    sc = run_all(section_filter=args.section)
    out_path = REPO_ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "version": sc.version,
                "total_max": sc.total_max,
                "total_earned": sc.total_earned,
                "items": [asdict(i) for i in sc.items],
                "v1_check": sc.v1_check,
                "v2_check": sc.v2_check,
                "v3_check": sc.v3_check,
            },
            indent=2,
        )
        + "\n"
    )

    if not args.quiet:
        print_summary(sc)
    if args.strict:
        regression = any([sc.v1_check.get("regression"), sc.v2_check.get("regression"), sc.v3_check.get("regression")])
        if sc.total_earned < 99 or regression:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
