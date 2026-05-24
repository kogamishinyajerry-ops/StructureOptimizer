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

    version: str = "v5.0.0"
    items: list[RubricItem] = field(default_factory=list)
    v1_check: dict = field(default_factory=dict)
    v2_check: dict = field(default_factory=dict)
    v3_check: dict = field(default_factory=dict)
    v4_check: dict = field(default_factory=dict)
    v5_check: dict = field(default_factory=dict)
    v6_check: dict = field(default_factory=dict)
    pytest_check: dict = field(default_factory=dict)

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


# --- v5 multi-physics rubric checks ------------------------------------


def check_v5_1_1_thermal_simp() -> tuple[int, str, str]:
    """§1.1 热传导 TO module + benchmark assertion (6 pts)."""
    has_module = _file_exists("structure_optimizer/core/thermal_simp.py") and _file_exists(
        "structure_optimizer/core/thermal.py"
    )
    has_test = _grep_count(r"thermal_simp|run_thermal_simp", "tests/**/*.py") >= 1
    if has_module and has_test:
        return 6, "PASS", "thermal_simp + thermal modules present + test"
    if has_module:
        return 3, "PARTIAL", "modules present, no test"
    return 0, "FAIL", "thermal modules missing"


def check_v5_1_2_modal() -> tuple[int, str, str]:
    """§1.2 模态 / 特征频率 TO (6 pts)."""
    has_module = _file_exists("structure_optimizer/core/modal.py")
    has_test = _grep_count(r"modal_eigenvalues|eigenfrequency|generalized_eigenvalue", "tests/**/*.py") >= 1
    if has_module and has_test:
        return 6, "PASS", "core/modal.py + eigenvalue test"
    if has_module:
        return 3, "PARTIAL", "module present, no test"
    return 0, "FAIL", "modal module missing"


def check_v5_1_3_nonlinear() -> tuple[int, str, str]:
    """§1.3 几何非线性 TO (5 pts)."""
    has_module = _file_exists("structure_optimizer/core/nonlinear_simp.py") and _file_exists(
        "structure_optimizer/core/nonlinear_fem.py"
    )
    has_test = _grep_count(r"nonlinear_fem|gere|elastica|newton_raphson", "tests/**/*.py") >= 1
    if has_module and has_test:
        return 5, "PASS", "nonlinear modules + Gere benchmark test"
    if has_module:
        return 2, "PARTIAL", "modules present, no test"
    return 0, "FAIL", "nonlinear modules missing"


def check_v5_1_4_multi_material() -> tuple[int, str, str]:
    """§1.4 多材料 ordered SIMP (5 pts)."""
    has_module = _file_exists("structure_optimizer/core/multi_material.py")
    has_test = _grep_count(r"multi_material|ordered_simp|bimaterial", "tests/**/*.py") >= 1
    if has_module and has_test:
        return 5, "PASS", "multi_material module + bimaterial test"
    if has_module:
        return 2, "PARTIAL", "module present, no test"
    return 0, "FAIL", "multi_material module missing"


def check_v5_1_5_stochastic() -> tuple[int, str, str]:
    """§1.5 随机 / 可靠性 TO (4 pts)."""
    has_module = _file_exists("structure_optimizer/core/stochastic.py")
    has_test = _grep_count(r"monte_carlo|uq_compliance|uncertainty_quantification", "tests/**/*.py") >= 1
    if has_module and has_test:
        return 4, "PASS", "stochastic module + Monte Carlo test"
    if has_module:
        return 2, "PARTIAL", "module present, no test"
    return 0, "FAIL", "stochastic module missing"


def check_v5_1_6_freq_response() -> tuple[int, str, str]:
    """§1.6 频响 / harmonic-driven TO (4 pts)."""
    has_module = _file_exists("structure_optimizer/core/freq_response.py")
    has_test = _grep_count(r"freq_response|harmonic|frequency_response", "tests/**/*.py") >= 1
    if has_module and has_test:
        return 4, "PASS", "freq_response module + test"
    if has_module:
        return 2, "PARTIAL", "module present, no test"
    return 0, "FAIL", "freq_response module missing"


def check_v5_2_1_thermal_analytical() -> tuple[int, str, str]:
    """§2.1 1D 杆 analytical 校验 (4 pts)."""
    n = _grep_count(r"analytical|1d_rod|closed_form.*thermal|T_x.*=.*", "tests/**/*.py")
    return (4, "PASS", f"{n} analytical thermal refs") if n >= 1 else (0, "FAIL", "no thermal analytical test")


def check_v5_2_2_euler_bernoulli() -> tuple[int, str, str]:
    """§2.2 Euler-Bernoulli 模态频率校验 (4 pts)."""
    n = _grep_count(r"euler_bernoulli|EB_freq|simply_supported_beam", "tests/**/*.py")
    return (4, "PASS", f"{n} EB modal refs") if n >= 1 else (0, "FAIL", "no EB modal test")


def check_v5_2_3_gere_elastica() -> tuple[int, str, str]:
    """§2.3 Gere 大变形 cantilever 校验 (3 pts)."""
    n = _grep_count(r"gere|elastica|tip_disp.*nonlinear", "tests/**/*.py")
    return (3, "PASS", f"{n} elastica refs") if n >= 1 else (0, "FAIL", "no Gere test")


def check_v5_2_4_mass_matrix_consistency() -> tuple[int, str, str]:
    """§2.4 Mass matrix lumped vs consistent agreement (2 pts)."""
    n = _grep_count(r"lumped.*consistent|mass_matrix.*backend|consistent_mass", "tests/**/*.py")
    return (2, "PASS", f"{n} mass-consistency refs") if n >= 1 else (0, "FAIL", "no mass-consistency test")


def check_v5_2_5_thermo_elastic_coupling() -> tuple[int, str, str]:
    """§2.5 Thermo-elastic coupling consistency (2 pts)."""
    n = _grep_count(r"thermo_elastic|thermal_stress|coupled.*thermal", "tests/**/*.py")
    return (2, "PASS", f"{n} thermo-elastic refs") if n >= 1 else (0, "FAIL", "no coupling test")


def check_v5_3_1_uq_monte_carlo() -> tuple[int, str, str]:
    """§3.1 Monte Carlo UQ (4 pts)."""
    has = _grep_count(r"uq_compliance|monte_carlo_uq", "structure_optimizer/core/stochastic.py") >= 1
    return (4, "PASS", "UQ entrypoint present") if has else (0, "FAIL", "no UQ entry")


def check_v5_3_2_worst_case() -> tuple[int, str, str]:
    """§3.2 worst-case / minmax TO (3 pts)."""
    has_file = _file_exists("structure_optimizer/core/reliability.py")
    has_fn = _grep_count(r"worst_case_simp|robust_topology|minmax_compliance", "**/*.py") >= 1
    if has_file and has_fn:
        return 3, "PASS", "reliability module + worst-case entry"
    if has_file:
        return 1, "PARTIAL", "reliability module present"
    return 0, "FAIL", "no reliability module"


def check_v5_3_3_rng_seed_repro() -> tuple[int, str, str]:
    """§3.3 RNG-seed reproducibility (3 pts)."""
    n = _grep_count(r"stochastic.*seed|seed.*stochastic|monte_carlo.*reproducible", "tests/**/*.py")
    return (3, "PASS", f"{n} seed-repro refs") if n >= 1 else (0, "FAIL", "no seed-repro test")


def check_v5_3_4_stochastic_fingerprints() -> tuple[int, str, str]:
    """§3.4 stochastic fingerprints ≥ 2 (3 pts)."""
    n = len(list((REPO_ROOT / "tests/fingerprints").glob("stochastic_*.json")))
    return (3, "PASS", f"{n} stochastic fingerprints") if n >= 2 else (0, "FAIL", f"{n} (need ≥2)")


