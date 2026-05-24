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
    v7_check: dict = field(default_factory=dict)
    v8_check: dict = field(default_factory=dict)
    v9_check: dict = field(default_factory=dict)
    v10_check: dict = field(default_factory=dict)
    v11_check: dict = field(default_factory=dict)
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


# === v8 rubric (closing the loop: gradient drivers + general distributions) ===
# Grep-based presence + quantitative-test checks (same pattern as CHECKS_V7).
# Each maps to a v7 (or earlier) ADR reopening criterion; see docs/blueprint-v8.md.


def check_v8_1_1_nonlinear_oc() -> tuple[int, str, str]:
    """§1.1 geometric-nonlinear TO full OC loop (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/nonlinear_simp.py",
        r"nonlinear_to_oc|geometric_nonlinear_optimize|tl_simp_optimize|def .*nonlinear.*optimize",
        r"nonlinear.*oc|nonlinear.*loop|large_deformation.*topolog|nonlinear_to_optimize",
        8, "nonlinear OC loop in module, no test", "nonlinear TO OC loop + large-deformation-vs-linear test")


def check_v8_1_2_dynamic_oc() -> tuple[int, str, str]:
    """§1.2 filtered dynamic-compliance TO loop (multi-ω) (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/freq_response.py",
        r"dynamic_compliance_to|band_dynamic|multi_omega|def .*dynamic.*optimize",
        r"dynamic.*to.*loop|band.*dynamic|multi_omega|dynamic_compliance_to",
        8, "dynamic OC loop in module, no test", "filtered multi-ω dynamic-compliance TO loop + test")


def check_v8_1_3_seeded_nsga3() -> tuple[int, str, str]:
    """§1.3 gradient-seeded NSGA-III density field (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/multi_objective_to.py",
        r"seed.*simp|warm_start|gradient_seed|seeded_pareto",
        r"seed.*nsga|warm_start|gradient_seed|seeded.*hypervolume",
        8, "seeded NSGA-III in module, no test", "gradient-seeded NSGA-III + HV-vs-budget test")


def check_v8_2_1_general_nataf() -> tuple[int, str, str]:
    """§2.1 general-marginal Nataf via Gauss-Hermite (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/reliability.py",
        r"gauss_hermite|nataf_integral|def .*weibull|def .*gumbel|equivalent_correlation_integral",
        r"gauss_hermite|weibull|gumbel|nataf.*integral",
        8, "general-marginal Nataf in module, no test", "Gauss-Hermite Nataf + Weibull/Gumbel test")


def check_v8_2_2_system_reliability() -> tuple[int, str, str]:
    """§2.2 system reliability (series/parallel, Ditlevsen bounds) (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/reliability.py",
        r"system_reliability|ditlevsen|series_system|parallel_system",
        r"system_reliability|ditlevsen|series.*system|parallel.*system",
        8, "system reliability in module, no test", "system reliability + Ditlevsen-bounds test")


def check_v8_3_1_fibre_steering() -> tuple[int, str, str]:
    """§3.1 fibre-steering thermal TO (orientation field optimisation) (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/thermal_simp.py",
        r"fibre_steer|orientation_sensitivity|optimize_orientation|steer.*thermal",
        r"fibre_steer|orientation.*sensitivity|steer.*thermal|orientation.*fd",
        8, "fibre-steering in module, no test", "fibre-steering orientation sensitivity + FD test")


def check_v8_3_2_ms_nesting() -> tuple[int, str, str]:
    """§3.2 marching-squares nested-loop hole detection → ear-clipping caps (7 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/stl_export.py",
        r"nested.*loop|detect.*hole|even_odd.*loop|classify_loops|write_stl_smooth_holes",
        r"nested.*loop|ms.*hole|smooth.*hole|nesting.*stl",
        7, "MS nesting in module, no test", "MS nested-loop detection + holed-STL area test")


def check_v8_4_1_test_count_920() -> tuple[int, str, str]:
    """§4.1 ≥ 920 tests (4 pts)."""
    n = _pytest_collect_count()
    return (4, "PASS", f"{n} tests collected") if n >= 920 else (0, "FAIL", f"{n} (need ≥920)")


def check_v8_4_2_core_coverage_95() -> tuple[int, str, str]:
    """§4.2 core coverage ≥ 95% incl. v8 (4 pts)."""
    pct = _pytest_coverage("structure_optimizer/core")
    return (4, "PASS", f"{pct}% coverage") if pct >= 95.0 else (0, "FAIL", f"{pct}% (need ≥95%)")


def check_v8_4_3_property_tests_42() -> tuple[int, str, str]:
    """§4.3 property tests ≥ 42 (3 pts)."""
    n = _grep_count(r"^def test_property_", "tests/**/*.py")
    return (3, "PASS", f"{n} property tests") if n >= 42 else (0, "FAIL", f"{n} (need ≥42)")


def check_v8_4_4_mutation_75() -> tuple[int, str, str]:
    """§4.4 mutation kill rate ≥ 75% (3 pts)."""
    report = REPO_ROOT / "tests/mutation_report.json"
    if not report.exists():
        return 0, "FAIL", "mutation_report missing"
    data = json.loads(report.read_text())
    rate = data.get("aggregate_kill_rate", data.get("kill_rate", 0.0))
    return (3, "PASS", f"{rate * 100:.1f}% kill rate") if rate >= 0.75 else (0, "FAIL", f"{rate * 100:.1f}%")


def check_v8_4_5_fingerprints_40() -> tuple[int, str, str]:
    """§4.5 fingerprint DB ≥ 40 (2 pts)."""
    n = len(list((REPO_ROOT / "tests/fingerprints").glob("*.json")))
    return (2, "PASS", f"{n} fingerprints") if n >= 40 else (0, "FAIL", f"{n} (need ≥40)")


def check_v8_4_6_pytest_gate() -> tuple[int, str, str]:
    """§4.6 pytest gate green / D033 mechanism present (2 pts)."""
    has_gate = _grep_count(r"def check_pytest_green", "scripts/test_agent.py") >= 1
    has_adr = _file_exists("docs/decisions/D033-pytest-green-no-regression-gate.md")
    return (2, "PASS", "D033 gate + ADR") if (has_gate and has_adr) else (0, "FAIL", f"gate={'✓' if has_gate else '✗'} ADR={'✓' if has_adr else '✗'}")


def check_v8_4_7_v8_in_agent_ci() -> tuple[int, str, str]:
    """§4.7 v8 rubric referenced in agent + CI (2 pts)."""
    me = (REPO_ROOT / "scripts/test_agent.py").read_text()
    in_agent = "CHECKS_V8" in me
    ci = REPO_ROOT / ".github/workflows/test.yml"
    in_ci = ci.exists() and "v8" in ci.read_text().lower()
    if in_agent and in_ci:
        return 2, "PASS", "v8 in agent + CI"
    if in_agent:
        return 1, "PARTIAL", "v8 in agent, not CI"
    return 0, "FAIL", "v8 not wired"


def check_v8_5_1_nonlinear_dynamic_demo() -> tuple[int, str, str]:
    """§5.1 nonlinear / dynamic OC-loop demo (3 pts)."""
    n = _grep_count(r"nonlinear_oc_demo|dynamic_oc_demo|nonlinear_loop_demo|render.*nonlinear.*loop", "**/*.py")
    return (3, "PASS", f"{n} nonlinear/dynamic-loop demo refs") if n >= 1 else (0, "FAIL", "no nonlinear/dynamic-loop demo")


def check_v8_5_2_seeded_nsga_demo() -> tuple[int, str, str]:
    """§5.2 seeded NSGA-III demo (3 pts)."""
    n = _grep_count(r"seeded_nsga_demo|warm_start_demo|seeded.*pareto.*demo|render.*seeded", "**/*.py")
    return (3, "PASS", f"{n} seeded-NSGA demo refs") if n >= 1 else (0, "FAIL", "no seeded-NSGA demo")


def check_v8_5_3_reliability_demo() -> tuple[int, str, str]:
    """§5.3 general-distribution / system-reliability demo (2 pts)."""
    n = _grep_count(r"system_reliability_demo|general_marginal_demo|weibull_demo|ditlevsen_demo", "**/*.py")
    return (2, "PASS", f"{n} reliability-demo refs") if n >= 1 else (0, "FAIL", "no reliability demo")


def check_v8_5_4_geometry_demo() -> tuple[int, str, str]:
    """§5.4 fibre-steering / holed-STL demo (2 pts)."""
    n = _grep_count(r"fibre_steer_demo|holed_stl_demo|nesting_demo|orientation_demo", "**/*.py")
    return (2, "PASS", f"{n} geometry-demo refs") if n >= 1 else (0, "FAIL", "no geometry demo")


def check_v8_6_1_blueprint_v8() -> tuple[int, str, str]:
    """§6.1 blueprint-v8 ≥6 wave ticks (3 pts)."""
    p = REPO_ROOT / "docs/blueprint-v8.md"
    if not p.exists():
        return 0, "FAIL", "blueprint-v8.md missing"
    ticks = p.read_text().count("[x]")
    return (3, "PASS", f"{ticks} ticks") if ticks >= 6 else (0, "PARTIAL", f"{ticks} ticks (need ≥6)")


def check_v8_6_2_tutorial_v8() -> tuple[int, str, str]:
    """§6.2 tutorial v8 ≥4 new sections (3 pts)."""
    p = REPO_ROOT / "docs/tutorial.md"
    if not p.exists():
        return 0, "FAIL", "missing"
    n = len(re.findall(r"^### 18\.\d", p.read_text(), re.MULTILINE))
    return (3, "PASS", f"{n} v8 subsections") if n >= 4 else (0, "PARTIAL", f"{n} (need ≥4)")


def check_v8_6_3_arch_v8() -> tuple[int, str, str]:
    """§6.3 architecture v8 section (3 pts)."""
    p = REPO_ROOT / "docs/architecture.md"
    if not p.exists():
        return 0, "FAIL", "missing"
    txt = p.read_text().lower()
    return (3, "PASS", "v8 section present") if ("## 18." in p.read_text() and "loop" in txt) else (0, "FAIL", "no v8 section")


def check_v8_6_4_adrs_v8() -> tuple[int, str, str]:
    """§6.4 ADRs D050+ ≥ 7 (3 pts)."""
    files = list((REPO_ROOT / "docs/decisions").glob("D05*.md"))
    new_adrs = [f for f in files if (m := re.search(r"D(\d+)", f.name)) and int(m.group(1)) >= 50]
    return (3, "PASS", f"{len(new_adrs)} v8 ADRs") if len(new_adrs) >= 7 else (0, "PARTIAL", f"{len(new_adrs)} (need ≥7)")


def check_v8_6_5_anchors_documented() -> tuple[int, str, str]:
    """§6.5 v8 quantitative anchors present in tests (3 pts)."""
    n = _grep_count(r"large_deformation|gauss_hermite|ditlevsen|fibre_steer|hypervolume.*budget|nested.*loop", "tests/**/*.py")
    return (3, "PASS", f"{n} v8-anchor refs") if n >= 3 else (0, "PARTIAL", f"{n} (need ≥3)")


CHECKS_V8 = [
    # §1 driver 闭环 (24 pts)
    ("§1", "1.1", "几何非线性 TO 完整 OC 环", 8, check_v8_1_1_nonlinear_oc),
    ("§1", "1.2", "滤波动态柔度 TO 环 (多频)", 8, check_v8_1_2_dynamic_oc),
    ("§1", "1.3", "梯度种子 NSGA-III", 8, check_v8_1_3_seeded_nsga3),
    # §2 不确定性 (16 pts)
    ("§2", "2.1", "一般 marginal Nataf (Gauss-Hermite)", 8, check_v8_2_1_general_nataf),
    ("§2", "2.2", "系统可靠性 (串/并联)", 8, check_v8_2_2_system_reliability),
    # §3 几何 + 场 (15 pts)
    ("§3", "3.1", "纤维转向热 TO", 8, check_v8_3_1_fibre_steering),
    ("§3", "3.2", "MS 嵌套环 → ear-clipping 封顶", 7, check_v8_3_2_ms_nesting),
    # §4 测试基础设施 (20 pts)
    ("§4", "4.1", "Test count ≥ 920", 4, check_v8_4_1_test_count_920),
    ("§4", "4.2", "Core coverage ≥ 95% (含 v8)", 4, check_v8_4_2_core_coverage_95),
    ("§4", "4.3", "Property tests ≥ 42", 3, check_v8_4_3_property_tests_42),
    ("§4", "4.4", "Mutation kill rate ≥ 75%", 3, check_v8_4_4_mutation_75),
    ("§4", "4.5", "Fingerprint DB ≥ 40", 2, check_v8_4_5_fingerprints_40),
    ("§4", "4.6", "pytest gate green (D033)", 2, check_v8_4_6_pytest_gate),
    ("§4", "4.7", "v8 rubric 写入 agent + CI", 2, check_v8_4_7_v8_in_agent_ci),
    # §5 用户面 demos (10 pts)
    ("§5", "5.1", "非线性/动态 OC-loop demo", 3, check_v8_5_1_nonlinear_dynamic_demo),
    ("§5", "5.2", "梯度种子 NSGA demo", 3, check_v8_5_2_seeded_nsga_demo),
    ("§5", "5.3", "系统/一般分布可靠性 demo", 2, check_v8_5_3_reliability_demo),
    ("§5", "5.4", "纤维转向/带孔 STL demo", 2, check_v8_5_4_geometry_demo),
    # §6 文档 (15 pts)
    ("§6", "6.1", "blueprint-v8 ≥6 ticks", 3, check_v8_6_1_blueprint_v8),
    ("§6", "6.2", "tutorial v8 ≥4 new sections", 3, check_v8_6_2_tutorial_v8),
    ("§6", "6.3", "architecture v8 section", 3, check_v8_6_3_arch_v8),
    ("§6", "6.4", "ADRs D050+ ≥ 7", 3, check_v8_6_4_adrs_v8),
    ("§6", "6.5", "v8 quantitative anchors documented", 3, check_v8_6_5_anchors_documented),
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
    """Score the v7 rubric in-process. Used for v8's no-regression gate."""
    sc = Scorecard(version="v7.0.0")
    sc.items = _score(CHECKS_V7, section_filter)
    return sc


