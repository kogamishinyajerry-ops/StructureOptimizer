"""Regression coverage for the bridge / turbine_blade / wing_spar benchmarks.

These three mechanical (min-compliance) benchmarks were added to
``structure_optimizer/benchmarks/configs/`` and are auto-discovered by the
registry (``registry.available_benchmarks`` globs ``configs/*.json``). The
per-benchmark smoke suite (``test_per_benchmark_smoke.py``) already exercises
``run_simp`` validity for every registered benchmark; this module adds the two
guarantees that suite does not:

1. **input_hash drift pins** — a recorded ``input_hash`` per benchmark so an
   accidental edit to the config JSON (mesh, material, loads, volume fraction)
   is caught. ``input_hash`` is a pure-config SHA-256 (no BLAS, no solve), so
   the pinned value is byte-identical on every platform — unlike the
   density/scalar fingerprints in ``test_fingerprints.py`` which require a
   bit-exact numerical environment (``REQUIRE_BIT_EXACT_FINGERPRINT=1``, Linux
   only). That portability is why these benchmarks are pinned here on
   ``input_hash`` rather than added to ``scripts/generate_fingerprints.py``:
   both new structural benchmarks use the ``cg`` solver backend, whose
   last-bit results are not reproducible across the CI OS matrix.

2. **runs + independently verifies** — each benchmark runs end-to-end through
   the deterministic pipeline at its smoke preset and passes the independent
   re-solve verification (``verify_run`` → status ``passed``). Both the ``cg``
   backend and the PNG/trace writers are NumPy-/stdlib-only, so this holds in
   the NumPy-only (``vanilla``) CI matrix cells too.

To regenerate a pin after an *intentional* config change::

    python3 -c "from structure_optimizer.benchmarks.registry import load_benchmark; \
from structure_optimizer.core.run_store import input_hash; \
print(input_hash(load_benchmark('bridge')))"
"""

from __future__ import annotations

from pathlib import Path

import pytest
from structure_optimizer.benchmarks.registry import available_benchmarks, load_benchmark
from structure_optimizer.core.run_store import input_hash
from structure_optimizer.core.verification import verify_run
from structure_optimizer.core.workflow import run_config

# Pinned ``input_hash`` of each benchmark's canonical (no-preset) config. A
# mismatch means the config JSON changed: if intentional, regenerate (see module
# docstring); if not, it is a drift regression.
PINNED_INPUT_HASH = {
    "bridge": "sha256:da151cd3231def0542a4b4b1827e773123369055f0a9fc19c40b60c59a262206",
    "turbine_blade": "sha256:ebed01e5c93f049d6d26beb6ab1617605b020d915e27206e3e38bd3bbc506b22",
    "wing_spar": "sha256:01ae52a6487821631f8e95b7868f84bc14bb477d3d0b2d22ce0b4de962849773",
}

NEW_BENCHMARKS = sorted(PINNED_INPUT_HASH)


def test_new_benchmarks_are_registered() -> None:
    available = set(available_benchmarks())
    missing = [n for n in NEW_BENCHMARKS if n not in available]
    assert not missing, f"benchmarks not auto-discovered by the registry: {missing}"


@pytest.mark.parametrize("benchmark", NEW_BENCHMARKS)
def test_new_benchmark_input_hash_pinned(benchmark: str) -> None:
    config = load_benchmark(benchmark)
    assert input_hash(config) == PINNED_INPUT_HASH[benchmark], (
        f"{benchmark}: input_hash drift — the config JSON changed. "
        f"If this was intentional, update PINNED_INPUT_HASH (see module docstring)."
    )


@pytest.mark.parametrize("benchmark", NEW_BENCHMARKS)
def test_new_benchmark_runs_and_verifies(benchmark: str, tmp_path: Path) -> None:
    config = load_benchmark(benchmark, preset="smoke")
    run_dir = run_config(config, run_dir=tmp_path / benchmark)
    verdict = verify_run(run_dir)
    assert verdict["status"] == "passed", (
        f"{benchmark}: independent verification did not pass (status={verdict.get('status')!r})"
    )