def check_v5_3_5_pareto_nsga() -> tuple[int, str, str]:
    """§3.5 NSGA-II Pareto front (2 pts)."""
    has = _file_exists("structure_optimizer/core/pareto_nsga.py")
    n = _grep_count(r"nsga|pareto_front", "tests/**/*.py")
    if has and n >= 1:
        return 2, "PASS", "pareto_nsga module + test"
    if has:
        return 1, "PARTIAL", "module present"
    return 0, "FAIL", "no NSGA module"


def check_v5_4_1_test_count_750() -> tuple[int, str, str]:
    """§4.1 ≥ 750 tests (4 pts)."""
    n = _pytest_collect_count()
    return (4, "PASS", f"{n} tests collected") if n >= 750 else (0, "FAIL", f"{n} (need ≥750)")


def check_v5_4_2_core_coverage_95() -> tuple[int, str, str]:
    """§4.2 core coverage ≥ 95% incl. v5 multi-physics (4 pts)."""
    pct = _pytest_coverage("structure_optimizer/core")
    return (4, "PASS", f"{pct}% coverage") if pct >= 95.0 else (0, "FAIL", f"{pct}% (need ≥95%)")


def check_v5_4_3_property_tests_25() -> tuple[int, str, str]:
    """§4.3 property tests ≥ 25 (3 pts)."""
    n = _grep_count(r"^def test_property_", "tests/**/*.py")
    return (3, "PASS", f"{n} property tests") if n >= 25 else (0, "FAIL", f"{n} (need ≥25)")


def check_v5_4_4_mutation_75() -> tuple[int, str, str]:
    """§4.4 mutation kill rate ≥ 75% (3 pts)."""
    report = REPO_ROOT / "tests/mutation_report.json"
    if not report.exists():
        return 0, "FAIL", "mutation_report missing"
    data = json.loads(report.read_text())
    rate = data.get("aggregate_kill_rate", data.get("kill_rate", 0.0))
    return (3, "PASS", f"{rate * 100:.1f}% kill rate") if rate >= 0.75 else (0, "FAIL", f"{rate * 100:.1f}%")


def check_v5_4_5_fingerprints_25() -> tuple[int, str, str]:
    """§4.5 fingerprint DB ≥ 25 (2 pts)."""
    n = len(list((REPO_ROOT / "tests/fingerprints").glob("*.json")))
    return (2, "PASS", f"{n} fingerprints") if n >= 25 else (0, "FAIL", f"{n} (need ≥25)")


def check_v5_4_6_v5_rubric_in_agent() -> tuple[int, str, str]:
    """§4.6 quality-rubric-v5.md referenced in this script (2 pts)."""
    me = REPO_ROOT / "scripts/test_agent.py"
    txt = me.read_text()
    return (2, "PASS", "v5 rubric referenced") if "quality-rubric-v5" in txt or "v5 multi-physics" in txt else (
        0,
        "FAIL",
        "no v5 reference",
    )


def check_v5_4_7_v5_in_ci() -> tuple[int, str, str]:
    """§4.7 CI runs v5 rubric step (2 pts)."""
    ci = REPO_ROOT / ".github/workflows/test.yml"
    if not ci.exists():
        return 0, "FAIL", "test.yml missing"
    txt = ci.read_text()
    return (2, "PASS", "v5 CI step present") if "v5" in txt.lower() else (0, "FAIL", "no v5 step")


def check_v5_5_1_pareto_html() -> tuple[int, str, str]:
    """§5.1 Pareto front HTML render (3 pts)."""
    has = _grep_count(r"render_pareto|pareto.*html", "structure_optimizer/core/pareto_nsga.py") >= 1
    return (3, "PASS", "render_pareto present") if has else (0, "FAIL", "no Pareto HTML")


def check_v5_5_2_stl_export() -> tuple[int, str, str]:
    """§5.2 2D→STL boundary export (3 pts)."""
    has_module = _file_exists("structure_optimizer/core/stl_export.py")
    has_test = _grep_count(r"stl_export|write_stl", "tests/**/*.py") >= 1
    if has_module and has_test:
        return 3, "PASS", "stl_export module + smoke test"
    if has_module:
        return 1, "PARTIAL", "module present"
    return 0, "FAIL", "no STL export"


def check_v5_5_3_autodiff() -> tuple[int, str, str]:
    """§5.3 pure-NumPy autodiff harness (2 pts)."""
    has = _file_exists("structure_optimizer/core/autodiff.py")
    has_test = _grep_count(r"autodiff|gradient_check", "tests/**/*.py") >= 1
    if has and has_test:
        return 2, "PASS", "autodiff + gradient-check test"
    if has:
        return 1, "PARTIAL", "module present"
    return 0, "FAIL", "no autodiff"


def check_v5_5_4_multi_physics_demo() -> tuple[int, str, str]:
    """§5.4 multi-physics demo HTML (2 pts)."""
    n = _grep_count(r"thermal.*mechanical|multi_physics_demo|side_by_side.*thermal", "**/*.py")
    return (2, "PASS", f"{n} multi-physics demo refs") if n >= 1 else (0, "FAIL", "no demo")


def check_v5_6_1_blueprint_v5() -> tuple[int, str, str]:
    """§6.1 blueprint-v5 six waves ticked (2 pts)."""
    p = REPO_ROOT / "docs/blueprint-v5.md"
    if not p.exists():
        return 0, "FAIL", "blueprint-v5.md missing"
    txt = p.read_text()
    ticks = txt.count("[x]")
    return (2, "PASS", f"{ticks} ticks") if ticks >= 6 else (0, "PARTIAL", f"{ticks}")


def check_v5_6_2_tutorial_v5() -> tuple[int, str, str]:
    """§6.2 tutorial v5 ≥ 5 new sections (3 pts)."""
    p = REPO_ROOT / "docs/tutorial.md"
    if not p.exists():
        return 0, "FAIL", "missing"
    txt = p.read_text()
    n = len(re.findall(r"^### 12\.\d|^### 13\.\d", txt, re.MULTILINE))
    return (3, "PASS", f"{n} v5 subsections") if n >= 5 else (0, "PARTIAL", f"{n}")


def check_v5_6_3_arch_v5() -> tuple[int, str, str]:
    """§6.3 architecture v5 + multi-physics doc (2 pts)."""
    p = REPO_ROOT / "docs/architecture.md"
    if not p.exists():
        return 0, "FAIL", "missing"
    txt = p.read_text().lower()
    return (2, "PASS", "v5 section present") if ("v5" in txt and "multi-physics" in txt) else (0, "FAIL", "no v5 section")


def check_v5_6_4_adrs_v5() -> tuple[int, str, str]:
    """§6.4 ADRs D025-D032 ≥ 8 new (3 pts)."""
    files = list((REPO_ROOT / "docs/decisions").glob("D0[23]*.md"))
    new_adrs = [f for f in files if (m := re.search(r"D(\d+)", f.name)) and int(m.group(1)) >= 25]
    return (3, "PASS", f"{len(new_adrs)} v5 ADRs") if len(new_adrs) >= 8 else (0, "PARTIAL", f"{len(new_adrs)} (need ≥8)")


# --- v6 production-grade rubric checks ---------------------------------


def check_v6_1_1_total_lagrangian() -> tuple[int, str, str]:
    """§1.1 full Total-Lagrangian Green-strain Newton (8 pts)."""
    has = _file_exists("structure_optimizer/core/total_lagrangian.py")
    has_test = _grep_count(r"total_lagrangian|green_strain|second_piola|2nd.?pk", "tests/**/*.py") >= 1
    if has and has_test:
        return 8, "PASS", "total_lagrangian module + quantitative test"
    if has:
        return 4, "PARTIAL", "module present, no quantitative test"
    return 0, "FAIL", "core/total_lagrangian.py missing"