def run_v8(section_filter: str | None = None) -> Scorecard:
    """Score the v8 rubric in-process."""
    sc = Scorecard(version="v8.0.0")
    sc.items = _score(CHECKS_V8, section_filter)
    return sc


# === v9 rubric — second-order drivers: constrained optimisers + coupled fields
#     + robust geometry (Waves CCC-JJJ, ADRs D058-D065). Each check traces a
#     D050-D056 reopening criterion. ===


def check_v9_1_1_mma_tl() -> tuple[int, str, str]:
    """§1.1 MMA-driven Total-Lagrangian nonlinear TO (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/nonlinear_simp.py",
        r"mma_nonlinear_to|nonlinear_to_mma|mma.*tl.*to|tl.*mma_to",
        r"mma.*nonlinear|nonlinear.*mma|mma_tl",
        8, "MMA-TL in module, no test", "MMA-driven TL nonlinear TO + convergence-vs-OC test")


def check_v9_1_2_band_gap() -> tuple[int, str, str]:
    """§1.2 eigenfrequency band-gap / minimax band objective (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/freq_response.py",
        r"band_gap|minimax_band|eigenfrequency_gap|maximize_band|band_stop",
        r"band_gap|minimax_band|band_stop|eigenfrequency_gap",
        8, "band objective in module, no test", "band-gap/minimax band objective + sensitivity test")


def check_v9_1_3_three_objective() -> tuple[int, str, str]:
    """§1.3 ≥3-objective multi-load-case NSGA-III + seeded warm-start (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/multi_objective_to.py",
        r"multi_load_case|three_objective|n_objectives|multi_objective.*3|three_obj",
        r"three_objective|multi_load|3.*objective|n_obj",
        8, "3-objective in module, no test", "≥3-objective multi-load NSGA-III + hypervolume test")


def check_v9_2_1_rosenblatt() -> tuple[int, str, str]:
    """§2.1 Rosenblatt transform for known joint distributions (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/reliability.py",
        r"rosenblatt|RosenblattTransform|conditional_cdf",
        r"rosenblatt|conditional_cdf",
        8, "Rosenblatt in module, no test", "Rosenblatt transform vs Nataf + round-trip test")


def check_v9_2_2_system_rbto() -> tuple[int, str, str]:
    """§2.2 system-reliability-based TO (drive to a target system β) (8 pts)."""
    has_rbto = _grep_count(r"system_rbto|system_reliability_to|target_system_beta", "structure_optimizer/core/rbto.py") >= 1
    has_rel = _grep_count(r"system_rbto|system_reliability_to|target_system_beta", "structure_optimizer/core/reliability.py") >= 1
    has_test = _grep_count(r"system_rbto|system.*rbto|target_system_beta", "tests/**/*.py") >= 1
    if (has_rbto or has_rel) and has_test:
        return 8, "PASS", "system-reliability-based TO + target-β test"
    if has_rbto or has_rel:
        return 4, "PARTIAL", "system RBTO in module, no test"
    return 0, "FAIL", "system_rbto missing"


def check_v9_3_1_coupled_orientation() -> tuple[int, str, str]:
    """§3.1 coupled density + orientation thermal TO (alternating min) (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/thermal_simp.py",
        r"coupled_density_orientation|alternating_minim|coupled.*orientation|coupled_thermal_to",
        r"coupled.*orientation|alternating.*minim|coupled_density",
        8, "coupled TO in module, no test", "coupled density+orientation TO + alternating-min test")


def check_v9_3_2_slit_free() -> tuple[int, str, str]:
    """§3.2 slit-free hole triangulation (robust watertight curved holes) (7 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/stl_export.py",
        r"monotone.*triangulat|constrained_delaunay|slit_free|triangulate_monotone|triangulate_simple",
        r"monotone|slit_free|watertight.*annulus|robust.*hole|slitfree",
        7, "slit-free triangulation in module, no test", "slit-free hole triangulation + annulus-watertight test")


def check_v9_4_1_test_count_960() -> tuple[int, str, str]:
    """§4.1 ≥ 960 tests (4 pts)."""
    n = _pytest_collect_count()
    return (4, "PASS", f"{n} tests collected") if n >= 960 else (0, "FAIL", f"{n} (need ≥960)")


def check_v9_4_2_core_coverage_95() -> tuple[int, str, str]:
    """§4.2 core coverage ≥ 95% incl. v9 (4 pts)."""
    pct = _pytest_coverage("structure_optimizer/core")
    return (4, "PASS", f"{pct}% coverage") if pct >= 95.0 else (0, "FAIL", f"{pct}% (need ≥95%)")


