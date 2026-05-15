import csv
import json
from pathlib import Path

from structure_optimizer.cli import main


def test_study_command_generates_ranked_candidates_and_html(capsys):
    exit_code = main(["study", "--config", "studies/simple_bracket_tradeoff.json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    study_html = Path(captured.out.strip())
    assert study_html.name == "study.html"
    assert study_html.exists()

    study_dir = study_html.parent
    for filename in ["study_input.json", "candidates.csv", "study.html"]:
        path = study_dir / filename
        assert path.exists(), filename
        assert path.stat().st_size > 0, filename

    study_input = json.loads((study_dir / "study_input.json").read_text())
    assert study_input["benchmark"] == "simple_bracket"
    assert study_input["preset"] == "smoke"

    rows = list(csv.DictReader((study_dir / "candidates.csv").open()))
    assert len(rows) >= 2
    expected_columns = {
        "rank",
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
    }
    assert expected_columns.issubset(rows[0])
    assert rows[0]["rank"] == "1"

    candidate_dirs = [study_dir / row["candidate_id"] for row in rows]
    for candidate_dir in candidate_dirs:
        assert candidate_dir.exists()
        for filename in ["input.json", "metrics.csv", "density.png", "verification.json", "report.md"]:
            path = candidate_dir / filename
            assert path.exists(), f"{candidate_dir.name}/{filename}"
            assert path.stat().st_size > 0, f"{candidate_dir.name}/{filename}"

    html = study_html.read_text()
    assert "候选方案对比" in html
    assert "Pareto 风格对比" in html
    assert "排序规则" in html
    assert "默认排名偏向减重" in html
    assert "质量" in html
    assert "体积分数" in html
    assert "柔度" in html
    assert "最大位移" in html
    assert "验证状态" in html
    assert "candidate_001/report.md" in html
    assert "optimization candidate" in html
    assert "2D/2.5D benchmark model" in html


def test_study_rejects_empty_parameter_values(tmp_path, capsys):
    config_path = tmp_path / "bad_study.json"
    config_path.write_text(
        json.dumps(
            {
                "benchmark": "simple_bracket",
                "preset": "smoke",
                "parameters": {"volume_fraction": []},
            }
        )
    )

    exit_code = main(["study", "--config", str(config_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "volume_fraction" in captured.err
    assert "non-empty" in captured.err