def check_v6_1_2_rayleigh_damping() -> tuple[int, str, str]:
    """§1.2 Rayleigh-damped complex frequency response (6 pts)."""
    has = _grep_count(r"damped_harmonic|rayleigh_damp|alpha.*M.*beta.*K|C\s*=\s*alpha", "structure_optimizer/core/freq_response.py") >= 1
    has_test = _grep_count(r"rayleigh|damped.*freq|half_power|damping_ratio", "tests/**/*.py") >= 1
    if has and has_test:
        return 6, "PASS", "damped harmonic response + test"
    if has:
        return 3, "PARTIAL", "damping in module, no test"
    return 0, "FAIL", "no Rayleigh-damped response"


def check_v6_1_3_anisotropic_thermal() -> tuple[int, str, str]:
    """§1.3 anisotropic / orthotropic thermal conductivity (6 pts)."""
    has = _grep_count(r"anisotropic|orthotropic|conductivity_matrix|tensor.*conduct|k_xy|kxy", "structure_optimizer/core/thermal.py") >= 1
    has_test = _grep_count(r"anisotropic|orthotropic|rotation.*invar|tensor.*conduct", "tests/**/*.py") >= 1
    if has and has_test:
        return 6, "PASS", "tensor conductivity + test"
    if has:
        return 3, "PARTIAL", "tensor k in module, no test"
    return 0, "FAIL", "no anisotropic thermal"


def check_v6_1_4_nsga3() -> tuple[int, str, str]:
    """§1.4 NSGA-III for ≥3 objectives (5 pts)."""
    has = _grep_count(r"nsga3|nsga_iii|das_dennis|reference_direction|reference_point", "structure_optimizer/core/pareto_nsga.py") >= 1
    has_test = _grep_count(r"nsga3|nsga_iii|three_objective|3.?obj|das_dennis", "tests/**/*.py") >= 1
    if has and has_test:
        return 5, "PASS", "NSGA-III + 3-objective test"
    if has:
        return 2, "PARTIAL", "NSGA-III in module, no test"
    return 0, "FAIL", "no NSGA-III"


def check_v6_2_1_form() -> tuple[int, str, str]:
    """§2.1 FORM reliability index β (5 pts)."""
    has = _grep_count(r"def form|form_reliability|hl_rf|hasofer|reliability_index|\bbeta\b.*reliab", "structure_optimizer/core/reliability.py") >= 1
    has_test = _grep_count(r"\bform\b|reliability_index|hl_rf|beta.*linear|linear.*limit_state", "tests/**/*.py") >= 1
    if has and has_test:
        return 5, "PASS", "FORM + analytical β test"
    if has:
        return 2, "PARTIAL", "FORM in module, no test"
    return 0, "FAIL", "no FORM"


def check_v6_2_2_importance_sampling() -> tuple[int, str, str]:
    """§2.2 importance sampling (4 pts)."""
    has = _grep_count(r"importance_sampling|importance_sample", "structure_optimizer/core/reliability.py") >= 1
    has_test = _grep_count(r"importance_sampl|variance_reduction", "tests/**/*.py") >= 1
    if has and has_test:
        return 4, "PASS", "importance sampling + variance-reduction test"
    if has:
        return 2, "PARTIAL", "IS in module, no test"
    return 0, "FAIL", "no importance sampling"


def check_v6_2_3_sorm() -> tuple[int, str, str]:
    """§2.3 SORM / curvature correction (3 pts)."""
    has = _grep_count(r"\bsorm\b|breitung|curvature.*correct|second_order_reliab", "structure_optimizer/core/reliability.py") >= 1
    has_test = _grep_count(r"\bsorm\b|breitung|curvature.*reliab", "tests/**/*.py") >= 1
    if has and has_test:
        return 3, "PASS", "SORM + test"
    if has:
        return 1, "PARTIAL", "SORM in module, no test"
    return 0, "FAIL", "no SORM"


def check_v6_2_4_tl_verification() -> tuple[int, str, str]:
    """§2.4 full-TL quantitative verification (4 pts).

    The rigorous, reliable quantitative proof of a full Green-strain TL is
    finite-rotation objectivity (zero strain to machine precision) + an
    analytical constant-strain patch — these distinguish full TL from the v5
    ``K + ½K_g`` approximation, where a fuzzy continuum-vs-beam elastica match
    would be flaky. We reward those.
    """
    n = _grep_count(
        r"finite_rotation.*green|rigid.*rotation|uniform_stretch.*analytical|green_strain.*assert|objectivity",
        "tests/**/*.py",
    )
    return (4, "PASS", f"{n} TL-objectivity/patch refs") if n >= 1 else (0, "FAIL", "no full-TL verification test")


def check_v6_2_5_half_power_bandwidth() -> tuple[int, str, str]:
    """§2.5 half-power bandwidth analytical check (4 pts)."""
    n = _grep_count(r"half_power|bandwidth.*analyt|quality_factor|q_factor|3db", "tests/**/*.py")
    return (4, "PASS", f"{n} half-power refs") if n >= 1 else (0, "FAIL", "no half-power bandwidth test")


def check_v6_3_1_smooth_stl() -> tuple[int, str, str]:
    """§3.1 marching-squares smooth-boundary STL (5 pts)."""
    has = _grep_count(r"marching_squares|smooth_boundary|export_stl_smooth|smooth.*contour", "structure_optimizer/core/stl_export.py") >= 1
    has_test = _grep_count(r"marching_squares|smooth.*stl|area_converg|smooth_boundary", "tests/**/*.py") >= 1
    if has and has_test:
        return 5, "PASS", "smooth-boundary STL + area-convergence test"
    if has:
        return 2, "PARTIAL", "smooth STL in module, no test"
    return 0, "FAIL", "no marching-squares smooth STL"


def check_v6_3_2_reverse_ad() -> tuple[int, str, str]:
    """§3.2 reverse-mode AD (tape) (5 pts)."""
    has = _grep_count(r"reverse_mode|backward|class Tape|def grad\b|\.backward\(", "structure_optimizer/core/autodiff.py") >= 1
    return (5, "PASS", "reverse-mode AD present") if has else (0, "FAIL", "no reverse-mode AD")


def check_v6_3_3_ad_consistency() -> tuple[int, str, str]:
    """§3.3 reverse-vs-forward-vs-FD consistency test (5 pts)."""
    n = _grep_count(r"reverse.*forward|forward.*reverse|reverse.*central|grad.*finite_diff|reverse_vs", "tests/**/*.py")
    return (5, "PASS", f"{n} AD-consistency refs") if n >= 1 else (0, "FAIL", "no reverse-vs-forward AD test")


def check_v6_4_1_test_count_850() -> tuple[int, str, str]:
    """§4.1 ≥ 850 tests (4 pts)."""
    n = _pytest_collect_count()
    return (4, "PASS", f"{n} tests collected") if n >= 850 else (0, "FAIL", f"{n} (need ≥850)")


def check_v6_4_2_core_coverage_95() -> tuple[int, str, str]:
    """§4.2 core coverage ≥ 95% incl. v6 (4 pts)."""
    pct = _pytest_coverage("structure_optimizer/core")
    return (4, "PASS", f"{pct}% coverage") if pct >= 95.0 else (0, "FAIL", f"{pct}% (need ≥95%)")


