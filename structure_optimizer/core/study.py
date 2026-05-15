from __future__ import annotations

import copy
import csv
import html
import itertools
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.config import BenchmarkConfig, parse_config, validate_config
from structure_optimizer.core.demo import generate_demo_html
from structure_optimizer.core.review_package import (
    format_metric_value,
    limitation_disclaimer_html,
    zh_status,
)
from structure_optimizer.core.run_store import RUNS_ROOT, read_json, write_json
from structure_optimizer.core.workflow import run_config

DEFAULT_RANKING = ["verification_status", "mass", "compliance", "max_displacement"]
DEFAULT_OBJECTIVES: list[dict[str, str]] = [
    {"name": "mass", "direction": "minimize"},
    {"name": "compliance", "direction": "minimize"},
]
VALID_DIRECTIONS = {"minimize", "maximize"}
STANDARD_CANDIDATE_COLUMNS = [
    "rank",
    "pareto_rank",
    "candidate_id",
    "run_dir",
    "benchmark",
    "preset",
    "status",
    "verification_status",
    "volume_fraction",
    "filter_radius",
    "mass",
    "compliance",
    "max_displacement",
    "manufacturability_warning_count",
    "parameters_json",
]


@dataclass(frozen=True)
class StudyConfig:
    """Parameter-study configuration: benchmark + parameter grid + ranking + Pareto objectives."""

    benchmark: str
    preset: str | None
    parameters: dict[str, list[Any]]
    ranking: list[str]
    objectives: list[dict[str, str]]
    source_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict copy; ``preset`` / ``source_path`` omitted when ``None``."""
        data: dict[str, Any] = {
            "benchmark": self.benchmark,
            "parameters": self.parameters,
            "ranking": self.ranking,
            "objectives": self.objectives,
        }
        if self.preset is not None:
            data["preset"] = self.preset
        if self.source_path is not None:
            data["source_path"] = self.source_path
        return data


def load_study_config(path: Path | str) -> StudyConfig:
    """Load + validate a study JSON config; raises ``ValueError`` on missing / malformed fields."""
    path = Path(path)
    raw = json.loads(path.read_text())
    try:
        benchmark = str(raw["benchmark"])
        parameters = raw["parameters"]
    except KeyError as exc:
        raise ValueError(f"Missing required study field: {exc.args[0]}") from exc

    if not isinstance(parameters, dict) or not parameters:
        raise ValueError("study parameters must be a non-empty object")

    normalized: dict[str, list[Any]] = {}
    candidate_count = 1
    for name, values in parameters.items():
        if not isinstance(name, str) or not name:
            raise ValueError("study parameter names must be non-empty strings")
        if not isinstance(values, list) or not values:
            raise ValueError(f"study parameter '{name}' must have non-empty values")
        normalized[name] = values
        candidate_count *= len(values)

    max_candidates = int(raw.get("max_candidates", 64))
    if max_candidates <= 0:
        raise ValueError("max_candidates must be positive")
    if candidate_count > max_candidates:
        raise ValueError(f"study expands to {candidate_count} candidates, above max_candidates={max_candidates}")

    ranking = raw.get("ranking", DEFAULT_RANKING)
    if not isinstance(ranking, list) or not all(isinstance(item, str) and item for item in ranking):
        raise ValueError("ranking must be a list of non-empty strings")

    objectives = _normalize_objectives(raw.get("objectives", DEFAULT_OBJECTIVES))

    preset = raw.get("preset")
    if preset is not None:
        preset = str(preset)

    return StudyConfig(
        benchmark=benchmark,
        preset=preset,
        parameters=normalized,
        ranking=ranking,
        objectives=objectives,
        source_path=str(path),
    )


def _normalize_objectives(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("objectives must be a non-empty list")
    normalized: list[dict[str, str]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("each objective must be an object with 'name' and 'direction'")
        name = entry.get("name")
        direction = entry.get("direction", "minimize")
        if not isinstance(name, str) or not name:
            raise ValueError("objective name must be a non-empty string")
        if direction not in VALID_DIRECTIONS:
            raise ValueError(f"objective direction must be one of {sorted(VALID_DIRECTIONS)}")
        normalized.append({"name": name, "direction": direction})
    return normalized


def run_study(config_path: Path | str) -> Path:
    """Run a parameter-grid study: for every override combination, run + verify + generate demo.

    Then compute Pareto ranks across the chosen objectives, rank the table by
    ``ranking`` criteria, write ``candidates.csv`` + ``study.html``. Returns the
    path to ``study.html``.
    """
    study = load_study_config(config_path)
    base_config = load_benchmark(study.benchmark, preset=study.preset)
    study_dir = _create_study_dir(study)
    write_json(study_dir / "study_input.json", study.to_dict())

    rows: list[dict[str, Any]] = []
    for index, overrides in enumerate(_parameter_matrix(study.parameters), start=1):
        candidate_id = f"candidate_{index:03d}"
        candidate_dir = study_dir / candidate_id
        candidate_config = _config_with_overrides(base_config, overrides)
        run_config(candidate_config, run_dir=candidate_dir)
        generate_demo_html(candidate_dir)
        verification = read_json(candidate_dir / "verification.json")
        rows.append(_candidate_row(study, candidate_id, candidate_dir, overrides, candidate_config, verification))

    _assign_pareto_ranks(rows, study.objectives)
    ranked_rows = _rank_candidates(rows, study.ranking)
    _write_candidates_csv(study_dir / "candidates.csv", ranked_rows)
    _write_study_html(study_dir / "study.html", study, ranked_rows)
    return study_dir / "study.html"


def _create_study_dir(study: StudyConfig) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    study_dir = RUNS_ROOT / "studies" / f"{study.benchmark}_{timestamp}"
    study_dir.mkdir(parents=True, exist_ok=False)
    return study_dir


def _parameter_matrix(parameters: dict[str, list[Any]]) -> list[dict[str, Any]]:
    names = list(parameters)
    return [
        dict(zip(names, values, strict=True)) for values in itertools.product(*(parameters[name] for name in names))
    ]


def _config_with_overrides(base_config: BenchmarkConfig, overrides: dict[str, Any]) -> BenchmarkConfig:
    raw = base_config.to_dict()
    for name, value in overrides.items():
        _apply_parameter_override(raw, name, value)
    config = parse_config(raw, source_path=base_config.source_path)
    validate_config(config)
    return config


def _apply_parameter_override(raw: dict[str, Any], name: str, value: Any) -> None:
    if name == "volume_fraction":
        raw["optimization"]["volume_fraction"] = float(value)
        return
    if name == "filter_radius":
        raw["optimization"]["filter_radius"] = float(value)
        return
    if name.startswith("load_weights."):
        load_case_name = name.split(".", 1)[1]
        for load_case in raw.get("load_cases", []):
            if load_case.get("name") == load_case_name:
                load_case["weight"] = float(value)
                return
        raise ValueError(f"Unknown load case for study parameter '{name}'")
    raise ValueError(f"Unsupported study parameter '{name}'")


def _candidate_row(
    study: StudyConfig,
    candidate_id: str,
    candidate_dir: Path,
    overrides: dict[str, Any],
    config: BenchmarkConfig,
    verification: dict[str, Any],
) -> dict[str, Any]:
    candidate = verification.get("candidate", {})
    manufacturability = verification.get("manufacturability", {})
    checks = manufacturability.get("checks", {})
    warning_count = sum(1 for check in checks.values() if check.get("status") != "passed")
    row: dict[str, Any] = {
        "rank": "",
        "candidate_id": candidate_id,
        "run_dir": str(candidate_dir),
        "benchmark": study.benchmark,
        "preset": study.preset or "",
        "status": "completed",
        "verification_status": verification.get("status", "missing"),
        "volume_fraction": config.optimization.volume_fraction,
        "filter_radius": config.optimization.filter_radius,
        "mass": candidate.get("mass", ""),
        "compliance": candidate.get("compliance", ""),
        "max_displacement": candidate.get("max_displacement", ""),
        "manufacturability_warning_count": warning_count,
        "parameters_json": json.dumps(overrides, sort_keys=True, separators=(",", ":")),
    }
    for name, value in overrides.items():
        row[name] = value
    return row


def _assign_pareto_ranks(rows: list[dict[str, Any]], objectives: list[dict[str, str]]) -> None:
    """Non-dominated sorting. Mutates each row, setting ``pareto_rank``.

    Candidates whose verification_status != 'passed' are excluded from the
    frontier (they receive pareto_rank = '' so they sort last visually).
    For minimize objectives, A dominates B iff A_i ≤ B_i for all i and strict
    for at least one. For maximize, the inequalities flip.

    Algorithm: iterative peeling — find the non-dominated set among remaining
    eligible candidates, assign current rank, remove, repeat.
    """
    eligible: list[int] = [idx for idx, row in enumerate(rows) if row.get("verification_status") == "passed"]
    for row in rows:
        row["pareto_rank"] = ""

    if not eligible:
        return

    vectors: dict[int, list[float]] = {}
    for idx in eligible:
        vectors[idx] = [_objective_value(rows[idx], obj) for obj in objectives]
    if not vectors:
        return

    remaining = set(eligible)
    current_rank = 1
    while remaining:
        front: list[int] = []
        for candidate in remaining:
            dominated = False
            for other in remaining:
                if other == candidate:
                    continue
                if _dominates(vectors[other], vectors[candidate], objectives):
                    dominated = True
                    break
            if not dominated:
                front.append(candidate)
        if not front:
            # numerical tie: assign current rank to everything remaining and stop
            for idx in remaining:
                rows[idx]["pareto_rank"] = current_rank
            return
        for idx in front:
            rows[idx]["pareto_rank"] = current_rank
        remaining.difference_update(front)
        current_rank += 1


def _objective_value(row: dict[str, Any], objective: dict[str, str]) -> float:
    raw = row.get(objective["name"])
    if raw is None:
        return float("inf") if objective["direction"] == "minimize" else float("-inf")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float("inf") if objective["direction"] == "minimize" else float("-inf")


def _dominates(a: list[float], b: list[float], objectives: list[dict[str, str]]) -> bool:
    strictly_better_in_one = False
    for value_a, value_b, obj in zip(a, b, objectives, strict=True):
        if obj["direction"] == "minimize":
            if value_a > value_b:
                return False
            if value_a < value_b:
                strictly_better_in_one = True
        else:
            if value_a < value_b:
                return False
            if value_a > value_b:
                strictly_better_in_one = True
    return strictly_better_in_one


def _rank_candidates(rows: list[dict[str, Any]], ranking: list[str]) -> list[dict[str, Any]]:
    ranked = [copy.deepcopy(row) for row in rows]
    ranked.sort(key=lambda row: _ranking_key(row, ranking))
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank
    return ranked


def _ranking_key(row: dict[str, Any], ranking: list[str]) -> tuple:
    key: list[Any] = []
    for criterion in ranking:
        if criterion == "verification_status":
            key.append(0 if row.get("verification_status") == "passed" else 1)
        elif criterion in {"mass", "compliance", "max_displacement", "volume_fraction", "filter_radius"}:
            key.append(_float_or_inf(row.get(criterion)))
        elif criterion == "manufacturability_warning_count":
            key.append(int(row.get(criterion) or 0))
    key.append(row.get("candidate_id", ""))
    return tuple(key)


def _float_or_inf(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("inf")


def _write_candidates_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    extra_columns = sorted({key for row in rows for key in row if key not in STANDARD_CANDIDATE_COLUMNS})
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=STANDARD_CANDIDATE_COLUMNS + extra_columns)
        writer.writeheader()
        writer.writerows(rows)


def _write_study_html(path: Path, study: StudyConfig, rows: list[dict[str, Any]]) -> None:
    points = _pareto_points(rows)
    rows_html = "\n".join(_candidate_table_row(row) for row in rows)
    points_html = "\n".join(
        f'<a class="point {_point_class(row)}" href="{html.escape(row["candidate_id"])}/report.md" '
        f'style="left:{point["x"]:.1f}%; bottom:{point["y"]:.1f}%;" '
        f'title="{html.escape(row["candidate_id"])} pareto_rank={row.get("pareto_rank", "")} mass={row["mass"]} compliance={row["compliance"]}">'
        f"{html.escape(str(row['rank']))}</a>"
        for row, point in zip(rows, points, strict=True)
    )
    pareto_front_count = sum(1 for row in rows if row.get("pareto_rank") == 1)
    pareto_objective_text = " vs ".join(
        f"{obj['name']} ({'最小化' if obj['direction'] == 'minimize' else '最大化'})" for obj in study.objectives
    )
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>StructureOptimizer Study - 候选方案对比</title>
  <style>
    :root {{
      --ink: #172026;
      --muted: #5d6b73;
      --line: #d7dee2;
      --panel: #f8faf9;
      --accent: #0e7c7b;
      --warn: #b35c00;
      --good: #147a3f;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: #ffffff;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.55;
    }}
    header {{
      padding: 40px 48px 28px;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(135deg, #f9fbfa, #eef5f4);
    }}
    main {{ padding: 28px 48px 56px; }}
    h1 {{ margin: 0 0 8px; font-size: 34px; letter-spacing: 0; }}
    h2 {{ margin: 32px 0 12px; font-size: 22px; letter-spacing: 0; }}
    p {{ max-width: 980px; color: var(--muted); }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(4, minmax(160px, 1fr));
      gap: 12px;
      margin-top: 24px;
      max-width: 1040px;
    }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px 16px;
      background: #fff;
    }}
    .metric strong {{ display: block; font-size: 22px; }}
    .metric span {{ color: var(--muted); font-size: 13px; }}
    .pareto {{
      position: relative;
      height: 360px;
      max-width: 1040px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background:
        linear-gradient(#edf2f4 1px, transparent 1px),
        linear-gradient(90deg, #edf2f4 1px, transparent 1px),
        #fff;
      background-size: 20% 20%;
      margin-bottom: 12px;
    }}
    .axis-x, .axis-y {{
      position: absolute;
      color: var(--muted);
      font-size: 13px;
    }}
    .axis-x {{ right: 14px; bottom: 10px; }}
    .axis-y {{ left: 14px; top: 10px; }}
    .point {{
      position: absolute;
      width: 32px;
      height: 32px;
      transform: translate(-50%, 50%);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
      background: var(--accent);
      color: #fff;
      text-decoration: none;
      font-weight: 700;
      box-shadow: 0 4px 12px rgba(14, 124, 123, 0.25);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
      margin-top: 12px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 8px;
      text-align: left;
      vertical-align: middle;
    }}
    th {{ color: #33444c; background: var(--panel); }}
    .thumb {{ width: 112px; max-height: 76px; object-fit: contain; border: 1px solid var(--line); background: #fff; }}
    .passed {{ color: var(--good); font-weight: 700; }}
    .failed {{ color: var(--warn); font-weight: 700; }}
    .point.pareto-front {{
      background: #b8390e;
      box-shadow: 0 4px 14px rgba(184, 57, 14, 0.35);
      outline: 2px solid #fff;
    }}
    .pareto-chip {{
      display: inline-block;
      padding: 3px 9px;
      border-radius: 999px;
      background: #b8390e;
      color: #fff;
      font-size: 12px;
      font-weight: 700;
    }}
    tr.pareto-front-row td {{ background: #fff5ec; }}
    .pareto-summary {{
      max-width: 1040px;
      padding: 12px 16px;
      border: 1px solid var(--line);
      border-left: 4px solid #b8390e;
      border-radius: 6px;
      background: #fff8f3;
      color: #5b2a14;
      margin: 8px 0 16px;
    }}
    .limits {{
      max-width: 1040px;
      padding: 16px 18px;
      border-left: 4px solid var(--warn);
      background: #fff8ef;
      color: #5b3b14;
    }}
    .note {{
      max-width: 1040px;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfc;
      color: #34454c;
    }}
    a {{ color: #09656a; }}
  </style>
</head>
<body>
  <header>
    <h1>候选方案对比</h1>
    <p>本页把同一个 2D/2.5D benchmark model 的多组 SIMP 参数运行放在一起比较，用于 2 分钟内判断哪个 optimization candidate 更值得进入下一轮工程复核。</p>
    <div class="summary">
      <div class="metric"><strong>{html.escape(study.benchmark)}</strong><span>Benchmark</span></div>
      <div class="metric"><strong>{html.escape(study.preset or "default")}</strong><span>Preset</span></div>
      <div class="metric"><strong>{len(rows)}</strong><span>候选数量</span></div>
      <div class="metric"><strong>{html.escape(str(rows[0]["verification_status"]) if rows else "n/a")}</strong><span>第一名验证状态</span></div>
    </div>
  </header>
  <main>
    <section>
      <h2>Pareto 前沿</h2>
      <p class="pareto-summary"><strong>{pareto_front_count}</strong> 个候选位于 Pareto 前沿（按 {html.escape(pareto_objective_text)} 计算非支配集）。前沿候选在散点图与排名表中用<strong>橙色</strong>高亮，表示当前参数空间内没有其他候选能在所有指标上同时优于它。验证未通过的候选不参与前沿。</p>
      <h2>Pareto 风格对比</h2>
      <p>横向越靠左表示质量越低，纵向越靠上表示柔度越低。柔度可以粗略理解为结构越不容易被载荷“推软”的指标；最大位移用于观察最不利点移动幅度；验证状态来自独立复算。</p>
      <p class="note"><strong>排序规则：</strong>当前按 <code>{html.escape(" -> ".join(study.ranking))}</code> 排名。默认排名偏向减重；如果评审目标是更硬的结构，请优先比较柔度和最大位移列。</p>
      <div class="pareto">
        <span class="axis-y">低柔度 / 更硬</span>
        <span class="axis-x">低质量 / 更轻</span>
        {points_html}
      </div>
    </section>

    <section>
      <h2>候选排名表</h2>
      <table>
        <thead>
          <tr>
            <th>排名</th>
            <th>Pareto 前沿</th>
            <th>候选</th>
            <th>详情页</th>
            <th>密度图</th>
            <th>质量</th>
            <th>体积分数</th>
            <th>滤波半径</th>
            <th>柔度</th>
            <th>最大位移</th>
            <th>验证状态</th>
            <th>制造性警告</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </section>

    <section>
      <h2>原始数据</h2>
      <p><a href="candidates.csv">candidates.csv</a> 保存所有候选指标；每个候选目录内保留 <code>input.json</code>、<code>metrics.csv</code>、<code>verification.json</code>、<code>report.md</code>、<code>demo.html</code> 和图片产物。</p>
    </section>

    {limitation_disclaimer_html("engineering")}
  </main>
</body>
</html>
"""
    path.write_text(html_text)