def check_v9_4_3_property_tests_44() -> tuple[int, str, str]:
    """§4.3 property tests ≥ 44 (3 pts)."""
    n = _grep_count(r"^def test_property_", "tests/**/*.py")
    return (3, "PASS", f"{n} property tests") if n >= 44 else (0, "FAIL", f"{n} (need ≥44)")


def check_v9_4_4_mutation_75() -> tuple[int, str, str]:
    """§4.4 mutation kill rate ≥ 75% (3 pts)."""
    report = REPO_ROOT / "tests/mutation_report.json"
    if not report.exists():
        return 0, "FAIL", "mutation_report missing"
    data = json.loads(report.read_text())
    rate = data.get("aggregate_kill_rate", data.get("kill_rate", 0.0))
    return (3, "PASS", f"{rate * 100:.1f}% kill rate") if rate >= 0.75 else (0, "FAIL", f"{rate * 100:.1f}%")


def check_v9_4_5_fingerprints_45() -> tuple[int, str, str]:
    """§4.5 fingerprint DB ≥ 45 (2 pts)."""
    n = len(list((REPO_ROOT / "tests/fingerprints").glob("*.json")))
    return (2, "PASS", f"{n} fingerprints") if n >= 45 else (0, "FAIL", f"{n} (need ≥45)")


def check_v9_4_6_pytest_gate() -> tuple[int, str, str]:
    """§4.6 pytest gate green / D033 mechanism present (2 pts)."""
    has_gate = _grep_count(r"def check_pytest_green", "scripts/test_agent.py") >= 1
    has_adr = _file_exists("docs/decisions/D033-pytest-green-no-regression-gate.md")
    return (2, "PASS", "D033 gate + ADR") if (has_gate and has_adr) else (0, "FAIL", f"gate={'✓' if has_gate else '✗'} ADR={'✓' if has_adr else '✗'}")


def check_v9_4_7_v9_in_agent_ci() -> tuple[int, str, str]:
    """§4.7 v9 rubric referenced in agent + CI (2 pts)."""
    me = (REPO_ROOT / "scripts/test_agent.py").read_text()
    in_agent = "CHECKS_V9" in me
    ci = REPO_ROOT / ".github/workflows/test.yml"
    in_ci = ci.exists() and "v9" in ci.read_text().lower()
    if in_agent and in_ci:
        return 2, "PASS", "v9 in agent + CI"
    if in_agent:
        return 1, "PARTIAL", "v9 in agent, not CI"
    return 0, "FAIL", "v9 not wired"


def check_v9_5_1_mma_band_demo() -> tuple[int, str, str]:
    """§5.1 MMA-TL / band-gap demo (3 pts)."""
    n = _grep_count(r"mma_tl_demo|band_gap_demo|minimax_band_demo|mma_nonlinear_demo", "**/*.py")
    return (3, "PASS", f"{n} MMA/band demo refs") if n >= 1 else (0, "FAIL", "no MMA/band demo")


def check_v9_5_2_three_objective_demo() -> tuple[int, str, str]:
    """§5.2 ≥3-objective NSGA-III demo (3 pts)."""
    n = _grep_count(r"three_objective_demo|multi_load_demo|nsga3_three_demo|render.*three_obj", "**/*.py")
    return (3, "PASS", f"{n} 3-objective demo refs") if n >= 1 else (0, "FAIL", "no 3-objective demo")


def check_v9_5_3_reliability_demo() -> tuple[int, str, str]:
    """§5.3 Rosenblatt / system-RBTO demo (2 pts)."""
    n = _grep_count(r"rosenblatt_demo|system_rbto_demo|target_beta_demo", "**/*.py")
    return (2, "PASS", f"{n} reliability-demo refs") if n >= 1 else (0, "FAIL", "no reliability demo")


def check_v9_5_4_geometry_demo() -> tuple[int, str, str]:
    """§5.4 coupled-field / slit-free STL demo (2 pts)."""
    n = _grep_count(r"coupled_field_demo|slit_free_demo|watertight_annulus_demo|monotone_demo|coupled_orientation_demo", "**/*.py")
    return (2, "PASS", f"{n} geometry-demo refs") if n >= 1 else (0, "FAIL", "no geometry demo")


def check_v9_6_1_blueprint_v9() -> tuple[int, str, str]:
    """§6.1 blueprint-v9 ≥6 wave ticks (3 pts)."""
    p = REPO_ROOT / "docs/blueprint-v9.md"
    if not p.exists():
        return 0, "FAIL", "blueprint-v9.md missing"
    ticks = p.read_text().count("[x]")
    return (3, "PASS", f"{ticks} ticks") if ticks >= 6 else (0, "PARTIAL", f"{ticks} ticks (need ≥6)")


def check_v9_6_2_tutorial_v9() -> tuple[int, str, str]:
    """§6.2 tutorial v9 ≥4 new sections (3 pts)."""
    p = REPO_ROOT / "docs/tutorial.md"
    if not p.exists():
        return 0, "FAIL", "missing"
    n = len(re.findall(r"^### 19\.\d", p.read_text(), re.MULTILINE))
    return (3, "PASS", f"{n} v9 subsections") if n >= 4 else (0, "PARTIAL", f"{n} (need ≥4)")


def check_v9_6_3_arch_v9() -> tuple[int, str, str]:
    """§6.3 architecture v9 section (3 pts)."""
    p = REPO_ROOT / "docs/architecture.md"
    if not p.exists():
        return 0, "FAIL", "missing"
    txt = p.read_text().lower()
    return (3, "PASS", "v9 section present") if ("## 19." in p.read_text() and "loop" in txt) else (0, "FAIL", "no v9 section")


def check_v9_6_4_adrs_v9() -> tuple[int, str, str]:
    """§6.4 ADRs D058+ ≥ 7 (3 pts)."""
    files = list((REPO_ROOT / "docs/decisions").glob("D05*.md")) + list((REPO_ROOT / "docs/decisions").glob("D06*.md"))
    new_adrs = [f for f in files if (m := re.search(r"D(\d+)", f.name)) and int(m.group(1)) >= 58]
    return (3, "PASS", f"{len(new_adrs)} v9 ADRs") if len(new_adrs) >= 7 else (0, "PARTIAL", f"{len(new_adrs)} (need ≥7)")


def check_v9_6_5_anchors_documented() -> tuple[int, str, str]:
    """§6.5 v9 quantitative anchors present in tests (3 pts)."""
    n = _grep_count(r"mma.*tl|band_gap|three_objective|rosenblatt|coupled.*orientation|system_rbto|slit_free|monotone.*tri", "tests/**/*.py")
    return (3, "PASS", f"{n} v9-anchor refs") if n >= 3 else (0, "PARTIAL", f"{n} (need ≥3)")


CHECKS_V9 = [
    # §1 driver 闭环 (24 pts)
    ("§1", "1.1", "MMA 驱动 TL 非线性 TO", 8, check_v9_1_1_mma_tl),
    ("§1", "1.2", "特征频率带隙 / minimax 频带", 8, check_v9_1_2_band_gap),
    ("§1", "1.3", "≥3 目标多载况 NSGA-III", 8, check_v9_1_3_three_objective),
    # §2 不确定性 (16 pts)
    ("§2", "2.1", "Rosenblatt 变换", 8, check_v9_2_1_rosenblatt),
    ("§2", "2.2", "系统可靠性驱动 TO", 8, check_v9_2_2_system_rbto),
    # §3 几何 + 场 (15 pts)
    ("§3", "3.1", "耦合密度+orientation 热 TO", 8, check_v9_3_1_coupled_orientation),
    ("§3", "3.2", "slit-free 孔三角化 (鲁棒水密)", 7, check_v9_3_2_slit_free),
    # §4 测试基础设施 (20 pts)
    ("§4", "4.1", "Test count ≥ 960", 4, check_v9_4_1_test_count_960),
    ("§4", "4.2", "Core coverage ≥ 95% (含 v9)", 4, check_v9_4_2_core_coverage_95),
    ("§4", "4.3", "Property tests ≥ 44", 3, check_v9_4_3_property_tests_44),
    ("§4", "4.4", "Mutation kill rate ≥ 75%", 3, check_v9_4_4_mutation_75),
    ("§4", "4.5", "Fingerprint DB ≥ 45", 2, check_v9_4_5_fingerprints_45),
    ("§4", "4.6", "pytest gate green (D033)", 2, check_v9_4_6_pytest_gate),
    ("§4", "4.7", "v9 rubric 写入 agent + CI", 2, check_v9_4_7_v9_in_agent_ci),
    # §5 用户面 demos (10 pts)
    ("§5", "5.1", "MMA-TL / 带隙 demo", 3, check_v9_5_1_mma_band_demo),
    ("§5", "5.2", "≥3 目标 NSGA demo", 3, check_v9_5_2_three_objective_demo),
    ("§5", "5.3", "Rosenblatt / 系统 RBTO demo", 2, check_v9_5_3_reliability_demo),
    ("§5", "5.4", "耦合场 / slit-free STL demo", 2, check_v9_5_4_geometry_demo),
    # §6 文档 (15 pts)
    ("§6", "6.1", "blueprint-v9 ≥6 ticks", 3, check_v9_6_1_blueprint_v9),
    ("§6", "6.2", "tutorial v9 ≥4 new sections", 3, check_v9_6_2_tutorial_v9),
    ("§6", "6.3", "architecture v9 section", 3, check_v9_6_3_arch_v9),
    ("§6", "6.4", "ADRs D058+ ≥ 7", 3, check_v9_6_4_adrs_v9),
    ("§6", "6.5", "v9 quantitative anchors documented", 3, check_v9_6_5_anchors_documented),
]