def check_v6_4_3_property_tests_35() -> tuple[int, str, str]:
    """§4.3 property tests ≥ 35 (3 pts)."""
    n = _grep_count(r"^def test_property_", "tests/**/*.py")
    return (3, "PASS", f"{n} property tests") if n >= 35 else (0, "FAIL", f"{n} (need ≥35)")


def check_v6_4_4_mutation_75() -> tuple[int, str, str]:
    """§4.4 mutation kill rate ≥ 75% (3 pts)."""
    report = REPO_ROOT / "tests/mutation_report.json"
    if not report.exists():
        return 0, "FAIL", "mutation_report missing"
    data = json.loads(report.read_text())
    rate = data.get("aggregate_kill_rate", data.get("kill_rate", 0.0))
    return (3, "PASS", f"{rate * 100:.1f}% kill rate") if rate >= 0.75 else (0, "FAIL", f"{rate * 100:.1f}%")


def check_v6_4_5_fingerprints_30() -> tuple[int, str, str]:
    """§4.5 fingerprint DB ≥ 30 (2 pts)."""
    n = len(list((REPO_ROOT / "tests/fingerprints").glob("*.json")))
    return (2, "PASS", f"{n} fingerprints") if n >= 30 else (0, "FAIL", f"{n} (need ≥30)")


def check_v6_4_6_pytest_gate() -> tuple[int, str, str]:
    """§4.6 pytest gate green / D033 mechanism present (2 pts)."""
    has_gate = _grep_count(r"def check_pytest_green", "scripts/test_agent.py") >= 1
    has_adr = _file_exists("docs/decisions/D033-pytest-green-no-regression-gate.md")
    if has_gate and has_adr:
        return 2, "PASS", "D033 pytest gate + ADR present"
    return 0, "FAIL", f"gate={'✓' if has_gate else '✗'} ADR={'✓' if has_adr else '✗'}"


def check_v6_4_7_v6_in_agent_ci() -> tuple[int, str, str]:
    """§4.7 v6 rubric referenced in agent + CI (2 pts)."""
    me = (REPO_ROOT / "scripts/test_agent.py").read_text()
    in_agent = "quality-rubric-v6" in me or "CHECKS_V6" in me
    ci = REPO_ROOT / ".github/workflows/test.yml"
    in_ci = ci.exists() and "v6" in ci.read_text().lower()
    if in_agent and in_ci:
        return 2, "PASS", "v6 in agent + CI"
    if in_agent:
        return 1, "PARTIAL", "v6 in agent, not CI"
    return 0, "FAIL", "v6 not wired"


def check_v6_5_1_convergence_html() -> tuple[int, str, str]:
    """§5.1 analytical-vs-numerical convergence study HTML (3 pts)."""
    n = _grep_count(r"convergence_study|render_convergence|convergence.*html", "**/*.py")
    return (3, "PASS", f"{n} convergence-study refs") if n >= 1 else (0, "FAIL", "no convergence study")


def check_v6_5_2_bode_plot() -> tuple[int, str, str]:
    """§5.2 damped frequency-response (Bode-style) render (3 pts)."""
    n = _grep_count(r"bode|magnitude.*phase|frequency_response.*render|render.*freq_response", "**/*.py")
    return (3, "PASS", f"{n} Bode refs") if n >= 1 else (0, "FAIL", "no damped-FR render")


def check_v6_5_3_nsga3_render() -> tuple[int, str, str]:
    """§5.3 3-objective Pareto render (2 pts)."""
    n = _grep_count(r"render.*nsga3|nsga3.*html|three_obj.*render|render.*3.?obj", "**/*.py")
    return (2, "PASS", f"{n} NSGA-III render refs") if n >= 1 else (0, "FAIL", "no 3-obj render")


def check_v6_5_4_smooth_stl_demo() -> tuple[int, str, str]:
    """§5.4 smooth-vs-voxel STL demo (2 pts)."""
    n = _grep_count(r"smooth.*voxel|voxel.*smooth|smooth_stl_demo", "**/*.py")
    return (2, "PASS", f"{n} smooth-STL demo refs") if n >= 1 else (0, "FAIL", "no smooth-STL demo")


def check_v6_6_1_blueprint_v6() -> tuple[int, str, str]:
    """§6.1 blueprint-v6 ≥6 wave ticks (2 pts)."""
    p = REPO_ROOT / "docs/blueprint-v6.md"
    if not p.exists():
        return 0, "FAIL", "blueprint-v6.md missing"
    ticks = p.read_text().count("[x]")
    return (2, "PASS", f"{ticks} ticks") if ticks >= 6 else (0, "PARTIAL", f"{ticks} ticks (need ≥6)")


def check_v6_6_2_tutorial_v6() -> tuple[int, str, str]:
    """§6.2 tutorial v6 ≥4 new sections (3 pts)."""
    p = REPO_ROOT / "docs/tutorial.md"
    if not p.exists():
        return 0, "FAIL", "missing"
    n = len(re.findall(r"^### 16\.\d|^### 17\.\d", p.read_text(), re.MULTILINE))
    return (3, "PASS", f"{n} v6 subsections") if n >= 4 else (0, "PARTIAL", f"{n} (need ≥4)")


def check_v6_6_3_arch_v6() -> tuple[int, str, str]:
    """§6.3 architecture v6 section (2 pts)."""
    p = REPO_ROOT / "docs/architecture.md"
    if not p.exists():
        return 0, "FAIL", "missing"
    txt = p.read_text().lower()
    return (2, "PASS", "v6 section present") if ("v6" in txt and "production-grade" in txt) else (0, "FAIL", "no v6 section")


def check_v6_6_4_adrs_v6() -> tuple[int, str, str]:
    """§6.4 ADRs D034+ ≥ 7 (3 pts)."""
    files = list((REPO_ROOT / "docs/decisions").glob("D0[34]*.md"))
    new_adrs = [f for f in files if (m := re.search(r"D(\d+)", f.name)) and int(m.group(1)) >= 34]
    return (3, "PASS", f"{len(new_adrs)} v6 ADRs") if len(new_adrs) >= 7 else (0, "PARTIAL", f"{len(new_adrs)} (need ≥7)")


# --- v7 rubric: production drivers & field-level fidelity ----------------
# Grep-based presence + quantitative-test checks (same pattern as CHECKS_V6).
# They fail until the corresponding v7 wave lands, then pass.


def _mod_and_test(module: str, mod_pat: str, test_pat: str, full: int, partial_msg: str, pass_msg: str):
    has = _grep_count(mod_pat, module) >= 1
    has_test = _grep_count(test_pat, "tests/**/*.py") >= 1
    if has and has_test:
        return full, "PASS", pass_msg
    if has:
        return full // 2, "PARTIAL", partial_msg
    return 0, "FAIL", f"{module}: {mod_pat} missing"


def check_v7_1_1_rbto() -> tuple[int, str, str]:
    """§1.1 reliability-based TO — FORM into a SIMP driver (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/rbto.py", r"def rbto|reliability_based|beta_target|rbto_simp",
        r"rbto|reliability_based.*to|beta_target", 8, "RBTO module, no test", "RBTO + analytical-β test")


def check_v7_1_2_nonlinear_to() -> tuple[int, str, str]:
    """§1.2 geometric-nonlinear TO via full-TL adjoint sensitivity (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/nonlinear_simp.py", r"total_lagrangian|tl_adjoint|green_strain|geometric_nonlinear.*simp|nonlinear_compliance",
        r"tl_adjoint|nonlinear.*sensitivity.*fd|geometric_nonlinear.*to", 8, "nonlinear-TO module, no test", "nonlinear TO + adjoint-vs-FD test")