def _candidate_table_row(row: dict[str, Any]) -> str:
    status = str(row.get("verification_status", "missing"))
    status_css = "passed" if status == "passed" else "failed"
    candidate_id = html.escape(str(row["candidate_id"]))
    pareto_rank = row.get("pareto_rank", "")
    pareto_cell = (
        '<span class="pareto-chip">前沿</span>'
        if pareto_rank == 1
        else (html.escape(str(pareto_rank)) if pareto_rank != "" else "—")
    )
    row_class = "pareto-front-row" if pareto_rank == 1 else ""
    return (
        f'<tr class="{row_class}">'
        f"<td>{html.escape(str(row['rank']))}</td>"
        f"<td>{pareto_cell}</td>"
        f'<td><a href="{candidate_id}/report.md">{candidate_id}</a></td>'
        f'<td><a class="demo-link" href="{candidate_id}/demo.html">查看详情</a></td>'
        f'<td><a href="{candidate_id}/density.png"><img class="thumb" src="{candidate_id}/density.png" alt="{candidate_id} density"></a></td>'
        f"<td>{format_metric_value(row.get('mass'))}</td>"
        f"<td>{format_metric_value(row.get('volume_fraction'))}</td>"
        f"<td>{format_metric_value(row.get('filter_radius'))}</td>"
        f"<td>{format_metric_value(row.get('compliance'))}</td>"
        f"<td>{format_metric_value(row.get('max_displacement'))}</td>"
        f'<td class="{status_css}">{html.escape(zh_status(status))}</td>'
        f"<td>{html.escape(str(row.get('manufacturability_warning_count', '')))}</td>"
        "</tr>"
    )


def _point_class(row: dict[str, Any]) -> str:
    return "pareto-front" if row.get("pareto_rank") == 1 else ""


def _pareto_points(rows: list[dict[str, Any]]) -> list[dict[str, float]]:
    masses = [_float_or_inf(row.get("mass")) for row in rows]
    compliances = [_float_or_inf(row.get("compliance")) for row in rows]
    min_mass, max_mass = min(masses), max(masses)
    min_compliance, max_compliance = min(compliances), max(compliances)
    points = []
    for mass, compliance in zip(masses, compliances, strict=True):
        x = _normalize(mass, min_mass, max_mass)
        y = 1.0 - _normalize(compliance, min_compliance, max_compliance)
        points.append({"x": 8.0 + x * 84.0, "y": 8.0 + y * 84.0})
    return points


def _normalize(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.5
    return min(1.0, max(0.0, (value - low) / (high - low)))
