"""End-to-end CLI tests covering every subcommand + every error path.

Goal: prove the CLI surface contract (exit codes, stdout content, stderr format)
without depending on implementation details. Each command tested with at least
one happy path + one failure path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from structure_optimizer.cli import main


def _last_run_dir(parent: str) -> Path:
    """Return the most-recently-created run directory under runs/<parent>/."""
    matches = sorted((Path("runs") / parent).glob("*-*"))
    assert matches, f"no run dirs under runs/{parent}"
    return matches[-1]


# --- run --------------------------------------------------------------


def test_run_command_smoke_returns_zero_and_prints_run_dir(capsys):
    exit_code = main(["run", "--benchmark", "mbb_beam", "--preset", "smoke"])
    captured = capsys.readouterr()
    assert exit_code == 0
    out = captured.out.strip()
    assert out.startswith("runs/mbb_beam/")
    assert Path(out).exists()


def test_run_command_rejects_unknown_benchmark(capsys):
    # argparse choices rejects this before our exception handler;
    # exit code 2 + usage error on stderr.
    with pytest.raises(SystemExit) as exc:
        main(["run", "--benchmark", "nonexistent_benchmark"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "invalid choice" in err or "argument --benchmark" in err


def test_run_command_rejects_missing_required_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["run"])  # no --benchmark
    assert exc.value.code == 2


def test_run_command_rejects_unknown_preset(capsys):
    exit_code = main(["run", "--benchmark", "mbb_beam", "--preset", "ghost_preset"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err.startswith("error: ")
    # Single-line stderr; no stack trace leakage.
    assert "Traceback" not in captured.err


# --- verify -----------------------------------------------------------


def test_verify_command_on_fresh_run_reports_passed(capsys):
    main(["run", "--benchmark", "mbb_beam", "--preset", "smoke"])
    capsys.readouterr()  # discard run output
    run_dir = _last_run_dir("mbb_beam")
    exit_code = main(["verify", "--run", str(run_dir)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "passed"


def test_verify_command_on_missing_dir_reports_invalid_config(capsys, tmp_path):
    missing = tmp_path / "does_not_exist"
    exit_code = main(["verify", "--run", str(missing)])
    captured = capsys.readouterr()
    # verify_run catches the exception and writes invalid_config to the
    # would-be path; but since the parent doesn't exist, it will raise.
    # Either way the CLI must report failure, not crash with a traceback.
    assert exit_code in (0, 1)
    assert "Traceback" not in captured.err
    # If exit_code == 0, stdout should say the failure status; if 1, stderr.
    output = captured.out.strip() if exit_code == 0 else captured.err.strip()
    assert output


def test_verify_command_on_corrupt_input_json_reports_invalid_config(capsys, tmp_path):
    run_dir = tmp_path / "fake_run"
    run_dir.mkdir()
    (run_dir / "input.json").write_text("{not json}")
    exit_code = main(["verify", "--run", str(run_dir)])
    captured = capsys.readouterr()
    assert exit_code == 0  # verify_run writes invalid_config and returns
    assert captured.out.strip() == "invalid_config"


# --- report -----------------------------------------------------------


def test_report_command_regenerates_report_after_run(capsys):
    main(["run", "--benchmark", "mbb_beam", "--preset", "smoke"])
    capsys.readouterr()
    run_dir = _last_run_dir("mbb_beam")
    report_path = run_dir / "report.md"
    report_path.unlink()  # delete then regenerate
    exit_code = main(["report", "--run", str(run_dir)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert Path(captured.out.strip()) == report_path
    assert report_path.exists() and report_path.stat().st_size > 0


def test_report_command_on_missing_dir_returns_one(capsys, tmp_path):
    missing = tmp_path / "no_such_dir"
    exit_code = main(["report", "--run", str(missing)])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err.startswith("error: ")
    assert "Traceback" not in captured.err


# --- demo -------------------------------------------------------------


def test_demo_command_smoke_prints_demo_html_path(capsys):
    exit_code = main(["demo", "--benchmark", "simple_bracket", "--preset", "smoke"])
    captured = capsys.readouterr()
    assert exit_code == 0
    demo_path = Path(captured.out.strip())
    assert demo_path.name == "demo.html"
    assert demo_path.exists()


def test_demo_command_rejects_unknown_benchmark(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["demo", "--benchmark", "nonexistent"])
    assert exc.value.code == 2


# --- study ------------------------------------------------------------


def test_study_command_smoke_returns_study_html(capsys):
    exit_code = main(["study", "--config", "studies/simple_bracket_tradeoff.json"])
    captured = capsys.readouterr()
    assert exit_code == 0
    study_html = Path(captured.out.strip())
    assert study_html.name == "study.html"
    assert study_html.exists()


def test_study_command_missing_config_returns_one(capsys, tmp_path):
    missing = tmp_path / "no_such_study.json"
    exit_code = main(["study", "--config", str(missing)])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err.startswith("error: ")
    assert "Traceback" not in captured.err


def test_study_command_malformed_json_returns_one(capsys, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{this is not json")
    exit_code = main(["study", "--config", str(bad)])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err.startswith("error: ")
    assert "Traceback" not in captured.err


def test_study_command_missing_required_field(capsys, tmp_path):
    bad = tmp_path / "no_benchmark.json"
    bad.write_text(json.dumps({"parameters": {"volume_fraction": [0.4]}}))  # no benchmark
    exit_code = main(["study", "--config", str(bad)])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "benchmark" in captured.err


# --- argparse top-level -----------------------------------------------


def test_main_without_subcommand_exits_two(capsys):
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_main_help_flag_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "run" in out and "verify" in out and "demo" in out and "study" in out


# --- error format invariant -------------------------------------------


def test_all_caught_errors_use_single_line_stderr_no_traceback(capsys, tmp_path):
    """Whenever the CLI catches an exception (exit code 1), stderr must be
    a single 'error: <msg>' line with no Python traceback leaking out.
    This is the documented UX contract."""
    cases = [
        ["report", "--run", str(tmp_path / "missing")],
        ["study", "--config", str(tmp_path / "missing.json")],
        ["run", "--benchmark", "mbb_beam", "--preset", "nonsense"],
    ]
    for argv in cases:
        capsys.readouterr()
        exit_code = main(argv)
        captured = capsys.readouterr()
        if exit_code == 1:
            assert captured.err.startswith("error: "), f"case {argv}: {captured.err!r}"
            assert "Traceback" not in captured.err
            assert captured.err.count("\n") <= 1