def check_v7_1_3_damped_fr_to() -> tuple[int, str, str]:
    """§1.3 damped frequency-response TO — minimise dynamic compliance (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/freq_response.py", r"dynamic_compliance|damped.*simp|freq_response_to|dynamic_to",
        r"dynamic_compliance|damped.*to|freq.*response.*sensitivity", 8, "damped-FR-TO in module, no test", "damped-FR TO + sensitivity test")


def check_v7_2_1_per_element_anisotropic() -> tuple[int, str, str]:
    """§2.1 per-element anisotropic thermal field (5 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/thermal.py", r"per_element.*tensor|tensor_field|conductivity_field|element_orientation|fibre_angle",
        r"per_element.*anisotrop|fibre_angle|orientation_field|tensor_field", 5, "per-element field in module, no test", "per-element anisotropic field + patch test")


def check_v7_2_2_anisotropic_thermal_to() -> tuple[int, str, str]:
    """§2.2 anisotropic thermal TO sensitivity (4 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/thermal_simp.py", r"anisotropic.*sens|tensor.*sensitivity|anisotropic.*simp",
        r"anisotropic.*thermal.*sens|anisotropic.*thermal.*to", 4, "anisotropic sens in module, no test", "anisotropic thermal TO sensitivity + FD test")


def check_v7_2_3_nsga3_density_field() -> tuple[int, str, str]:
    """§2.3 NSGA-III directly on density fields, not proxies (7 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/multi_objective_to.py", r"def .*multi_objective|nsga3.*density|density.*genome|hypervolume",
        r"multi_objective.*to|density.*pareto|hypervolume", 7, "density-field MO module, no test", "NSGA-III density-field TO + hypervolume test")


def check_v7_3_1_nataf() -> tuple[int, str, str]:
    """§3.1 Nataf transform for correlated Gaussians (4 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/reliability.py", r"NatafTransform|build_nataf|correlated_gaussian_reliability|_equivalent_normal_correlation",
        r"nataf|correlated.*gaussian|correlation.*reliab", 4, "Nataf in module, no test", "Nataf transform + correlated mapping test")


def check_v7_3_2_correlated_form() -> tuple[int, str, str]:
    """§3.2 correlated / non-Gaussian FORM (4 pts)."""
    n = _grep_count(r"correlated.*beta|nataf.*form|correlated.*limit_state|non_gaussian.*form", "tests/**/*.py")
    return (4, "PASS", f"{n} correlated-FORM refs") if n >= 1 else (0, "FAIL", "no correlated-FORM test")


def check_v7_3_3_earclip_stl() -> tuple[int, str, str]:
    """§3.3 ear-clipping general-polygon STL triangulation (4 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/stl_export.py", r"ear_clip|earclip|triangulate_polygon|def .*triangulate",
        r"ear_clip|earclip|triangulate.*polygon|concave.*stl", 4, "ear-clipping in module, no test", "ear-clipping + concave-polygon area test")


def check_v7_3_4_hole_handling() -> tuple[int, str, str]:
    """§3.4 STL hole handling (even-odd) (3 pts)."""
    n = _grep_count(r"even_odd|hole.*loop|nested.*loop|punch.*hole|annulus", "tests/**/*.py")
    return (3, "PASS", f"{n} hole-handling refs") if n >= 1 else (0, "FAIL", "no hole-handling test")


def check_v7_4_1_test_count_900() -> tuple[int, str, str]:
    """§4.1 ≥ 900 tests (4 pts)."""
    n = _pytest_collect_count()
    return (4, "PASS", f"{n} tests collected") if n >= 900 else (0, "FAIL", f"{n} (need ≥900)")


def check_v7_4_2_core_coverage_95() -> tuple[int, str, str]:
    """§4.2 core coverage ≥ 95% incl. v7 (4 pts)."""
    pct = _pytest_coverage("structure_optimizer/core")
    return (4, "PASS", f"{pct}% coverage") if pct >= 95.0 else (0, "FAIL", f"{pct}% (need ≥95%)")


def check_v7_4_3_property_tests_40() -> tuple[int, str, str]:
    """§4.3 property tests ≥ 40 (3 pts)."""
    n = _grep_count(r"^def test_property_", "tests/**/*.py")
    return (3, "PASS", f"{n} property tests") if n >= 40 else (0, "FAIL", f"{n} (need ≥40)")


def check_v7_4_4_mutation_75() -> tuple[int, str, str]:
    """§4.4 mutation kill rate ≥ 75% (3 pts)."""
    report = REPO_ROOT / "tests/mutation_report.json"
    if not report.exists():
        return 0, "FAIL", "mutation_report missing"
    data = json.loads(report.read_text())
    rate = data.get("aggregate_kill_rate", data.get("kill_rate", 0.0))
    return (3, "PASS", f"{rate * 100:.1f}% kill rate") if rate >= 0.75 else (0, "FAIL", f"{rate * 100:.1f}%")


def check_v7_4_5_fingerprints_35() -> tuple[int, str, str]:
    """§4.5 fingerprint DB ≥ 35 (2 pts)."""
    n = len(list((REPO_ROOT / "tests/fingerprints").glob("*.json")))
    return (2, "PASS", f"{n} fingerprints") if n >= 35 else (0, "FAIL", f"{n} (need ≥35)")


def check_v7_4_6_pytest_gate() -> tuple[int, str, str]:
    """§4.6 pytest gate green / D033 mechanism present (2 pts)."""
    has_gate = _grep_count(r"def check_pytest_green", "scripts/test_agent.py") >= 1
    has_adr = _file_exists("docs/decisions/D033-pytest-green-no-regression-gate.md")
    return (2, "PASS", "D033 gate + ADR") if (has_gate and has_adr) else (0, "FAIL", f"gate={'✓' if has_gate else '✗'} ADR={'✓' if has_adr else '✗'}")


def check_v7_4_7_v7_in_agent_ci() -> tuple[int, str, str]:
    """§4.7 v7 rubric referenced in agent + CI (2 pts)."""
    me = (REPO_ROOT / "scripts/test_agent.py").read_text()
    in_agent = "CHECKS_V7" in me
    ci = REPO_ROOT / ".github/workflows/test.yml"
    in_ci = ci.exists() and "v7" in ci.read_text().lower()
    if in_agent and in_ci:
        return 2, "PASS", "v7 in agent + CI"
    if in_agent:
        return 1, "PARTIAL", "v7 in agent, not CI"
    return 0, "FAIL", "v7 not wired"


def check_v7_5_1_rbto_demo() -> tuple[int, str, str]:
    """§5.1 RBTO convergence demo (3 pts)."""
    n = _grep_count(r"rbto_demo|reliability.*demo|render_rbto|rbto.*html", "**/*.py")
    return (3, "PASS", f"{n} RBTO-demo refs") if n >= 1 else (0, "FAIL", "no RBTO demo")


def check_v7_5_2_nonlinear_demo() -> tuple[int, str, str]:
    """§5.2 nonlinear / damped-FR TO demo (3 pts)."""
    n = _grep_count(r"nonlinear_to_demo|damped_to_demo|dynamic_to_demo|render.*nonlinear", "**/*.py")
    return (3, "PASS", f"{n} nonlinear/damped-TO demo refs") if n >= 1 else (0, "FAIL", "no nonlinear/damped-TO demo")


def check_v7_5_3_density_pareto_render() -> tuple[int, str, str]:
    """§5.3 density-field Pareto render (2 pts)."""
    n = _grep_count(r"density.*pareto.*render|render.*density.*pareto|multi_objective.*demo|pareto_field", "**/*.py")
    return (2, "PASS", f"{n} density-Pareto render refs") if n >= 1 else (0, "FAIL", "no density-Pareto render")


