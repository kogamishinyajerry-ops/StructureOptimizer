from structure_optimizer.core.reporting import generate_report
from structure_optimizer.core.verification import FAILURE_STATUSES, PASS_STATUS, verify_run
from structure_optimizer.core.workflow import run_benchmark


def test_run_verify_report_smoke_path_creates_required_artifacts():
    run_dir = run_benchmark("mbb_beam", preset="smoke")

    required = [
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
    ]
    for filename in required:
        path = run_dir / filename
        assert path.exists(), filename
        assert path.stat().st_size > 0, filename

    verification = verify_run(run_dir)
    assert verification["status"] in {PASS_STATUS, *FAILURE_STATUSES}
    assert "constraints" in verification
    assert verification["constraints"]
    assert {"name", "value", "limit", "unit", "source", "status"}.issubset(verification["constraints"][0])

    report_path = generate_report(run_dir)
    report = report_path.read_text()
    assert "## Objective" in report
    assert "## Responses" in report
    assert "## Constraints" in report
    assert "## Baseline Metrics" in report
    assert "## Optimization Iteration Metrics" in report
    assert "## Independent Verification Metrics" in report
    assert "## Manufacturability Warnings" in report
    assert "optimization candidates only" in report