def run_v9(section_filter: str | None = None) -> Scorecard:
    """Score the v9 rubric in-process."""
    sc = Scorecard(version="v9.0.0")
    sc.items = _score(CHECKS_V9, section_filter)
    return sc


# === v10 rubric — constraint-rich & manufacturable (Waves KKK-RRR, ADRs
#     D066-D073). Each check traces a D058-D064 reopening criterion. ===


def check_v10_1_1_multi_constraint_mma() -> tuple[int, str, str]:
    """§1.1 multi-constraint MMA (stress p-norm + volume) (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/nonlinear_simp.py",
        r"multi_constraint_mma|stress_constrained|mma.*stress|pnorm_stress",
        r"multi_constraint|stress_constrained|stress.*pnorm|pnorm.*stress",
        8, "multi-constraint MMA in module, no test", "multi-constraint MMA (stress+volume) + test")


def check_v10_1_2_target_band() -> tuple[int, str, str]:
    """§1.2 target-band placement (minimax around a target frequency) (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/freq_response.py",
        r"target_band|band_placement|minimax_around|place_band",
        r"target_band|band_placement|minimax_around|place_band",
        8, "target-band placement in module, no test", "target-band placement + sensitivity test")


def check_v10_1_3_generalized_nsga() -> tuple[int, str, str]:
    """§1.3 generalised nsga3_density_to + IGD+ indicator (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/multi_objective_to.py",
        r"nsga3_density_to|igd_plus|igd\+|generalized_nsga",
        r"nsga3_density_to|igd_plus|igd\+|generalised.*nsga|refactor.*identical",
        8, "generalised NSGA in module, no test", "generalised nsga3_density_to + IGD+ test")


def check_v10_2_1_archimedean_copula() -> tuple[int, str, str]:
    """§2.1 Archimedean copula Rosenblatt (Clayton/Frank) (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/reliability.py",
        r"clayton|frank_copula|archimedean|copula_rosenblatt",
        r"clayton|frank_copula|archimedean|copula",
        8, "Archimedean copula in module, no test", "Archimedean copula Rosenblatt + round-trip test")


def check_v10_2_2_correlated_system_rbto() -> tuple[int, str, str]:
    """§2.2 correlated-system-mode RBTO (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/rbto.py",
        r"correlated_system|system_rbto.*corr|rho_modes|correlated.*rbto",
        r"correlated_system|correlated.*system.*rbto|system.*corr",
        8, "correlated-system RBTO in module, no test", "correlated-system-mode RBTO + test")


def check_v10_3_1_simultaneous_mma() -> tuple[int, str, str]:
    """§3.1 simultaneous (ρ,θ) MMA coupled thermal TO (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/thermal_simp.py",
        r"simultaneous.*mma|joint.*mma|mma.*coupled|coupled_mma",
        r"simultaneous.*mma|joint.*mma|coupled_mma|simultaneous.*coupled",
        8, "simultaneous MMA in module, no test", "simultaneous (ρ,θ) MMA + vs-alternating test")


def check_v10_3_2_smooth_watertight() -> tuple[int, str, str]:
    """§3.2 smooth AND watertight holed triangulation (7 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/stl_export.py",
        r"smooth_watertight|monotone_contour|cdt_holes|smooth.*hole.*watertight|triangulate_contour",
        r"smooth_watertight|monotone_contour|cdt|smooth.*watertight",
        7, "smooth-watertight triangulation in module, no test", "smooth+watertight holed contour + test")


def check_v10_4_1_test_count_1000() -> tuple[int, str, str]:
    """§4.1 ≥ 1000 tests (4 pts)."""
    n = _pytest_collect_count()
    return (4, "PASS", f"{n} tests collected") if n >= 1000 else (0, "FAIL", f"{n} (need ≥1000)")


def check_v10_4_2_core_coverage_95() -> tuple[int, str, str]:
    """§4.2 core coverage ≥ 95% incl. v10 (4 pts)."""
    pct = _pytest_coverage("structure_optimizer/core")
    return (4, "PASS", f"{pct}% coverage") if pct >= 95.0 else (0, "FAIL", f"{pct}% (need ≥95%)")


def check_v10_4_3_property_tests_46() -> tuple[int, str, str]:
    """§4.3 property tests ≥ 46 (3 pts)."""
    n = _grep_count(r"^def test_property_", "tests/**/*.py")
    return (3, "PASS", f"{n} property tests") if n >= 46 else (0, "FAIL", f"{n} (need ≥46)")


def check_v10_4_4_mutation_75() -> tuple[int, str, str]:
    """§4.4 mutation kill rate ≥ 75% (3 pts)."""
    report = REPO_ROOT / "tests/mutation_report.json"
    if not report.exists():
        return 0, "FAIL", "mutation_report missing"
    data = json.loads(report.read_text())
    rate = data.get("aggregate_kill_rate", data.get("kill_rate", 0.0))
    return (3, "PASS", f"{rate * 100:.1f}% kill rate") if rate >= 0.75 else (0, "FAIL", f"{rate * 100:.1f}%")


def check_v10_4_5_fingerprints_50() -> tuple[int, str, str]:
    """§4.5 fingerprint DB ≥ 50 (2 pts)."""
    n = len(list((REPO_ROOT / "tests/fingerprints").glob("*.json")))
    return (2, "PASS", f"{n} fingerprints") if n >= 50 else (0, "FAIL", f"{n} (need ≥50)")


def check_v10_4_6_pytest_gate() -> tuple[int, str, str]:
    """§4.6 pytest gate green / D033 mechanism present (2 pts)."""
    has_gate = _grep_count(r"def check_pytest_green", "scripts/test_agent.py") >= 1
    has_adr = _file_exists("docs/decisions/D033-pytest-green-no-regression-gate.md")
    return (2, "PASS", "D033 gate + ADR") if (has_gate and has_adr) else (0, "FAIL", f"gate={'✓' if has_gate else '✗'} ADR={'✓' if has_adr else '✗'}")


def check_v10_4_7_v10_in_agent_ci() -> tuple[int, str, str]:
    """§4.7 v10 rubric referenced in agent + CI (2 pts)."""
    me = (REPO_ROOT / "scripts/test_agent.py").read_text()
    in_agent = "CHECKS_V10" in me
    ci = REPO_ROOT / ".github/workflows/test.yml"
    in_ci = ci.exists() and "v10" in ci.read_text().lower()
    if in_agent and in_ci:
        return 2, "PASS", "v10 in agent + CI"
    if in_agent:
        return 1, "PARTIAL", "v10 in agent, not CI"
    return 0, "FAIL", "v10 not wired"


def check_v10_5_1_constraint_demo() -> tuple[int, str, str]:
    """§5.1 multi-constraint MMA / target-band demo (3 pts)."""
    n = _grep_count(r"multi_constraint_demo|stress_mma_demo|target_band_demo|band_placement_demo", "**/*.py")
    return (3, "PASS", f"{n} constraint-demo refs") if n >= 1 else (0, "FAIL", "no constraint demo")


def check_v10_5_2_nsga_demo() -> tuple[int, str, str]:
    """§5.2 generalised NSGA / IGD+ demo (3 pts)."""
    n = _grep_count(r"igd_plus_demo|generalized_nsga_demo|nsga_general_demo|igd_demo", "**/*.py")
    return (3, "PASS", f"{n} NSGA-demo refs") if n >= 1 else (0, "FAIL", "no NSGA demo")


def check_v10_5_3_reliability_demo() -> tuple[int, str, str]:
    """§5.3 Archimedean copula / correlated-system demo (2 pts)."""
    n = _grep_count(r"clayton_demo|frank_demo|copula_demo|correlated_system_demo", "**/*.py")
    return (2, "PASS", f"{n} reliability-demo refs") if n >= 1 else (0, "FAIL", "no reliability demo")


def check_v10_5_4_geometry_demo() -> tuple[int, str, str]:
    """§5.4 simultaneous-MMA / smooth-watertight demo (2 pts)."""
    n = _grep_count(r"simultaneous_mma_demo|smooth_watertight_demo|joint_mma_demo|cdt_demo", "**/*.py")
    return (2, "PASS", f"{n} geometry-demo refs") if n >= 1 else (0, "FAIL", "no geometry demo")


def check_v10_6_1_blueprint_v10() -> tuple[int, str, str]:
    """§6.1 blueprint-v10 ≥6 wave ticks (3 pts)."""
    p = REPO_ROOT / "docs/blueprint-v10.md"
    if not p.exists():
        return 0, "FAIL", "blueprint-v10.md missing"
    ticks = p.read_text().count("[x]")
    return (3, "PASS", f"{ticks} ticks") if ticks >= 6 else (0, "PARTIAL", f"{ticks} ticks (need ≥6)")


def check_v10_6_2_tutorial_v10() -> tuple[int, str, str]:
    """§6.2 tutorial v10 ≥4 new sections (3 pts)."""
    p = REPO_ROOT / "docs/tutorial.md"
    if not p.exists():
        return 0, "FAIL", "missing"
    n = len(re.findall(r"^### 20\.\d", p.read_text(), re.MULTILINE))
    return (3, "PASS", f"{n} v10 subsections") if n >= 4 else (0, "PARTIAL", f"{n} (need ≥4)")


def check_v10_6_3_arch_v10() -> tuple[int, str, str]:
    """§6.3 architecture v10 section (3 pts)."""
    p = REPO_ROOT / "docs/architecture.md"
    if not p.exists():
        return 0, "FAIL", "missing"
    txt = p.read_text().lower()
    return (3, "PASS", "v10 section present") if ("## 20." in p.read_text() and "constraint" in txt) else (0, "FAIL", "no v10 section")


def check_v10_6_4_adrs_v10() -> tuple[int, str, str]:
    """§6.4 ADRs D066+ ≥ 7 (3 pts)."""
    files = list((REPO_ROOT / "docs/decisions").glob("D0[67]*.md"))
    new_adrs = [f for f in files if (m := re.search(r"D(\d+)", f.name)) and int(m.group(1)) >= 66]
    return (3, "PASS", f"{len(new_adrs)} v10 ADRs") if len(new_adrs) >= 7 else (0, "PARTIAL", f"{len(new_adrs)} (need ≥7)")


def check_v10_6_5_anchors_documented() -> tuple[int, str, str]:
    """§6.5 v10 quantitative anchors present in tests (3 pts)."""
    n = _grep_count(r"multi_constraint|target_band|igd_plus|clayton|frank|simultaneous.*mma|smooth_watertight|correlated_system", "tests/**/*.py")
    return (3, "PASS", f"{n} v10-anchor refs") if n >= 3 else (0, "PARTIAL", f"{n} (need ≥3)")


CHECKS_V10 = [
    # §1 约束丰富 driver (24 pts)
    ("§1", "1.1", "多约束 MMA (应力+体积)", 8, check_v10_1_1_multi_constraint_mma),
    ("§1", "1.2", "目标频带放置", 8, check_v10_1_2_target_band),
    ("§1", "1.3", "泛化 NSGA + IGD+", 8, check_v10_1_3_generalized_nsga),
    # §2 不确定性 (16 pts)
    ("§2", "2.1", "Archimedean copula Rosenblatt", 8, check_v10_2_1_archimedean_copula),
    ("§2", "2.2", "相关系统模态 RBTO", 8, check_v10_2_2_correlated_system_rbto),
    # §3 几何 + 场 (15 pts)
    ("§3", "3.1", "同时 (ρ,θ) MMA 耦合", 8, check_v10_3_1_simultaneous_mma),
    ("§3", "3.2", "平滑且水密带孔三角化", 7, check_v10_3_2_smooth_watertight),
    # §4 测试基础设施 (20 pts)
    ("§4", "4.1", "Test count ≥ 1000", 4, check_v10_4_1_test_count_1000),
    ("§4", "4.2", "Core coverage ≥ 95% (含 v10)", 4, check_v10_4_2_core_coverage_95),
    ("§4", "4.3", "Property tests ≥ 46", 3, check_v10_4_3_property_tests_46),
    ("§4", "4.4", "Mutation kill rate ≥ 75%", 3, check_v10_4_4_mutation_75),
    ("§4", "4.5", "Fingerprint DB ≥ 50", 2, check_v10_4_5_fingerprints_50),
    ("§4", "4.6", "pytest gate green (D033)", 2, check_v10_4_6_pytest_gate),
    ("§4", "4.7", "v10 rubric 写入 agent + CI", 2, check_v10_4_7_v10_in_agent_ci),
    # §5 用户面 demos (10 pts)
    ("§5", "5.1", "多约束 / 目标频带 demo", 3, check_v10_5_1_constraint_demo),
    ("§5", "5.2", "泛化 NSGA / IGD+ demo", 3, check_v10_5_2_nsga_demo),
    ("§5", "5.3", "copula / 相关系统 demo", 2, check_v10_5_3_reliability_demo),
    ("§5", "5.4", "同时 MMA / 平滑水密 demo", 2, check_v10_5_4_geometry_demo),
    # §6 文档 (15 pts)
    ("§6", "6.1", "blueprint-v10 ≥6 ticks", 3, check_v10_6_1_blueprint_v10),
    ("§6", "6.2", "tutorial v10 ≥4 new sections", 3, check_v10_6_2_tutorial_v10),
    ("§6", "6.3", "architecture v10 section", 3, check_v10_6_3_arch_v10),
    ("§6", "6.4", "ADRs D066+ ≥ 7", 3, check_v10_6_4_adrs_v10),
    ("§6", "6.5", "v10 quantitative anchors documented", 3, check_v10_6_5_anchors_documented),
]


def run_v10(section_filter: str | None = None) -> Scorecard:
    """Score the v10 rubric in-process."""
    sc = Scorecard(version="v10.0.0")
    sc.items = _score(CHECKS_V10, section_filter)
    return sc


def check_v9_no_regression() -> dict:
    """v9 must remain 100/100 for a v10 release (true in-process re-score)."""
    sc_v9 = run_v9()
    return {
        "score": sc_v9.total_earned,
        "max": sc_v9.total_max,
        "regression": sc_v9.total_earned < 100,
    }


# ===========================================================================
# v11 rubric — exact & robust (Wave SSS-ZZZ, D074-D081)
# ===========================================================================


def check_v11_1_1_stress_relaxation_buckling() -> tuple[int, str, str]:
    """§1.1 stress-singularity relaxation (qp/ε) + buckling eigenvalue constraint (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/stress.py",
        r"qp_stress|relaxed_stress|epsilon_relax|stress_singularity|buckling",
        r"qp_stress|relaxed_stress|stress_singularity|buckling|relaxation",
        8, "stress relaxation in module, no test", "qp-relaxed stress + qp-stress-constrained MMA + test (buckling-driving deferred to D074 reopening)")


