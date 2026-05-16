from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from structure_optimizer.core.reporting import generate_report
from structure_optimizer.core.review_package import (
    format_metric_value,
    limitation_disclaimer_html,
    percent_reduction,
    status_badge_html,
    zh_check_name,
    zh_status,
    zh_stop_reason,
)
from structure_optimizer.core.run_store import load_metrics, read_json
from structure_optimizer.core.verification import verify_run
from structure_optimizer.core.workflow import run_benchmark


def generate_demo_package(benchmark: str, preset: str | None = None) -> Path:
    """Run a benchmark and emit a static ``demo.html`` review package; return its path."""
    run_dir = run_benchmark(benchmark, preset=preset)
    return generate_demo_html(run_dir)


def generate_demo_html(run_dir: Path | str) -> Path:
    """Generate ``demo.html`` for an existing run directory (does not re-run optimization)."""
    run_dir = Path(run_dir)
    input_config = read_json(run_dir / "input.json")
    summary = read_json(run_dir / "summary.json") if (run_dir / "summary.json").exists() else {}
    verification = (
        read_json(run_dir / "verification.json") if (run_dir / "verification.json").exists() else verify_run(run_dir)
    )
    metrics = load_metrics(run_dir)
    report_path = run_dir / "report.md"
    if not report_path.exists():
        generate_report(run_dir)

    benchmark = input_config["name"]
    dimension = input_config["dimension"]
    mesh = input_config["mesh"]
    input_config["optimization"]
    baseline = verification.get("baseline", {})
    candidate = verification.get("candidate", {})
    objective = verification.get("objective", {})
    responses = verification.get("responses", [])
    constraints = verification.get("constraints", [])
    manufacturability = verification.get("manufacturability", {})
    first_metric = metrics[0] if metrics else {}
    last_metric = metrics[-1] if metrics else {}

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>StructureOptimizer 演示 - {escape(benchmark)}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #182026;
      --muted: #5d6975;
      --line: #d9e1e8;
      --panel: #ffffff;
      --bg: #f4f7fa;
      --accent: #007c89;
      --good: #147d45;
      --warn: #a15c00;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }}
    header {{
      padding: 30px 36px 24px;
      background: #fdfefe;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{ margin: 8px 0 10px; font-size: 38px; line-height: 1.08; letter-spacing: 0; max-width: 940px; }}
    h2 {{ margin: 0 0 14px; font-size: 18px; letter-spacing: 0; }}
    p {{ color: var(--muted); line-height: 1.55; }}
    .eyebrow {{
      margin: 0 0 6px;
      color: var(--accent);
      font-size: 13px;
      font-weight: 750;
      text-transform: uppercase;
      letter-spacing: 0;
    }}
    .hero {{
      display: grid;
      grid-template-columns: minmax(360px, 0.9fr) minmax(440px, 1.1fr);
      gap: 28px;
      align-items: center;
    }}
    .hero p {{ max-width: 760px; font-size: 16px; }}
    .hero-visual {{
      background: #f5f9fb;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .hero-visual img {{
      display: block;
      width: 100%;
      border-radius: 6px;
    }}
    .hero-comparison {{
      display: grid;
      grid-template-columns: 1fr 42px 1fr;
      gap: 12px;
      align-items: center;
    }}
    .hero-card {{
      background: #ffffff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
    }}
    .hero-card p {{
      margin: 0 0 8px;
      font-size: 13px;
      font-weight: 700;
      color: var(--ink);
    }}
    .hero-arrow {{
      text-align: center;
      font-size: 30px;
      font-weight: 800;
      color: var(--accent);
    }}
    .demo-story {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
      margin-top: 16px;
    }}
    .story-step {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #ffffff;
    }}
    .story-step strong {{ display: block; margin-bottom: 4px; }}
    .story-step span {{ color: var(--muted); font-size: 13px; }}
    main {{ padding: 24px 36px 36px; }}
    .grid {{
      display: grid;
      grid-template-columns: minmax(360px, 1.25fr) minmax(320px, 0.75fr);
      gap: 18px;
      align-items: start;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(150px, 1fr));
      gap: 12px;
      margin: 18px 0 0;
    }}
    .metric {{
      position: relative;
      background: #f8fbfd;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      min-height: 130px;
    }}
    .metric .label {{ color: var(--muted); font-size: 13px; }}
    .metric .value {{ font-size: 24px; font-weight: 700; margin-top: 10px; }}
    .metric .sub {{ color: var(--muted); font-size: 12px; margin-top: 6px; }}
    .explain {{
      margin-top: 10px;
      position: relative;
    }}
    .explain summary {{
      display: inline-flex;
      cursor: pointer;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 9px;
      color: var(--accent);
      background: #fff;
      font-size: 12px;
      font-weight: 700;
      list-style: none;
    }}
    .explain summary::-webkit-details-marker {{ display: none; }}
    .popover {{
      margin-top: 8px;
      border: 1px solid #b9dce3;
      border-radius: 8px;
      padding: 10px;
      background: #f7fcfd;
      color: var(--ink);
      font-size: 13px;
      line-height: 1.55;
      box-shadow: 0 8px 24px rgba(24, 32, 38, 0.08);
    }}
    .status {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 5px 10px;
      font-size: 13px;
      font-weight: 650;
      border: 1px solid var(--line);
      background: #f8fbfd;
    }}
    .status.pass {{ color: var(--good); border-color: #a8d5bc; background: #eef9f2; }}
    .status.warn {{ color: var(--warn); border-color: #e8c27d; background: #fff8e8; }}
    .visuals {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
      margin-top: 14px;
    }}
    .visuals.three {{
      grid-template-columns: repeat(3, 1fr);
    }}
    .image-label {{
      color: var(--muted);
      font-size: 13px;
      margin: 0 0 8px;
    }}
    img {{
      width: 100%;
      height: auto;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 8px;
      text-align: left;
    }}
    th {{ color: var(--muted); font-weight: 650; }}
    .bar {{
      height: 10px;
      background: #dce7ee;
      border-radius: 999px;
      overflow: hidden;
      margin-top: 8px;
    }}
    .bar span {{ display: block; height: 100%; background: var(--accent); }}
    .artifact-list a {{
      display: inline-block;
      margin: 0 10px 10px 0;
      color: var(--accent);
      text-decoration: none;
      font-weight: 650;
    }}
    .note {{
      margin-top: 18px;
      padding: 12px 14px;
      border-left: 4px solid var(--accent);
      background: #f7fbfc;
      color: var(--muted);
      line-height: 1.55;
    }}
    .legend {{
      display: grid;
      grid-template-columns: repeat(4, minmax(120px, 1fr));
      gap: 10px;
      margin-top: 14px;
    }}
    .legend-item {{
      display: flex;
      gap: 8px;
      align-items: center;
      color: var(--muted);
      font-size: 13px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
      background: #fff;
    }}
    .swatch {{
      width: 18px;
      height: 18px;
      border-radius: 4px;
      border: 1px solid var(--line);
      flex: 0 0 18px;
    }}
    .swatch.material {{ background: #0c3e4e; }}
    .swatch.void {{ background: #f5f9fb; }}
    .swatch.fixed {{ background: #005caa; }}
    .swatch.load {{ background: #d22c2c; }}
    .metric-explainers {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
      margin-top: 14px;
    }}
    @media (max-width: 900px) {{
      main, header {{ padding-left: 18px; padding-right: 18px; }}
      .grid, .visuals, .visuals.three, .metrics, .hero, .demo-story, .legend, .metric-explainers {{ grid-template-columns: 1fr; }}
    }}
  </style>
  <style>
    /* Wave Q (rubric §5.4): interactive review enhancements */
    .interactive-toolbar {{
      margin: 12px 0;
      display: flex;
      gap: 14px;
      flex-wrap: wrap;
      align-items: center;
      font-size: 13px;
      color: var(--muted);
    }}
    .interactive-toolbar label {{
      display: inline-flex;
      gap: 6px;
      align-items: center;
      cursor: pointer;
      user-select: none;
    }}
    .panzoom-stage {{
      position: relative;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 4px;
      background: #fff;
      cursor: grab;
      touch-action: none;
    }}
    .panzoom-stage img {{
      display: block;
      transform-origin: 0 0;
      transition: transform 80ms;
      max-width: none;
    }}
    .panzoom-stage:active {{
      cursor: grabbing;
    }}
    .panzoom-controls {{
      position: absolute;
      top: 8px;
      right: 8px;
      background: rgba(255,255,255,0.94);
      border: 1px solid var(--line);
      border-radius: 4px;
      display: flex;
      gap: 4px;
      padding: 2px;
      font-size: 12px;
    }}
    .panzoom-controls button {{
      border: none;
      background: transparent;
      cursor: pointer;
      padding: 4px 8px;
      font-weight: 600;
      color: var(--ink);
    }}
    .panzoom-controls button:hover {{ background: var(--bg); }}
    .toggleable-image.is-hidden {{ display: none; }}
  </style>
</head>
<body>
  <header>
    <section class="hero">
      <div>
        {status_badge_html(verification.get("status"), "验证状态：" + zh_status(verification.get("status")))}
        <p class="eyebrow">StructureOptimizer 结构优化演示</p>
        <h1>从实心支架到轻量化候选结构</h1>
        <p>这是一页给非算法背景也能看懂的本地演示：先给定原始支架、固定边和载荷，再让 SIMP 拓扑优化自动移除低效材料，最后做一次独立验证检查。这里的结果是“优化候选方案”，不是可直接投产的认证设计。</p>
        <div class="demo-story">
          <div class="story-step"><strong>1. 原始结构</strong><span>深色区域代表可保留材料。</span></div>
          <div class="story-step"><strong>2. 受力边界</strong><span>蓝色是固定边，红色箭头是外加载荷。</span></div>
          <div class="story-step"><strong>3. 优化验证</strong><span>动画展示材料被逐步移除后的候选载荷路径。</span></div>
        </div>
      </div>
      <div class="hero-visual">
        <div class="hero-comparison">
          <div class="hero-card">
            <p>原始实心结构</p>
            <img src="baseline.png" alt="baseline design domain">
          </div>
          <div class="hero-arrow">→</div>
          <div class="hero-card">
            <p>轻量化候选结构</p>
            <img src="density.png" alt="optimized candidate density">
          </div>
        </div>
      </div>
    </section>
  </header>
  <main>
    <section class="metrics">
      {_metric_card("减重", percent_reduction(baseline.get("mass"), candidate.get("mass")), "相对原始实心结构", "表示材料用量减少多少。减重高不一定更安全，必须结合柔度、位移和应力一起看。")}
      {_metric_card("材料保留比例", format_metric_value(verification.get("actual_volume_fraction")), f"目标 {format_metric_value(verification.get('target_volume_fraction'))}", "0.5 表示大约保留一半材料。它是优化约束，不代表结构已经通过工程认证。")}
      {_metric_card("柔度", format_metric_value(candidate.get("compliance")), f"原始 {format_metric_value(baseline.get('compliance'))}，数值越低越硬", "柔度可以理解为“不够硬”的程度。越低通常越好；这里减重后柔度升高，说明结构更轻但更软。")}
      {_metric_card("最大位移", format_metric_value(candidate.get("max_displacement")), f"原始 {format_metric_value(baseline.get('max_displacement'))}", "最大位移表示受力后变形最大的点移动了多少。越低通常越稳；如果变大，需要后续工程复核。")}
    </section>

    <section class="panel" style="margin-top: 18px;">
      <h2>怎么看这页</h2>
      <p>看三个信息就够了：左边是原始结构，中间是固定和载荷，右边是优化后候选结构。减重越高越轻；柔度和位移越低代表越硬。这个 demo 的候选结构减重明显，但柔度和位移上升，所以它适合做概念候选，后续还需要更高保真工程复核。</p>
    </section>

    <section class="grid" style="margin-top: 18px;">
      <div class="panel">
        <h2>2分钟看懂</h2>
        <div class="interactive-toolbar" data-panel="visuals-three">
          <span>显示：</span>
          <label><input type="checkbox" data-toggle="baseline" checked> 原始</label>
          <label><input type="checkbox" data-toggle="loadcase" checked> 边界</label>
          <label><input type="checkbox" data-toggle="density" checked> 候选</label>
        </div>
        <div class="visuals three">
          <div class="toggleable-image" data-key="baseline">
            <p class="image-label">原始实心设计域</p>
            <img src="baseline.png" alt="baseline design domain">
          </div>
          <div class="toggleable-image" data-key="loadcase">
            <p class="image-label">受力与固定边界</p>
            <img src="loadcase.png" alt="load and constraint map">
          </div>
          <div class="toggleable-image" data-key="density">
            <p class="image-label">优化后的候选结构（可缩放）</p>
            <div class="panzoom-stage" data-panzoom>
              <img src="density.png" alt="final density field">
              <div class="panzoom-controls">
                <button type="button" data-zoom="out">−</button>
                <button type="button" data-zoom="reset">100%</button>
                <button type="button" data-zoom="in">+</button>
              </div>
            </div>
          </div>
        </div>
        <div class="visuals">
          <div>
            <p class="image-label">优化过程动画</p>
            <img src="optimization.gif" alt="optimization density animation">
          </div>
          <div>
            <p class="image-label">柔度收敛曲线</p>
            <img src="convergence.png" alt="compliance convergence">
          </div>
        </div>
        <div class="note">图中深色代表保留材料，浅色代表被移除或低密度材料。蓝色表示固定约束，红色箭头表示外加载荷。</div>
        {_legend()}
      </div>

      <div class="panel">
        <h2>算例设置</h2>
        <table>
          <tr><th>项目</th><th>值</th></tr>
          <tr><td>算例</td><td>{escape(benchmark)}</td></tr>
          <tr><td>模型维度</td><td>{escape(dimension)}</td></tr>
          <tr><td>网格</td><td>{mesh.get("nelx")} x {mesh.get("nely")}</td></tr>
          <tr><td>目标</td><td>最小柔度</td></tr>
          <tr><td>迭代次数</td><td>{summary.get("iterations", len(metrics))}</td></tr>
          <tr><td>停止原因</td><td>{zh_stop_reason(summary.get("stop_reason", "unknown"))}</td></tr>
        </table>
      </div>
    </section>

    <section class="grid" style="margin-top: 18px;">
      <div class="panel">
        <h2>原始结构 vs 优化候选</h2>
        {_comparison_table(baseline, candidate)}
        {_metric_explainers()}
      </div>
      <div class="panel">
        <h2>制造性粗检</h2>
        {_manufacturability_table(manufacturability)}
      </div>
    </section>

    <section class="grid" style="margin-top: 18px;">
      <div class="panel">
        <h2>优化目标与响应</h2>
        {_objective_response_table(objective, responses)}
      </div>
      <div class="panel">
        <h2>约束验证</h2>
        {_constraint_table(constraints)}
      </div>
    </section>

    {limitation_disclaimer_html("evaluator")}

    <section class="panel" style="margin-top: 18px;">
      <h2>输出文件</h2>
      <div class="artifact-list">
        <a href="input.json">input.json</a>
        <a href="metrics.csv">metrics.csv</a>
        <a href="baseline.png">baseline.png</a>
        <a href="loadcase.png">loadcase.png</a>
        <a href="optimization.gif">optimization.gif</a>
        <a href="density.npy">density.npy</a>
        <a href="verification.json">verification.json</a>
        <a href="manufacturability.json">manufacturability.json</a>
        <a href="report.md">report.md</a>
      </div>
      <p>第一次迭代柔度：{format_metric_value(first_metric.get("compliance"))}。最终记录迭代柔度：{format_metric_value(last_metric.get("compliance"))}。</p>
      <div class="bar"><span style="width: {_bar_width(verification.get("actual_volume_fraction"))}%"></span></div>
      <p>上方进度条表示独立验证得到的材料保留比例。</p>
    </section>
  </main>
  <script>
    // Wave Q (rubric §5.4): toggle visibility of overlay images + pan/zoom
    document.querySelectorAll('.interactive-toolbar input[data-toggle]').forEach(function(box) {{
      box.addEventListener('change', function() {{
        var panel = box.closest('.interactive-toolbar').dataset.panel;
        var key = box.dataset.toggle;
        var section = box.closest('.panel');
        if (!section) return;
        var card = section.querySelector('.toggleable-image[data-key="' + key + '"]');
        if (card) card.classList.toggle('is-hidden', !box.checked);
      }});
    }});

    document.querySelectorAll('[data-panzoom]').forEach(function(stage) {{
      var img = stage.querySelector('img');
      if (!img) return;
      var state = {{ scale: 1, x: 0, y: 0 }};
      var dragging = false;
      var startX = 0, startY = 0;
      function apply() {{
        img.style.transform = 'translate(' + state.x + 'px,' + state.y + 'px) scale(' + state.scale + ')';
      }}
      function setScale(s) {{
        state.scale = Math.max(0.5, Math.min(8, s));
        apply();
      }}
      stage.addEventListener('wheel', function(ev) {{
        ev.preventDefault();
        var dir = ev.deltaY < 0 ? 1.1 : 0.9;
        setScale(state.scale * dir);
      }}, {{ passive: false }});
      stage.addEventListener('pointerdown', function(ev) {{
        dragging = true; startX = ev.clientX - state.x; startY = ev.clientY - state.y;
        stage.setPointerCapture(ev.pointerId);
      }});
      stage.addEventListener('pointermove', function(ev) {{
        if (!dragging) return;
        state.x = ev.clientX - startX; state.y = ev.clientY - startY;
        apply();
      }});
      stage.addEventListener('pointerup', function() {{ dragging = false; }});
      stage.querySelectorAll('button[data-zoom]').forEach(function(btn) {{
        btn.addEventListener('click', function() {{
          var op = btn.dataset.zoom;
          if (op === 'in') setScale(state.scale * 1.25);
          else if (op === 'out') setScale(state.scale * 0.8);
          else {{ state.scale = 1; state.x = 0; state.y = 0; apply(); }}
        }});
      }});
    }});
  </script>
</body>
</html>
"""
    demo_path = run_dir / "demo.html"
    demo_path.write_text(html)
    return demo_path


def _metric_card(label: str, value: str, sub: str, explanation: str) -> str:
    return (
        f'<div class="metric"><div class="label">{escape(label)}</div><div class="value">{escape(value)}</div>'
        f'<div class="sub">{escape(sub)}</div>{_explain("点击说明", explanation)}</div>'
    )


def _explain(summary: str, body: str) -> str:
    return f'<details class="explain"><summary>{escape(summary)}</summary><div class="popover">{escape(body)}</div></details>'


def _legend() -> str:
    return """
        <div class="legend" aria-label="图例">
          <div class="legend-item"><span class="swatch material"></span><span>深青色：保留材料 / 主要承力路径</span></div>
          <div class="legend-item"><span class="swatch void"></span><span>浅色：移除材料 / 低密度区域</span></div>
          <div class="legend-item"><span class="swatch fixed"></span><span>蓝色：固定边界，不能移动</span></div>
          <div class="legend-item"><span class="swatch load"></span><span>红色：外加载荷方向</span></div>
        </div>
    """


def _metric_explainers() -> str:
    return (
        '<div class="metric-explainers">'
        + _explain(
            "柔度怎么读", "柔度越低，结构越不容易变形，通常越硬。减重后柔度上升是常见权衡，说明需要看使用场景能否接受。"
        )
        + _explain(
            "最大位移怎么读",
            "最大位移越低，结构受力后的最大变形越小。位移变大并不必然失败，但需要和设计允许变形量比较。",
        )
        + _explain(
            "近似应力怎么读",
            "应力越高，局部材料越吃力。当前是简化 2D/2.5D 近似值，只能做风险提示，不能替代高保真 FEA。",
        )
        + "</div>"
    )


def _comparison_table(baseline: dict[str, Any], candidate: dict[str, Any]) -> str:
    labels = {
        "mass": "质量",
        "compliance": "柔度",
        "max_displacement": "最大位移",
        "max_stress": "近似最大应力",
    }
    rows = ["<table><tr><th>指标</th><th>原始结构</th><th>优化候选</th></tr>"]
    for key in ("mass", "compliance", "max_displacement", "max_stress"):
        rows.append(
            f"<tr><td>{labels[key]}</td><td>{format_metric_value(baseline.get(key))}</td><td>{format_metric_value(candidate.get(key))}</td></tr>"
        )
    rows.append("</table>")
    return "".join(rows)


def _objective_response_table(objective: dict[str, Any], responses: list[dict[str, Any]]) -> str:
    rows = ["<table><tr><th>类型</th><th>名称</th><th>数值</th><th>来源</th></tr>"]
    if objective:
        rows.append(
            f"<tr><td>目标</td><td>{escape(str(objective.get('name', 'n/a')))}</td><td>{format_metric_value(objective.get('value'))}</td><td>{escape(str(objective.get('source', 'n/a')))}</td></tr>"
        )
    for response in responses:
        rows.append(
            f"<tr><td>响应</td><td>{escape(str(response.get('name', 'n/a')))}</td><td>{format_metric_value(response.get('value'))}</td><td>{escape(str(response.get('source', 'n/a')))}</td></tr>"
        )
    rows.append("</table>")
    return "".join(rows)


def _constraint_table(constraints: list[dict[str, Any]]) -> str:
    if not constraints:
        return "<p>没有生成约束验证结果。</p>"
    rows = ["<table><tr><th>约束</th><th>数值</th><th>限值</th><th>状态</th></tr>"]
    for constraint in constraints:
        rows.append(
            f"<tr><td>{escape(str(constraint.get('name', 'n/a')))}</td><td>{format_metric_value(constraint.get('value'))}</td><td>{format_metric_value(constraint.get('limit'))}</td><td>{zh_status(constraint.get('status'))}</td></tr>"
        )
    rows.append("</table>")
    return "".join(rows)


def _manufacturability_table(manufacturability: dict[str, Any]) -> str:
    checks = manufacturability.get("checks", {})
    if not checks:
        return "<p>没有生成制造性检查结果。</p>"
    rows = [
        f"<p>{status_badge_html(manufacturability.get('status'), '总体：' + zh_status(manufacturability.get('status')))}</p>"
    ]
    rows.append("<table><tr><th>检查项</th><th>状态</th><th>关键结果</th></tr>")
    for name, check in checks.items():
        detail = ", ".join(f"{key}={value}" for key, value in check.items() if key not in {"status", "rule"})
        rows.append(
            f"<tr><td>{zh_check_name(name)}</td><td>{zh_status(check.get('status', 'unknown'))}</td><td>{escape(detail)}</td></tr>"
        )
    rows.append("</table>")
    return "".join(rows)


def _bar_width(value: Any) -> int:
    try:
        return max(0, min(100, int(float(value) * 100)))
    except (TypeError, ValueError):
        return 0
