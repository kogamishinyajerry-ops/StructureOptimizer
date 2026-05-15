import json
from pathlib import Path

from structure_optimizer.cli import main


def test_demo_command_generates_html_and_artifacts(capsys):
    exit_code = main(["demo", "--benchmark", "simple_bracket", "--preset", "smoke"])
    captured = capsys.readouterr()

    assert exit_code == 0
    demo_path = Path(captured.out.strip())
    assert demo_path.name == "demo.html"
    assert demo_path.exists()

    run_dir = demo_path.parent
    for filename in [
        "input.json",
        "metrics.csv",
        "baseline.png",
        "loadcase.png",
        "optimization.gif",
        "density.npy",
        "density.png",
        "convergence.png",
        "verification.json",
        "manufacturability.json",
        "report.md",
        "demo.html",
    ]:
        path = run_dir / filename
        assert path.exists(), filename
        assert path.stat().st_size > 0, filename
    frames = sorted((run_dir / "optimization_frames").glob("*.png"))
    assert len(frames) >= 2
    assert all(frame.stat().st_size > 0 for frame in frames)
    assert (run_dir / "optimization.gif").read_bytes().startswith(b"GIF89a")

    html = demo_path.read_text()
    assert "StructureOptimizer 结构优化演示" in html
    assert "从实心支架到轻量化候选结构" in html
    assert "怎么看这页" in html
    assert "2分钟看懂" in html
    assert "原始结构 vs 优化候选" in html
    assert "验证状态" in html
    assert "优化候选方案" in html
    assert "点击说明" in html
    assert "图例" in html
    assert "深青色：保留材料" in html
    assert "蓝色：固定边界" in html
    assert "红色：外加载荷方向" in html
    assert "柔度怎么读" in html
    assert "最大位移怎么读" in html
    assert "近似应力怎么读" in html
    assert "2D/2.5D benchmark model" not in html
    assert "baseline.png" in html
    assert "loadcase.png" in html
    assert "optimization.gif" in html
    assert "density.png" in html
    assert "convergence.png" in html


def test_manufacturability_result_schema_from_demo_run(capsys):
    exit_code = main(["demo", "--benchmark", "simple_bracket", "--preset", "smoke"])
    demo_path = Path(capsys.readouterr().out.strip())

    assert exit_code == 0
    verification = json.loads((demo_path.parent / "verification.json").read_text())
    manufacturability = json.loads((demo_path.parent / "manufacturability.json").read_text())

    assert verification["manufacturability"]["status"] in {"passed", "warning"}
    assert manufacturability["status"] in {"passed", "warning"}
    assert "isolated_islands" in manufacturability["checks"]
    assert "thin_member_warning" in manufacturability["checks"]
    assert "local_density_warning" in manufacturability["checks"]