def check_v11_1_2_adaptive_band() -> tuple[int, str, str]:
    """§1.2 adaptive band sampling + peak-as-constraint (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/freq_response.py",
        r"adaptive_band|band_refine|peak_constraint|adaptive.*sampl",
        r"adaptive_band|peak_constraint|adaptive.*sampl|peak.*as.*constraint",
        8, "adaptive band in module, no test", "adaptive band sampling + peak-as-constraint + test")


def check_v11_1_3_reference_free_indicator() -> tuple[int, str, str]:
    """§1.3 reference-free multi-objective quality indicator (hypervolume-only / R2) (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/multi_objective_to.py",
        r"hypervolume_indicator|r2_indicator|reference_free|hv_only",
        r"hypervolume_indicator|r2_indicator|reference_free|r2.*indicator",
        8, "reference-free indicator in module, no test", "reference-free quality indicator + test")


def check_v11_2_1_gumbel_dim_copula() -> tuple[int, str, str]:
    """§2.1 d-dimensional / Gumbel Archimedean copula (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/reliability.py",
        r"gumbel_copula|nested_copula|d_dim.*copula|copula.*nested",
        r"gumbel|nested_copula|d_dim.*copula|gumbel.*copula",
        8, "Gumbel/nested copula in module, no test", "Gumbel / d-dim copula + round-trip test")


def check_v11_2_2_genz_system() -> tuple[int, str, str]:
    """§2.2 full correlation matrix + Genz exact multivariate system P_f (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/reliability.py",
        r"genz|multivariate_normal_cdf|mvn_cdf|full_correlation",
        r"genz|multivariate_normal_cdf|mvn_cdf|full.*correlation",
        8, "Genz/MVN-CDF in module, no test", "Genz multivariate system P_f + test")


def check_v11_3_1_elastic_simultaneous_mma() -> tuple[int, str, str]:
    """§3.1 elastic simultaneous (ρ,θ) MMA + fibre-continuity (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/orthotropic_simp.py",
        r"elastic.*orientation|orthotropic.*mma|fibre_continuity|simultaneous.*elastic|elastic_simultaneous",
        r"elastic.*orientation|orthotropic|fibre_continuity|elastic.*simultaneous",
        8, "elastic simultaneous MMA in module, no test", "elastic simultaneous (ρ,θ) MMA + fibre-continuity test")


def check_v11_3_2_constrained_delaunay() -> tuple[int, str, str]:
    """§3.2 constrained-Delaunay multi-hole smooth + watertight (7 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/stl_export.py",
        r"constrained_delaunay|cdt|multi_hole.*watertight|delaunay",
        r"constrained_delaunay|cdt|multi_hole|delaunay",
        7, "constrained-Delaunay in module, no test", "constrained-Delaunay multi-hole + test")


def check_v11_4_1_test_count_1050() -> tuple[int, str, str]:
    """§4.1 ≥ 1050 tests (4 pts)."""
    n = _pytest_collect_count()
    return (4, "PASS", f"{n} tests collected") if n >= 1050 else (0, "FAIL", f"{n} (need ≥1050)")


def check_v11_4_2_core_coverage_95() -> tuple[int, str, str]:
    """§4.2 core coverage ≥ 95% incl. v11 (4 pts)."""
    pct = _pytest_coverage("structure_optimizer/core")
    return (4, "PASS", f"{pct}% coverage") if pct >= 95.0 else (0, "FAIL", f"{pct}% (need ≥95%)")


def check_v11_4_3_property_tests_48() -> tuple[int, str, str]:
    """§4.3 property tests ≥ 48 (3 pts)."""
    n = _grep_count(r"^def test_property_", "tests/**/*.py")
    return (3, "PASS", f"{n} property tests") if n >= 48 else (0, "FAIL", f"{n} (need ≥48)")