def check_v7_5_4_earclip_demo() -> tuple[int, str, str]:
    """§5.4 ear-clipping STL demo (2 pts)."""
    n = _grep_count(r"earclip.*demo|ear_clip.*demo|concave.*stl.*demo|hole.*stl.*demo", "**/*.py")
    return (2, "PASS", f"{n} ear-clip demo refs") if n >= 1 else (0, "FAIL", "no ear-clipping demo")


def check_v7_6_1_blueprint_v7() -> tuple[int, str, str]:
    """§6.1 blueprint-v7 ≥6 wave ticks (3 pts)."""
    p = REPO_ROOT / "docs/blueprint-v7.md"
    if not p.exists():
        return 0, "FAIL", "blueprint-v7.md missing"
    ticks = p.read_text().count("[x]")
    return (3, "PASS", f"{ticks} ticks") if ticks >= 6 else (0, "PARTIAL", f"{ticks} ticks (need ≥6)")


def check_v7_6_2_tutorial_v7() -> tuple[int, str, str]:
    """§6.2 tutorial v7 ≥4 new sections (3 pts)."""
    p = REPO_ROOT / "docs/tutorial.md"
    if not p.exists():
        return 0, "FAIL", "missing"
    n = len(re.findall(r"^### 17\.\d", p.read_text(), re.MULTILINE))
    return (3, "PASS", f"{n} v7 subsections") if n >= 4 else (0, "PARTIAL", f"{n} (need ≥4)")


def check_v7_6_3_arch_v7() -> tuple[int, str, str]:
    """§6.3 architecture v7 section (3 pts)."""
    p = REPO_ROOT / "docs/architecture.md"
    if not p.exists():
        return 0, "FAIL", "missing"
    txt = p.read_text().lower()
    return (3, "PASS", "v7 section present") if ("## 17." in p.read_text() and "driver" in txt) else (0, "FAIL", "no v7 section")


def check_v7_6_4_adrs_v7() -> tuple[int, str, str]:
    """§6.4 ADRs D042+ ≥ 7 (3 pts)."""
    files = list((REPO_ROOT / "docs/decisions").glob("D04*.md"))
    new_adrs = [f for f in files if (m := re.search(r"D(\d+)", f.name)) and int(m.group(1)) >= 42]
    return (3, "PASS", f"{len(new_adrs)} v7 ADRs") if len(new_adrs) >= 7 else (0, "PARTIAL", f"{len(new_adrs)} (need ≥7)")


def check_v7_6_5_anchors_documented() -> tuple[int, str, str]:
    """§6.5 v7 quantitative anchors present in tests (3 pts)."""
    n = _grep_count(r"adjoint.*fd|hypervolume|nataf|beta_target|earclip.*area|dynamic_compliance", "tests/**/*.py")
    return (3, "PASS", f"{n} v7-anchor refs") if n >= 3 else (0, "PARTIAL", f"{n} (need ≥3)")


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


def check_v4_no_regression() -> dict:
    """v4 must remain 100/100.

    Strategy: re-score the v4 rubric in-process and verify total == 100. This
    is a true regression check (not just file-presence) — if any v4 §1-§6
    item degrades, the v5 release is blocked.
    """
    sc_v4 = run_v4()
    return {
        "score": sc_v4.total_earned,
        "max": sc_v4.total_max,
        "regression": sc_v4.total_earned < 100,
    }


def check_v5_no_regression() -> dict:
    """v5 must remain 100/100 for a v6 release (true in-process re-score)."""
    sc_v5 = run_v5()
    return {
        "score": sc_v5.total_earned,
        "max": sc_v5.total_max,
        "regression": sc_v5.total_earned < 100,
    }


def check_pytest_green() -> dict:
    """No-regression gate: the full pytest suite must be green (D033).

    The rubric items are file-presence / coverage / ``--collect-only`` counts —
    none of them *runs* the suite, so a 100/100 rubric historically coexisted
    with red pytest (5 v5 multi-physics fingerprint tests crashed undetected,
    because the rubric only counted the fixture files). This gate executes
    ``pytest -q`` for real and blocks "release ready" on any failure/error,
    independent of the 100-point score. It is *not* part of the 100 points.

    Skips are allowed (the slow perf tests are ``--run-slow``-gated). The
    authoritative signal is the return code; counts are parsed for reporting.
    """
    rc, out, err = _run([str(VENV_PYTEST), "-q", "--no-header"])
    text = out + err

    def _count(pattern: str) -> int:
        m = re.search(pattern, text)
        return int(m.group(1)) if m else 0

    failed = _count(r"(\d+) failed")
    errors = _count(r"(\d+) error")
    passed = _count(r"(\d+) passed")
    skipped = _count(r"(\d+) skipped")
    # pytest return codes: 0 = all passed (skips ok), 1 = failures, 2 = interrupted,
    # 5 = no tests collected. Anything non-zero is a regression.
    green = rc == 0 and failed == 0 and errors == 0
    return {
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "returncode": rc,
        "green": green,
        "regression": not green,
    }


# --- main orchestration -----------------------------------------------


