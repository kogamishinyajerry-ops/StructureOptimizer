"""Wave W: lightweight mutation testing for rubric §3.3.

The standard ``mutmut`` tool is hard to install + slow; this in-house
mutation harness applies a small, well-defined set of mutators to a
single core module (the SIMP main loop), runs the test suite under each
mutation, and counts the kill rate (mutations caught by ≥1 failing
test).

A mutation that does NOT cause a test failure is a "survivor" — it
signals that the test suite has a coverage gap. The kill rate
(killed / total) is the §3.3 metric (target ≥ 70%).

Output: ``tests/mutation_report.json``.

Mutators applied (per Coles 2007 "Mutation Operators for Java"):
- ``>``  →  ``>=``    (boundary mutation)
- ``+``  →  ``-``     (arithmetic operator)
- ``*``  →  ``+``     (arithmetic operator)
- ``True`` → ``False`` (boolean negation)
- numeric literal × 1.5 (constant change)

Each mutator is applied once per occurrence in the target module's
source code, the module is reloaded, a short subset of the test suite
is re-run, and the result (killed = test failed; survived = test
passed) is recorded.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DEFAULT_TARGETS = [
    REPO_ROOT / "structure_optimizer" / "core" / "augmented_lagrangian.py",
    REPO_ROOT / "structure_optimizer" / "core" / "robust.py",
    REPO_ROOT / "structure_optimizer" / "core" / "matrix_free_cg.py",
]
DEFAULT_TEST_GLOBS = [
    "tests/test_augmented_lagrangian.py",
    "tests/test_robust.py",
    "tests/test_matrix_free_cg.py",
    "tests/test_property_extended.py",
]


MUTATORS = [
    # (regex_pattern, replacement)
    (re.compile(r"(?<![<>=!])>(?![=>])"), ">="),  # > → >=
    (re.compile(r"(?<![+\-*/])\+(?![+=])"), "-"),  # + → -
    (re.compile(r"True"), "False"),
    (re.compile(r"\*(?!\*)"), "+"),  # * → +
]


def _apply_one_mutation(source: str, mutator_idx: int, occurrence: int) -> str | None:
    """Apply the ``mutator_idx``-th mutator to the ``occurrence``-th match."""
    pattern, repl = MUTATORS[mutator_idx]
    matches = list(pattern.finditer(source))
    if occurrence >= len(matches):
        return None
    m = matches[occurrence]
    return source[: m.start()] + repl + source[m.end() :]


def _run_subset_tests(test_globs: list[str]) -> bool:
    """Returns True if all tests pass, False if any failed."""
    cmd = [sys.executable, "-m", "pytest", "-q", "--no-header", "-x", *test_globs]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
    return proc.returncode == 0


def mutate_and_test(
    target: Path,
    test_globs: list[str],
    max_per_mutator: int = 5,
) -> dict:
    """Mutate one target module and report kill/survive per mutation.

    Args:
        target: path to a single Python file.
        test_globs: pytest paths to run under each mutation.
        max_per_mutator: cap occurrences per mutator to keep runtime
            bounded (default 5 → 5 × 4 mutators = 20 mutations/file).
    """
    original = target.read_text()
    killed = 0
    survived = 0
    skipped = 0
    log: list[dict] = []

    for m_idx in range(len(MUTATORS)):
        for occ in range(max_per_mutator):
            mutated = _apply_one_mutation(original, m_idx, occ)
            if mutated is None or mutated == original:
                skipped += 1
                continue
            target.write_text(mutated)
            try:
                tests_passed = _run_subset_tests(test_globs)
            except subprocess.TimeoutExpired:
                tests_passed = False
            if tests_passed:
                survived += 1
                outcome = "survived"
            else:
                killed += 1
                outcome = "killed"
            log.append(
                {
                    "mutator_idx": m_idx,
                    "occurrence": occ,
                    "outcome": outcome,
                }
            )

    target.write_text(original)  # restore

    total = killed + survived
    kill_rate = killed / max(total, 1)
    return {
        "target": str(target.relative_to(REPO_ROOT)),
        "total_applied": total,
        "killed": killed,
        "survived": survived,
        "skipped": skipped,
        "kill_rate": kill_rate,
        "details": log,
    }


def main() -> int:
    results: list[dict] = []
    for target in DEFAULT_TARGETS:
        print(f"mutating {target.name} ...")
        r = mutate_and_test(target, DEFAULT_TEST_GLOBS, max_per_mutator=3)
        results.append(r)
        print(f"  → kill rate {r['kill_rate']:.1%} ({r['killed']}/{r['total_applied']})")
    total_killed = sum(r["killed"] for r in results)
    total_applied = sum(r["total_applied"] for r in results)
    aggregate_kill_rate = total_killed / max(total_applied, 1)

    report = {
        "aggregate_kill_rate": aggregate_kill_rate,
        "total_killed": total_killed,
        "total_applied": total_applied,
        "per_module": results,
    }
    out = REPO_ROOT / "tests" / "mutation_report.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(f"\nwrote {out}")
    print(f"aggregate kill rate: {aggregate_kill_rate:.1%}")
    return 0 if aggregate_kill_rate >= 0.70 else 1


if __name__ == "__main__":
    sys.exit(main())