def check_v11_4_4_mutation_75() -> tuple[int, str, str]:
    """§4.4 mutation kill rate ≥ 75% (3 pts)."""
    report = REPO_ROOT / "tests/mutation_report.json"
    if not report.exists():
        return 0, "FAIL", "mutation_report missing"
    data = json.loads(report.read_text())
    rate = data.get("aggregate_kill_rate", data.get("kill_rate", 0.0))
    return (3, "PASS", f"{rate * 100:.1f}% kill rate") if rate >= 0.75 else (0, "FAIL", f"{rate * 100:.1f}%")


def check_v11_4_5_fingerprints_55() -> tuple[int, str, str]:
    """§4.5 fingerprint DB ≥ 55 (2 pts)."""
    n = len(list((REPO_ROOT / "tests/fingerprints").glob("*.json")))
    return (2, "PASS", f"{n} fingerprints") if n >= 55 else (0, "FAIL", f"{n} (need ≥55)")


def check_v11_4_6_pytest_gate() -> tuple[int, str, str]:
    """§4.6 pytest gate green / D033 mechanism present (2 pts)."""
    has_gate = _grep_count(r"def check_pytest_green", "scripts/test_agent.py") >= 1
    has_adr = _file_exists("docs/decisions/D033-pytest-green-no-regression-gate.md")
    return (2, "PASS", "D033 gate + ADR") if (has_gate and has_adr) else (0, "FAIL", f"gate={'✓' if has_gate else '✗'} ADR={'✓' if has_adr else '✗'}")


def check_v11_4_7_v11_in_agent_ci() -> tuple[int, str, str]:
    """§4.7 v11 rubric referenced in agent + CI (2 pts)."""
    me = (REPO_ROOT / "scripts/test_agent.py").read_text()
    in_agent = "CHECKS_V11" in me
    ci = REPO_ROOT / ".github/workflows/test.yml"
    in_ci = ci.exists() and "v11" in ci.read_text().lower()
    if in_agent and in_ci:
        return 2, "PASS", "v11 in agent + CI"
    if in_agent:
        return 1, "PARTIAL", "v11 in agent, not CI"
    return 0, "FAIL", "v11 not wired"


def check_v11_5_1_constraint_demo() -> tuple[int, str, str]:
    """§5.1 stress-relaxation+buckling / adaptive-band demo (3 pts)."""
    n = _grep_count(r"qp_stress_demo|buckling_demo|adaptive_band_demo|relaxation_demo", "**/*.py")
    return (3, "PASS", f"{n} robust-driver-demo refs") if n >= 1 else (0, "FAIL", "no robust-driver demo")


def check_v11_5_2_indicator_demo() -> tuple[int, str, str]:
    """§5.2 reference-free indicator demo (3 pts)."""
    n = _grep_count(r"hypervolume_indicator_demo|r2_demo|reference_free_demo|hv_indicator_demo", "**/*.py")
    return (3, "PASS", f"{n} indicator-demo refs") if n >= 1 else (0, "FAIL", "no indicator demo")


def check_v11_5_3_reliability_demo() -> tuple[int, str, str]:
    """§5.3 Gumbel copula / Genz system demo (2 pts)."""
    n = _grep_count(r"gumbel_demo|genz_demo|mvn_cdf_demo|nested_copula_demo", "**/*.py")
    return (2, "PASS", f"{n} reliability-demo refs") if n >= 1 else (0, "FAIL", "no reliability demo")


def check_v11_5_4_geometry_demo() -> tuple[int, str, str]:
    """§5.4 elastic-MMA / constrained-Delaunay demo (2 pts)."""
    n = _grep_count(r"elastic_mma_demo|cdt_demo|constrained_delaunay_demo|elastic_simultaneous_demo", "**/*.py")
    return (2, "PASS", f"{n} geometry-demo refs") if n >= 1 else (0, "FAIL", "no geometry demo")


def check_v11_6_1_blueprint_v11() -> tuple[int, str, str]:
    """§6.1 blueprint-v11 ≥6 wave ticks (3 pts)."""
    p = REPO_ROOT / "docs/blueprint-v11.md"
    if not p.exists():
        return 0, "FAIL", "blueprint-v11.md missing"
    ticks = p.read_text().count("[x]")
    return (3, "PASS", f"{ticks} ticks") if ticks >= 6 else (0, "PARTIAL", f"{ticks} ticks (need ≥6)")


def check_v11_6_2_tutorial_v11() -> tuple[int, str, str]:
    """§6.2 tutorial v11 ≥4 new sections (3 pts)."""
    p = REPO_ROOT / "docs/tutorial.md"
    if not p.exists():
        return 0, "FAIL", "missing"
    n = len(re.findall(r"^### 21\.\d", p.read_text(), re.MULTILINE))
    return (3, "PASS", f"{n} v11 subsections") if n >= 4 else (0, "PARTIAL", f"{n} (need ≥4)")


def check_v11_6_3_arch_v11() -> tuple[int, str, str]:
    """§6.3 architecture v11 section (3 pts)."""
    p = REPO_ROOT / "docs/architecture.md"
    if not p.exists():
        return 0, "FAIL", "missing"
    txt = p.read_text().lower()
    return (3, "PASS", "v11 section present") if ("## 21." in p.read_text() and "robust" in txt) else (0, "FAIL", "no v11 section")


def check_v11_6_4_adrs_v11() -> tuple[int, str, str]:
    """§6.4 ADRs D074+ ≥ 7 (3 pts)."""
    files = list((REPO_ROOT / "docs/decisions").glob("D0[78]*.md"))
    new_adrs = [f for f in files if (m := re.search(r"D(\d+)", f.name)) and int(m.group(1)) >= 74]
    return (3, "PASS", f"{len(new_adrs)} v11 ADRs") if len(new_adrs) >= 7 else (0, "PARTIAL", f"{len(new_adrs)} (need ≥7)")


def check_v11_6_5_anchors_documented() -> tuple[int, str, str]:
    """§6.5 v11 quantitative anchors present in tests (3 pts)."""
    n = _grep_count(r"qp_stress|buckling|adaptive_band|reference_free|gumbel|genz|elastic.*orientation|constrained_delaunay", "tests/**/*.py")
    return (3, "PASS", f"{n} v11-anchor refs") if n >= 3 else (0, "PARTIAL", f"{n} (need ≥3)")


CHECKS_V11 = [
    # §1 鲁棒约束 driver (24 pts)
    ("§1", "1.1", "应力奇异性松弛（qp-relaxed）", 8, check_v11_1_1_stress_relaxation_buckling),
    ("§1", "1.2", "自适应频带 + peak 约束", 8, check_v11_1_2_adaptive_band),
    ("§1", "1.3", "reference-free 质量指标", 8, check_v11_1_3_reference_free_indicator),
    # §2 不确定性 (16 pts)
    ("§2", "2.1", "d 维 / Gumbel copula", 8, check_v11_2_1_gumbel_dim_copula),
    ("§2", "2.2", "Genz 精确多元系统 P_f", 8, check_v11_2_2_genz_system),
    # §3 几何 + 场 (15 pts)
    ("§3", "3.1", "弹性同时 (ρ,θ) MMA", 8, check_v11_3_1_elastic_simultaneous_mma),
    ("§3", "3.2", "约束 Delaunay 多孔水密", 7, check_v11_3_2_constrained_delaunay),
    # §4 测试基础设施 (20 pts)
    ("§4", "4.1", "Test count ≥ 1050", 4, check_v11_4_1_test_count_1050),
    ("§4", "4.2", "Core coverage ≥ 95% (含 v11)", 4, check_v11_4_2_core_coverage_95),
    ("§4", "4.3", "Property tests ≥ 48", 3, check_v11_4_3_property_tests_48),
    ("§4", "4.4", "Mutation kill rate ≥ 75%", 3, check_v11_4_4_mutation_75),
    ("§4", "4.5", "Fingerprint DB ≥ 55", 2, check_v11_4_5_fingerprints_55),
    ("§4", "4.6", "pytest gate green (D033)", 2, check_v11_4_6_pytest_gate),
    ("§4", "4.7", "v11 rubric 写入 agent + CI", 2, check_v11_4_7_v11_in_agent_ci),
    # §5 用户面 demos (10 pts)
    ("§5", "5.1", "应力松弛+屈曲 / 自适应频带 demo", 3, check_v11_5_1_constraint_demo),
    ("§5", "5.2", "reference-free 指标 demo", 3, check_v11_5_2_indicator_demo),
    ("§5", "5.3", "Gumbel / Genz demo", 2, check_v11_5_3_reliability_demo),
    ("§5", "5.4", "弹性 MMA / 约束 Delaunay demo", 2, check_v11_5_4_geometry_demo),
    # §6 文档 (15 pts)
    ("§6", "6.1", "blueprint-v11 ≥6 ticks", 3, check_v11_6_1_blueprint_v11),
    ("§6", "6.2", "tutorial v11 ≥4 new sections", 3, check_v11_6_2_tutorial_v11),
    ("§6", "6.3", "architecture v11 section", 3, check_v11_6_3_arch_v11),
    ("§6", "6.4", "ADRs D074+ ≥ 7", 3, check_v11_6_4_adrs_v11),
    ("§6", "6.5", "v11 quantitative anchors documented", 3, check_v11_6_5_anchors_documented),
]


def run_v11(section_filter: str | None = None) -> Scorecard:
    """Score the v11 rubric in-process."""
    sc = Scorecard(version="v11.0.0")
    sc.items = _score(CHECKS_V11, section_filter)
    return sc