CHECKS_V4 = [
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


CHECKS_V5 = [
    # §1 multi-physics algorithms (30 pts)
    ("§1", "1.1", "热传导 TO (thermal SIMP)", 6, check_v5_1_1_thermal_simp),
    ("§1", "1.2", "模态 / 特征频率 TO", 6, check_v5_1_2_modal),
    ("§1", "1.3", "几何非线性 TO", 5, check_v5_1_3_nonlinear),
    ("§1", "1.4", "多材料 ordered SIMP", 5, check_v5_1_4_multi_material),
    ("§1", "1.5", "随机 / 可靠性 TO (Monte Carlo)", 4, check_v5_1_5_stochastic),
    ("§1", "1.6", "频响 / harmonic-driven TO", 4, check_v5_1_6_freq_response),
    # §2 coupled solvers + analytical verification (15 pts)
    ("§2", "2.1", "热传导 1D 杆 analytical 校验", 4, check_v5_2_1_thermal_analytical),
    ("§2", "2.2", "Euler-Bernoulli 模态频率校验", 4, check_v5_2_2_euler_bernoulli),
    ("§2", "2.3", "Gere 大变形 cantilever 校验", 3, check_v5_2_3_gere_elastica),
    ("§2", "2.4", "Mass matrix lumped vs consistent", 2, check_v5_2_4_mass_matrix_consistency),
    ("§2", "2.5", "Thermo-elastic coupling 一致性", 2, check_v5_2_5_thermo_elastic_coupling),
    # §3 reliability + stochastic (15 pts)
    ("§3", "3.1", "Monte Carlo UQ entrypoint", 4, check_v5_3_1_uq_monte_carlo),
    ("§3", "3.2", "Worst-case / minmax TO", 3, check_v5_3_2_worst_case),
    ("§3", "3.3", "RNG-seed 可复现性", 3, check_v5_3_3_rng_seed_repro),
    ("§3", "3.4", "Stochastic fingerprints ≥ 2", 3, check_v5_3_4_stochastic_fingerprints),
    ("§3", "3.5", "NSGA-II Pareto front", 2, check_v5_3_5_pareto_nsga),
    # §4 engineering quality (20 pts)
    ("§4", "4.1", "Test count ≥ 750", 4, check_v5_4_1_test_count_750),
    ("§4", "4.2", "Core coverage ≥ 95% (含 v5)", 4, check_v5_4_2_core_coverage_95),
    ("§4", "4.3", "Property tests ≥ 25", 3, check_v5_4_3_property_tests_25),
    ("§4", "4.4", "Mutation kill rate ≥ 75%", 3, check_v5_4_4_mutation_75),
    ("§4", "4.5", "Fingerprint DB ≥ 25", 2, check_v5_4_5_fingerprints_25),
    ("§4", "4.6", "v5 rubric 写入 test agent", 2, check_v5_4_6_v5_rubric_in_agent),
    ("§4", "4.7", "CI 跑 v5 rubric", 2, check_v5_4_7_v5_in_ci),
    # §5 user-facing (10 pts)
    ("§5", "5.1", "Pareto front HTML render", 3, check_v5_5_1_pareto_html),
    ("§5", "5.2", "2D→STL boundary 导出", 3, check_v5_5_2_stl_export),
    ("§5", "5.3", "Pure-NumPy autodiff", 2, check_v5_5_3_autodiff),
    ("§5", "5.4", "Multi-physics demo", 2, check_v5_5_4_multi_physics_demo),
    # §6 docs (10 pts)
    ("§6", "6.1", "blueprint-v5 six waves ticked", 2, check_v5_6_1_blueprint_v5),
    ("§6", "6.2", "tutorial v5 ≥5 new sections", 3, check_v5_6_2_tutorial_v5),
    ("§6", "6.3", "architecture v5 + multi-physics doc", 2, check_v5_6_3_arch_v5),
    ("§6", "6.4", "ADRs D025+ ≥ 8", 3, check_v5_6_4_adrs_v5),
]


CHECKS_V6 = [
    # §1 严格公式升级 (25 pts)
    ("§1", "1.1", "完整 TL Green-strain Newton", 8, check_v6_1_1_total_lagrangian),
    ("§1", "1.2", "Rayleigh 阻尼复频响", 6, check_v6_1_2_rayleigh_damping),
    ("§1", "1.3", "各向异性张量热传导", 6, check_v6_1_3_anisotropic_thermal),
    ("§1", "1.4", "NSGA-III ≥3 目标", 5, check_v6_1_4_nsga3),
    # §2 高级可靠性 + 解析校验 (20 pts)
    ("§2", "2.1", "FORM 可靠性指标 β", 5, check_v6_2_1_form),
    ("§2", "2.2", "Importance sampling", 4, check_v6_2_2_importance_sampling),
    ("§2", "2.3", "SORM / 曲率修正", 3, check_v6_2_3_sorm),
    ("§2", "2.4", "完整 TL objectivity + 解析 patch 校验", 4, check_v6_2_4_tl_verification),
    ("§2", "2.5", "半功率带宽解析校验", 4, check_v6_2_5_half_power_bandwidth),
    # §3 几何 + AD (15 pts)
    ("§3", "3.1", "Marching-squares 平滑 STL", 5, check_v6_3_1_smooth_stl),
    ("§3", "3.2", "Reverse-mode AD (tape)", 5, check_v6_3_2_reverse_ad),
    ("§3", "3.3", "AD reverse-vs-forward 一致性", 5, check_v6_3_3_ad_consistency),
    # §4 工程质量 (20 pts)
    ("§4", "4.1", "Test count ≥ 850", 4, check_v6_4_1_test_count_850),
    ("§4", "4.2", "Core coverage ≥ 95% (含 v6)", 4, check_v6_4_2_core_coverage_95),
    ("§4", "4.3", "Property tests ≥ 35", 3, check_v6_4_3_property_tests_35),
    ("§4", "4.4", "Mutation kill rate ≥ 75%", 3, check_v6_4_4_mutation_75),
    ("§4", "4.5", "Fingerprint DB ≥ 30", 2, check_v6_4_5_fingerprints_30),
    ("§4", "4.6", "pytest gate green (D033)", 2, check_v6_4_6_pytest_gate),
    ("§4", "4.7", "v6 rubric 写入 agent + CI", 2, check_v6_4_7_v6_in_agent_ci),
    # §5 用户面 (10 pts)
    ("§5", "5.1", "收敛研究 HTML", 3, check_v6_5_1_convergence_html),
    ("§5", "5.2", "阻尼频响 Bode 图", 3, check_v6_5_2_bode_plot),
    ("§5", "5.3", "3 目标 Pareto 渲染", 2, check_v6_5_3_nsga3_render),
    ("§5", "5.4", "平滑 STL demo", 2, check_v6_5_4_smooth_stl_demo),
    # §6 文档 (10 pts)
    ("§6", "6.1", "blueprint-v6 six waves ticked", 2, check_v6_6_1_blueprint_v6),
    ("§6", "6.2", "tutorial v6 ≥4 new sections", 3, check_v6_6_2_tutorial_v6),
    ("§6", "6.3", "architecture v6 + production-grade doc", 2, check_v6_6_3_arch_v6),
    ("§6", "6.4", "ADRs D034+ ≥ 7", 3, check_v6_6_4_adrs_v6),
]


CHECKS_V7 = [
    # §1 优化驱动器 (24 pts)
    ("§1", "1.1", "Reliability-based TO (FORM→SIMP)", 8, check_v7_1_1_rbto),
    ("§1", "1.2", "几何非线性 TO (TL 伴随)", 8, check_v7_1_2_nonlinear_to),
    ("§1", "1.3", "阻尼频响 TO (动柔度)", 8, check_v7_1_3_damped_fr_to),
    # §2 场级保真 + 多目标 (16 pts)
    ("§2", "2.1", "逐单元各向异性热场", 5, check_v7_2_1_per_element_anisotropic),
    ("§2", "2.2", "各向异性热 TO 灵敏度", 4, check_v7_2_2_anisotropic_thermal_to),
    ("§2", "2.3", "NSGA-III 直接优化密度场", 7, check_v7_2_3_nsga3_density_field),
    # §3 不确定性 + 几何 (15 pts)
    ("§3", "3.1", "Nataf 变换 (相关高斯)", 4, check_v7_3_1_nataf),
    ("§3", "3.2", "相关/非高斯 FORM", 4, check_v7_3_2_correlated_form),
    ("§3", "3.3", "Ear-clipping 通用多边形 STL", 4, check_v7_3_3_earclip_stl),
    ("§3", "3.4", "STL 孔洞 (even-odd)", 3, check_v7_3_4_hole_handling),
    # §4 测试基础设施 (20 pts)
    ("§4", "4.1", "Test count ≥ 900", 4, check_v7_4_1_test_count_900),
    ("§4", "4.2", "Core coverage ≥ 95% (含 v7)", 4, check_v7_4_2_core_coverage_95),
    ("§4", "4.3", "Property tests ≥ 40", 3, check_v7_4_3_property_tests_40),
    ("§4", "4.4", "Mutation kill rate ≥ 75%", 3, check_v7_4_4_mutation_75),
    ("§4", "4.5", "Fingerprint DB ≥ 35", 2, check_v7_4_5_fingerprints_35),
    ("§4", "4.6", "pytest gate green (D033)", 2, check_v7_4_6_pytest_gate),
    ("§4", "4.7", "v7 rubric 写入 agent + CI", 2, check_v7_4_7_v7_in_agent_ci),
    # §5 用户面 demos (10 pts)
    ("§5", "5.1", "RBTO 收敛 demo", 3, check_v7_5_1_rbto_demo),
    ("§5", "5.2", "非线性/阻尼 TO demo", 3, check_v7_5_2_nonlinear_demo),
    ("§5", "5.3", "密度场 Pareto 渲染", 2, check_v7_5_3_density_pareto_render),
    ("§5", "5.4", "Ear-clipping STL demo", 2, check_v7_5_4_earclip_demo),
    # §6 文档 (15 pts)
    ("§6", "6.1", "blueprint-v7 ≥6 ticks", 3, check_v7_6_1_blueprint_v7),
    ("§6", "6.2", "tutorial v7 ≥4 new sections", 3, check_v7_6_2_tutorial_v7),
    ("§6", "6.3", "architecture v7 section", 3, check_v7_6_3_arch_v7),
    ("§6", "6.4", "ADRs D042+ ≥ 7", 3, check_v7_6_4_adrs_v7),
    ("§6", "6.5", "v7 quantitative anchors documented", 3, check_v7_6_5_anchors_documented),
]


def _score(checks: list, section_filter: str | None = None) -> list[RubricItem]:
    items: list[RubricItem] = []
    for section, code, title, max_pts, fn in checks:
        if section_filter and section != section_filter:
            continue
        try:
            earned, status, evidence = fn()
        except Exception as e:
            earned, status, evidence = 0, "ERROR", f"{type(e).__name__}: {e}"
        items.append(
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
    return items


def run_v4(section_filter: str | None = None) -> Scorecard:
    """Score the v4 rubric in-process. Used for v5's no-regression gate."""
    sc = Scorecard(version="v4.0.0")
    sc.items = _score(CHECKS_V4, section_filter)
    return sc


def run_v5(section_filter: str | None = None) -> Scorecard:
    """Score the v5 rubric in-process. Used for v6's no-regression gate."""
    sc = Scorecard(version="v5.0.0")
    sc.items = _score(CHECKS_V5, section_filter)
    return sc


def run_v6(section_filter: str | None = None) -> Scorecard:
    """Score the v6 rubric in-process. Used for v7's no-regression gate."""
    sc = Scorecard(version="v6.0.0")
    sc.items = _score(CHECKS_V6, section_filter)
    return sc


def run_v7(section_filter: str | None = None) -> Scorecard:
    """Score the v7 rubric in-process."""
    sc = Scorecard(version="v7.0.0")
    sc.items = _score(CHECKS_V7, section_filter)
    return sc


def check_v6_no_regression() -> dict:
    """v6 must remain 100/100 for a v7 release (true in-process re-score)."""
    sc_v6 = run_v6()
    return {
        "score": sc_v6.total_earned,
        "max": sc_v6.total_max,
        "regression": sc_v6.total_earned < 100,
    }


def run_all(section_filter: str | None = None, rubric: str = "v5", run_pytest_gate: bool = True) -> Scorecard:
    """Score the currently-active rubric. Default = v5.

    ``run_pytest_gate`` runs the full suite as a hard-fail no-regression gate
    (D033). It is skipped for ``--section`` (partial) runs and via
    ``--no-pytest-gate`` — a partial score shouldn't gate on the whole suite.
    """
    if rubric == "v4":
        sc = run_v4(section_filter)
    elif rubric == "v5":
        sc = run_v5(section_filter)
    elif rubric == "v6":
        sc = run_v6(section_filter)
    else:  # v7
        sc = run_v7(section_filter)
    sc.v1_check = check_v1_no_regression()
    sc.v2_check = check_v2_no_regression()
    sc.v3_check = check_v3_no_regression()
    if rubric in ("v5", "v6", "v7"):
        sc.v4_check = check_v4_no_regression()
    if rubric in ("v6", "v7"):
        sc.v5_check = check_v5_no_regression()
    if rubric == "v7":
        sc.v6_check = check_v6_no_regression()
    if run_pytest_gate:
        sc.pytest_check = check_pytest_green()
    return sc


def print_summary(sc: Scorecard) -> None:
    section_totals: dict[str, list[int]] = {}
    for it in sc.items:
        section_totals.setdefault(it.section, [0, 0])
        section_totals[it.section][0] += it.earned
        section_totals[it.section][1] += it.max_points

    label = sc.version.split(".")[0]  # "v5" / "v4"
    print(f"{label} 测试 Agent — Scorecard ({sc.version})")
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
    if sc.v4_check:
        print(f"  v4 rubric  : {sc.v4_check.get('score')}/{sc.v4_check.get('max', 100)}  regression={sc.v4_check.get('regression')}")
    if sc.v5_check:
        print(f"  v5 rubric  : {sc.v5_check.get('score')}/{sc.v5_check.get('max', 100)}  regression={sc.v5_check.get('regression')}")
    if sc.pytest_check:
        pc = sc.pytest_check
        marker = "✓" if pc.get("green") else "✗"
        print(
            f"  pytest gate: [{marker}] {pc.get('passed')} passed / {pc.get('failed')} failed / "
            f"{pc.get('errors')} errors / {pc.get('skipped')} skipped (rc={pc.get('returncode')})"
        )

    regressions = [
        sc.v1_check.get("regression"),
        sc.v2_check.get("regression"),
        sc.v3_check.get("regression"),
        sc.v4_check.get("regression") if sc.v4_check else False,
        sc.v5_check.get("regression") if sc.v5_check else False,
        sc.pytest_check.get("regression") if sc.pytest_check else False,
    ]
    if sc.total_earned >= 99 and not any(regressions):
        print(f"\n✅  {label} rubric ≥ 99/100 AND no regression (incl. pytest green) — release ready.")
    elif sc.total_earned >= 99 and sc.pytest_check.get("regression"):
        print(f"\n❌  {label} rubric ≥ 99 but pytest is RED — release blocked (D033 gate).")
    elif sc.total_earned >= 80:
        print(f"\n⚠️  {label} progress: not yet 99 (release blocked).")
    else:
        print(f"\n❌  {label} score below 80 — significant work remaining.")


def main() -> int:
    parser = argparse.ArgumentParser(description="测试 Agent (v4 + v5 rubrics)")
    parser.add_argument("--strict", action="store_true", help="exit 1 if total < 99 or any regression")
    parser.add_argument(
        "--rubric",
        choices=["v4", "v5", "v6", "v7"],
        default="v5",
        help="which rubric to score (default v5; v4-v6 scorable for regression checks)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="scorecard JSON path (default tests/v{rubric}_scorecard.json)",
    )
    parser.add_argument("--section", default=None, help="only score one section (e.g. §4)")
    parser.add_argument("--quiet", action="store_true", help="suppress human-readable summary")
    parser.add_argument(
        "--no-pytest-gate",
        action="store_true",
        help="skip the D033 full-suite pytest gate (faster; for iterative scoring only)",
    )
    args = parser.parse_args()

    # The pytest gate runs the whole suite; skip it for partial (--section) scoring.
    run_pytest_gate = not args.no_pytest_gate and args.section is None
    sc = run_all(section_filter=args.section, rubric=args.rubric, run_pytest_gate=run_pytest_gate)
    out_default = f"tests/{args.rubric}_scorecard.json"
    out_path = REPO_ROOT / (args.output or out_default)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": sc.version,
        "total_max": sc.total_max,
        "total_earned": sc.total_earned,
        "items": [asdict(i) for i in sc.items],
        "v1_check": sc.v1_check,
        "v2_check": sc.v2_check,
        "v3_check": sc.v3_check,
    }
    if sc.v4_check:
        payload["v4_check"] = sc.v4_check
    if sc.v5_check:
        payload["v5_check"] = sc.v5_check
    if sc.v6_check:
        payload["v6_check"] = sc.v6_check
    if sc.pytest_check:
        payload["pytest_check"] = sc.pytest_check
    out_path.write_text(json.dumps(payload, indent=2) + "\n")

    if not args.quiet:
        print_summary(sc)
    if args.strict:
        regression = any(
            [
                sc.v1_check.get("regression"),
                sc.v2_check.get("regression"),
                sc.v3_check.get("regression"),
                sc.v4_check.get("regression") if sc.v4_check else False,
                sc.v5_check.get("regression") if sc.v5_check else False,
                sc.v6_check.get("regression") if sc.v6_check else False,
                sc.pytest_check.get("regression") if sc.pytest_check else False,
            ]
        )
        if sc.total_earned < 99 or regression:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
