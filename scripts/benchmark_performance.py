"""Run each built-in benchmark (smoke preset where available, else default)
and emit a performance baseline as Markdown.

This is *not* part of the test suite: the wall-time / memory numbers are
machine-specific and noisy. Re-run on a fresh checkout to refresh
``docs/performance.md`` whenever the codebase changes meaningfully.

Usage:
    python -m scripts.benchmark_performance              # write docs/performance.md
    python -m scripts.benchmark_performance --dry-run    # just print, don't write
    python -m scripts.benchmark_performance --preset smoke  # override preset
"""

from __future__ import annotations

import argparse
import platform
import resource
import sys
import time
from datetime import datetime
from pathlib import Path

from structure_optimizer.benchmarks.registry import available_benchmarks, load_benchmark
from structure_optimizer.core.run_store import RUNS_ROOT
from structure_optimizer.core.workflow import run_config


def _maxrss_mb() -> float:
    """Return process peak RSS in MB. On macOS getrusage returns bytes; on
    Linux it returns kilobytes. Normalize to MB."""
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return rss / (1024.0 * 1024.0)
    return rss / 1024.0


def _benchmarks_with_smoke() -> dict[str, str | None]:
    """Map each benchmark name to its preferred preset for perf benchmarking."""
    mapping: dict[str, str | None] = {}
    for name in available_benchmarks():
        config_raw = (Path(__file__).resolve().parent.parent
                      / "structure_optimizer" / "benchmarks" / "configs" / f"{name}.json")
        text = config_raw.read_text()
        if '"smoke"' in text:
            mapping[name] = "smoke"
        else:
            mapping[name] = None
    return mapping


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print only, do not write docs/performance.md")
    parser.add_argument("--preset", default=None, help="Force a single preset for all benchmarks")
    args = parser.parse_args()

    benchmarks = _benchmarks_with_smoke()
    if args.preset:
        benchmarks = {name: args.preset for name in benchmarks}

    rows: list[dict[str, str | float]] = []
    rss_before = _maxrss_mb()
    for name, preset in benchmarks.items():
        try:
            config = load_benchmark(name, preset=preset)
        except Exception as exc:
            rows.append({"benchmark": name, "preset": preset or "default", "wall_s": float("nan"),
                         "rss_delta_mb": float("nan"), "iterations": 0, "status": f"config_error: {exc}"})
            continue
        start = time.perf_counter()
        rss_pre = _maxrss_mb()
        try:
            run_dir = run_config(config)
            elapsed = time.perf_counter() - start
            rss_post = _maxrss_mb()
            verification = (run_dir / "verification.json").read_text()
            verified = '"status": "passed"' in verification
            rows.append({
                "benchmark": name,
                "preset": preset or "default",
                "mesh": f"{config.mesh.nelx}×{config.mesh.nely}",
                "max_iterations": config.optimization.max_iterations,
                "wall_s": elapsed,
                "rss_delta_mb": max(0.0, rss_post - rss_pre),
                "verification": "passed" if verified else "see verification.json",
            })
        except Exception as exc:
            rows.append({"benchmark": name, "preset": preset or "default", "wall_s": float("nan"),
                         "rss_delta_mb": float("nan"), "verification": f"error: {exc}"})

    total_rss_delta = _maxrss_mb() - rss_before
    timestamp = datetime.now().isoformat(timespec="seconds")

    table_lines = [
        "| Benchmark | Preset | Mesh | Max Iter | Wall (s) | ΔRSS (MB) | Verification |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        table_lines.append(
            "| {benchmark} | {preset} | {mesh} | {max_iterations} | {wall_s:.2f} | {rss_delta_mb:.1f} | {verification} |".format(
                benchmark=row.get("benchmark", "?"),
                preset=row.get("preset", "?"),
                mesh=row.get("mesh", "n/a"),
                max_iterations=row.get("max_iterations", "n/a"),
                wall_s=float(row.get("wall_s", float("nan"))),
                rss_delta_mb=float(row.get("rss_delta_mb", float("nan"))),
                verification=row.get("verification", "n/a"),
            )
        )

    markdown = f"""# StructureOptimizer 性能基线

> 自动生成产物。重新生成：`python -m scripts.benchmark_performance`
> 这些数值与机器、Python 版本、NumPy BLAS 后端紧密相关。**请勿当作绝对指标**——它们的价值在于"同一台机器上的相对趋势"。

- 生成时间：{timestamp}
- 平台：{platform.platform()}
- Python：{platform.python_version()}
- 解释器：{sys.executable}

## Smoke preset 实测

{chr(10).join(table_lines)}

总累计 ΔRSS：{total_rss_delta:.1f} MB（受 numpy 缓存影响，仅供参考）

## 解读

- **Wall (s)** 是 `run_config()` 全流水线时间（含 mesh / SIMP 主循环 / verify / report / 可视化 PNG/GIF 落盘）。
- **ΔRSS (MB)** 是单次基准前后进程峰值常驻内存差；不是绝对内存占用，受历史调用影响。
- **Verification** 列 `passed` 表示独立验证全部约束通过。任何其他值需要查对应 run 目录的 `verification.json`。
- 默认 backend = `dense`（`np.linalg.solve`）。`backend=cg` 在大网格上内存占用更低但 wall time 通常更高，可在配置中切换实测。

## 性能扩展建议（不在 v1.0 范围）

- 大网格（≥ 200×200）建议引入 `scipy.sparse` adapter，避免 dense O(N²) 内存
- 多核：`np.linalg.solve` 已通过 LAPACK 自动用 BLAS 多线程；CG 是单线程纯 NumPy
- GPU/MPS 加速：要等真求解器适配（CalculiX / FEniCS / JAX-FEM）成熟
"""

    if args.dry_run:
        print(markdown)
        return 0

    output = Path(__file__).resolve().parent.parent / "docs" / "performance.md"
    output.write_text(markdown)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