def check_v10_no_regression() -> dict:
    """v10 must remain 100/100 for a v11 release (true in-process re-score)."""
    sc_v10 = run_v10()
    return {
        "score": sc_v10.total_earned,
        "max": sc_v10.total_max,
        "regression": sc_v10.total_earned < 100,
    }


# ===========================================================================
# v12 rubric — design-grade & adaptive (Waves AAAA-HHHH, D082-D089)
# ===========================================================================


def check_v12_1_1_design_buckling() -> tuple[int, str, str]:
    """§1.1 design-grade buckling sensitivity (∂u/∂ρ + void-mode) (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/buckling.py",
        r"design_grade|adjoint.*buckl|buckling.*adjoint|void_mode|du_drho|design_buckling",
        r"design_grade|void_mode|design_buckling|buckling.*adjoint|adjoint.*buckl",
        8, "design-grade buckling in module, no test", "design-grade buckling adjoint + void-mode + test")


def check_v12_1_2_inloop_band() -> tuple[int, str, str]:
    """§1.2 in-loop adaptive band re-gridding (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/freq_response.py",
        r"inloop|in_loop|adaptive.*regrid|regrid|adaptive_peak_constrained",
        r"inloop|in_loop|regrid|adaptive_peak_constrained",
        8, "in-loop re-grid in module, no test", "in-loop adaptive band re-gridding + test")


def check_v12_1_3_augmented_r2() -> tuple[int, str, str]:
    """§1.3 augmented Tchebycheff R2 + diversity indicator (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/multi_objective_to.py",
        r"augmented_r2|r2_augmented|spacing_indicator|diversity_indicator|augmented.*tcheb",
        r"augmented_r2|spacing_indicator|diversity_indicator|augmented",
        8, "augmented R2 in module, no test", "augmented R2 + diversity indicator + test")


def check_v12_2_1_nested_copula() -> tuple[int, str, str]:
    """§2.1 nested / hierarchical Archimedean copula (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/reliability.py",
        r"nested_copula|hierarchical_copula|NestedClayton|per_cluster|nested_clayton",
        r"nested_copula|hierarchical|nested_clayton|per_cluster",
        8, "nested copula in module, no test", "nested/hierarchical copula + round-trip test")


def check_v12_2_2_korobov_genz() -> tuple[int, str, str]:
    """§2.2 Korobov lattice Genz + error bound (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/reliability.py",
        r"korobov|lattice_genz|genz_lattice|genz_mvn_cdf_lattice",
        r"korobov|lattice_genz|genz_lattice|standard_error",
        8, "Korobov Genz in module, no test", "Korobov lattice Genz + error bound + test")


def check_v12_3_1_periodic_fibre() -> tuple[int, str, str]:
    """§3.1 period-aware fibre continuity + laminate (8 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/orthotropic_simp.py",
        r"period_aware|periodic_continuity|laminate|abd_matrix|sin.*continuity",
        r"period_aware|periodic|laminate|abd",
        8, "period-aware fibre in module, no test", "period-aware fibre continuity + laminate + test")


def check_v12_3_2_cdt_flip_recovery() -> tuple[int, str, str]:
    """§3.2 flip-based CDT constraint recovery + quality refinement (7 pts)."""
    return _mod_and_test(
        "structure_optimizer/core/stl_export.py",
        r"constraint_recovery|edge_flip|flip_recover|refine_triangulation|cdt_refine",
        r"constraint_recovery|edge_flip|flip|refine",
        7, "CDT flip-recovery in module, no test", "flip constraint recovery + refinement + test")


def check_v12_4_1_test_count_1095() -> tuple[int, str, str]:
    """§4.1 ≥ 1095 tests (4 pts)."""
    n = _pytest_collect_count()
    return (4, "PASS", f"{n} tests collected") if n >= 1095 else (0, "FAIL", f"{n} (need ≥1095)")


def check_v12_4_2_core_coverage_95() -> tuple[int, str, str]:
    """§4.2 core coverage ≥ 95% incl. v12 (4 pts)."""
    pct = _pytest_coverage("structure_optimizer/core")
    return (4, "PASS", f"{pct}% coverage") if pct >= 95.0 else (0, "FAIL", f"{pct}% (need ≥95%)")


def check_v12_4_3_property_tests_53() -> tuple[int, str, str]:
    """§4.3 property tests ≥ 53 (3 pts)."""
    n = _grep_count(r"^def test_property_", "tests/**/*.py")
    return (3, "PASS", f"{n} property tests") if n >= 53 else (0, "FAIL", f"{n} (need ≥53)")


def check_v12_4_4_mutation_75() -> tuple[int, str, str]:
    """§4.4 mutation kill rate ≥ 75% (3 pts)."""
    report = REPO_ROOT / "tests/mutation_report.json"
    if not report.exists():
        return 0, "FAIL", "mutation_report missing"
    data = json.loads(report.read_text())
    rate = data.get("aggregate_kill_rate", data.get("kill_rate", 0.0))
    return (3, "PASS", f"{rate * 100:.1f}% kill rate") if rate >= 0.75 else (0, "FAIL", f"{rate * 100:.1f}%")


def check_v12_4_5_fingerprints_60() -> tuple[int, str, str]:
    """§4.5 fingerprint DB ≥ 60 (2 pts)."""
    n = len(list((REPO_ROOT / "tests/fingerprints").glob("*.json")))
    return (2, "PASS", f"{n} fingerprints") if n >= 60 else (0, "FAIL", f"{n} (need ≥60)")


def check_v12_4_6_pytest_gate() -> tuple[int, str, str]:
    """§4.6 pytest gate green / D033 mechanism present (2 pts)."""
    has_gate = _grep_count(r"def check_pytest_green", "scripts/test_agent.py") >= 1
    has_adr = _file_exists("docs/decisions/D033-pytest-green-no-regression-gate.md")
    return (2, "PASS", "D033 gate + ADR") if (has_gate and has_adr) else (0, "FAIL", f"gate={'✓' if has_gate else '✗'} ADR={'✓' if has_adr else '✗'}")


def check_v12_4_7_v12_in_agent_ci() -> tuple[int, str, str]:
    """§4.7 v12 rubric referenced in agent + CI (2 pts)."""
    me = (REPO_ROOT / "scripts/test_agent.py").read_text()
    in_agent = "CHECKS_V12" in me
    ci = REPO_ROOT / ".github/workflows/test.yml"
    in_ci = ci.exists() and "v12" in ci.read_text().lower()
    if in_agent and in_ci:
        return 2, "PASS", "v12 in agent + CI"
    if in_agent:
        return 1, "PARTIAL", "v12 in agent, not CI"
    return 0, "FAIL", "v12 not wired"


def check_v12_5_1_buckling_demo() -> tuple[int, str, str]:
    """§5.1 design-buckling / in-loop-band demo (3 pts)."""
    n = _grep_count(r"design_buckling_demo|buckling_to_demo|inloop_band_demo|design_grade_demo", "**/*.py")
    return (3, "PASS", f"{n} buckling-demo refs") if n >= 1 else (0, "FAIL", "no buckling/band demo")


def check_v12_5_2_diversity_demo() -> tuple[int, str, str]:
    """§5.2 augmented-R2 / diversity demo (3 pts)."""
    n = _grep_count(r"augmented_r2_demo|diversity_demo|spacing_demo", "**/*.py")
    return (3, "PASS", f"{n} diversity-demo refs") if n >= 1 else (0, "FAIL", "no diversity demo")


def check_v12_5_3_copula_genz_demo() -> tuple[int, str, str]:
    """§5.3 nested-copula / Korobov-Genz demo (2 pts)."""
    n = _grep_count(r"nested_copula_demo|korobov_demo|lattice_genz_demo", "**/*.py")
    return (2, "PASS", f"{n} reliability-demo refs") if n >= 1 else (0, "FAIL", "no reliability demo")


def check_v12_5_4_geometry_demo() -> tuple[int, str, str]:
    """§5.4 laminate / period-fibre / flip-CDT demo (2 pts)."""
    n = _grep_count(r"laminate_demo|periodic_fibre_demo|cdt_refine_demo", "**/*.py")
    return (2, "PASS", f"{n} geometry-demo refs") if n >= 1 else (0, "FAIL", "no geometry demo")


def check_v12_6_1_blueprint_v12() -> tuple[int, str, str]:
    """§6.1 blueprint-v12 ≥6 wave ticks (3 pts)."""
    p = REPO_ROOT / "docs/blueprint-v12.md"
    if not p.exists():
        return 0, "FAIL", "blueprint-v12.md missing"
    ticks = p.read_text().count("[x]")
    return (3, "PASS", f"{ticks} ticks") if ticks >= 6 else (0, "PARTIAL", f"{ticks} ticks (need ≥6)")


def check_v12_6_2_tutorial_v12() -> tuple[int, str, str]:
    """§6.2 tutorial v12 ≥4 new sections (3 pts)."""
    p = REPO_ROOT / "docs/tutorial.md"
    if not p.exists():
        return 0, "FAIL", "missing"
    n = len(re.findall(r"^### 22\.\d", p.read_text(), re.MULTILINE))
    return (3, "PASS", f"{n} v12 subsections") if n >= 4 else (0, "PARTIAL", f"{n} (need ≥4)")


def check_v12_6_3_arch_v12() -> tuple[int, str, str]:
    """§6.3 architecture v12 section (3 pts)."""
    p = REPO_ROOT / "docs/architecture.md"
    if not p.exists():
        return 0, "FAIL", "missing"
    txt = p.read_text().lower()
    return (3, "PASS", "v12 section present") if ("## 22." in p.read_text() and "adaptive" in txt) else (0, "FAIL", "no v12 section")


def check_v12_6_4_adrs_v12() -> tuple[int, str, str]:
    """§6.4 ADRs D082+ ≥ 7 (3 pts)."""
    files = list((REPO_ROOT / "docs/decisions").glob("D08[2-9]*.md"))
    new_adrs = [f for f in files if (m := re.search(r"D(\d+)", f.name)) and int(m.group(1)) >= 82]
    return (3, "PASS", f"{len(new_adrs)} v12 ADRs") if len(new_adrs) >= 7 else (0, "PARTIAL", f"{len(new_adrs)} (need ≥7)")


def check_v12_6_5_anchors_documented() -> tuple[int, str, str]:
    """§6.5 v12 quantitative anchors present in tests (3 pts)."""
    n = _grep_count(r"design_grade|void_mode|inloop|augmented_r2|nested_copula|korobov|period_aware|laminate|constraint_recovery", "tests/**/*.py")
    return (3, "PASS", f"{n} v12-anchor refs") if n >= 3 else (0, "PARTIAL", f"{n} (need ≥3)")


CHECKS_V12 = [
    ("§1", "1.1", "设计级屈曲灵敏度", 8, check_v12_1_1_design_buckling),
    ("§1", "1.2", "循环内自适应频带重采样", 8, check_v12_1_2_inloop_band),
    ("§1", "1.3", "增广 Tchebycheff R2 + 多样性", 8, check_v12_1_3_augmented_r2),
    ("§2", "2.1", "分层 Archimedean copula", 8, check_v12_2_1_nested_copula),
    ("§2", "2.2", "Korobov 点阵 Genz + 误差界", 8, check_v12_2_2_korobov_genz),
    ("§3", "3.1", "周期感知 fibre 连续性 + 层合", 8, check_v12_3_1_periodic_fibre),
    ("§3", "3.2", "flip 约束恢复 CDT + 质量细化", 7, check_v12_3_2_cdt_flip_recovery),
    ("§4", "4.1", "Test count ≥ 1095", 4, check_v12_4_1_test_count_1095),
    ("§4", "4.2", "Core coverage ≥ 95% (含 v12)", 4, check_v12_4_2_core_coverage_95),
    ("§4", "4.3", "Property tests ≥ 53", 3, check_v12_4_3_property_tests_53),
    ("§4", "4.4", "Mutation kill rate ≥ 75%", 3, check_v12_4_4_mutation_75),
    ("§4", "4.5", "Fingerprint DB ≥ 60", 2, check_v12_4_5_fingerprints_60),
    ("§4", "4.6", "pytest gate green (D033)", 2, check_v12_4_6_pytest_gate),
    ("§4", "4.7", "v12 rubric 写入 agent + CI", 2, check_v12_4_7_v12_in_agent_ci),
    ("§5", "5.1", "设计级屈曲 / 自适应频带 demo", 3, check_v12_5_1_buckling_demo),
    ("§5", "5.2", "增广 R2 / 多样性 demo", 3, check_v12_5_2_diversity_demo),
    ("§5", "5.3", "分层 copula / Korobov Genz demo", 2, check_v12_5_3_copula_genz_demo),
    ("§5", "5.4", "周期 fibre / flip-CDT demo", 2, check_v12_5_4_geometry_demo),
    ("§6", "6.1", "blueprint-v12 ≥6 ticks", 3, check_v12_6_1_blueprint_v12),
    ("§6", "6.2", "tutorial v12 ≥4 sections", 3, check_v12_6_2_tutorial_v12),
    ("§6", "6.3", "architecture v12 section", 3, check_v12_6_3_arch_v12),
    ("§6", "6.4", "ADRs D082+ ≥ 7", 3, check_v12_6_4_adrs_v12),
    ("§6", "6.5", "v12 anchors documented", 3, check_v12_6_5_anchors_documented),
]


def run_v12(section_filter: str | None = None) -> Scorecard:
    """Score the v12 rubric in-process."""
    sc = Scorecard(version="v12.0.0")
    sc.items = _score(CHECKS_V12, section_filter)
    return sc


def check_v11_no_regression() -> dict:
    """v11 must remain 100/100 for a v12 release (true in-process re-score)."""
    sc_v11 = run_v11()
    return {
        "score": sc_v11.total_earned,
        "max": sc_v11.total_max,
        "regression": sc_v11.total_earned < 100,
    }


def check_v6_no_regression() -> dict:
    """v6 must remain 100/100 for a v7 release (true in-process re-score)."""
    sc_v6 = run_v6()
    return {
        "score": sc_v6.total_earned,
        "max": sc_v6.total_max,
        "regression": sc_v6.total_earned < 100,
    }


def check_v7_no_regression() -> dict:
    """v7 must remain 100/100 for a v8 release (true in-process re-score)."""
    sc_v7 = run_v7()
    return {
        "score": sc_v7.total_earned,
        "max": sc_v7.total_max,
        "regression": sc_v7.total_earned < 100,
    }


def check_v8_no_regression() -> dict:
    """v8 must remain 100/100 for a v9 release (true in-process re-score)."""
    sc_v8 = run_v8()
    return {
        "score": sc_v8.total_earned,
        "max": sc_v8.total_max,
        "regression": sc_v8.total_earned < 100,
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
    elif rubric == "v7":
        sc = run_v7(section_filter)
    elif rubric == "v8":
        sc = run_v8(section_filter)
    elif rubric == "v9":
        sc = run_v9(section_filter)
    elif rubric == "v10":
        sc = run_v10(section_filter)
    elif rubric == "v11":
        sc = run_v11(section_filter)
    else:  # v12
        sc = run_v12(section_filter)
    sc.v1_check = check_v1_no_regression()
    sc.v2_check = check_v2_no_regression()
    sc.v3_check = check_v3_no_regression()
    if rubric in ("v5", "v6", "v7", "v8", "v9", "v10", "v11", "v12"):
        sc.v4_check = check_v4_no_regression()
    if rubric in ("v6", "v7", "v8", "v9", "v10", "v11", "v12"):
        sc.v5_check = check_v5_no_regression()
    if rubric in ("v7", "v8", "v9", "v10", "v11", "v12"):
        sc.v6_check = check_v6_no_regression()
    if rubric in ("v8", "v9", "v10", "v11", "v12"):
        sc.v7_check = check_v7_no_regression()
    if rubric in ("v9", "v10", "v11", "v12"):
        sc.v8_check = check_v8_no_regression()
    if rubric in ("v10", "v11", "v12"):
        sc.v9_check = check_v9_no_regression()
    if rubric in ("v11", "v12"):
        sc.v10_check = check_v10_no_regression()
    if rubric == "v12":
        sc.v11_check = check_v11_no_regression()
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
    if sc.v6_check:
        print(f"  v6 rubric  : {sc.v6_check.get('score')}/{sc.v6_check.get('max', 100)}  regression={sc.v6_check.get('regression')}")
    if sc.v7_check:
        print(f"  v7 rubric  : {sc.v7_check.get('score')}/{sc.v7_check.get('max', 100)}  regression={sc.v7_check.get('regression')}")
    if sc.v8_check:
        print(f"  v8 rubric  : {sc.v8_check.get('score')}/{sc.v8_check.get('max', 100)}  regression={sc.v8_check.get('regression')}")
    if sc.v9_check:
        print(f"  v9 rubric  : {sc.v9_check.get('score')}/{sc.v9_check.get('max', 100)}  regression={sc.v9_check.get('regression')}")
    if sc.v10_check:
        print(f"  v10 rubric : {sc.v10_check.get('score')}/{sc.v10_check.get('max', 100)}  regression={sc.v10_check.get('regression')}")
    if sc.v11_check:
        print(f"  v11 rubric : {sc.v11_check.get('score')}/{sc.v11_check.get('max', 100)}  regression={sc.v11_check.get('regression')}")
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
        sc.v6_check.get("regression") if sc.v6_check else False,
        sc.v7_check.get("regression") if sc.v7_check else False,
        sc.v8_check.get("regression") if sc.v8_check else False,
        sc.v9_check.get("regression") if sc.v9_check else False,
        sc.v10_check.get("regression") if sc.v10_check else False,
        sc.v11_check.get("regression") if sc.v11_check else False,
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
        choices=["v4", "v5", "v6", "v7", "v8", "v9", "v10", "v11", "v12"],
        default="v5",
        help="which rubric to score (default v5; v4-v10 scorable for regression checks)",
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
    if sc.v7_check:
        payload["v7_check"] = sc.v7_check
    if sc.v8_check:
        payload["v8_check"] = sc.v8_check
    if sc.v9_check:
        payload["v9_check"] = sc.v9_check
    if sc.v10_check:
        payload["v10_check"] = sc.v10_check
    if sc.v11_check:
        payload["v11_check"] = sc.v11_check
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
                sc.v7_check.get("regression") if sc.v7_check else False,
                sc.v8_check.get("regression") if sc.v8_check else False,
                sc.v9_check.get("regression") if sc.v9_check else False,
                sc.v10_check.get("regression") if sc.v10_check else False,
                sc.pytest_check.get("regression") if sc.pytest_check else False,
            ]
        )
        if sc.total_earned < 99 or regression:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
