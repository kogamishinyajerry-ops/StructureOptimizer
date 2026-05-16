"""Wave V tests for CLI color / diagnostic hooks."""

from __future__ import annotations

from structure_optimizer import cli


def test_color_disabled_when_no_color_env_set(monkeypatch):
    """NO_COLOR env var should disable color output."""
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    assert cli._color_supported() is False


def test_color_enabled_when_force_color_env_set(monkeypatch):
    """FORCE_COLOR overrides any TTY check."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert cli._color_supported() is True


def test_color_disabled_on_non_tty(monkeypatch):
    """Non-TTY stdout → no color."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    # pytest captures stdout so isatty() is naturally False here
    assert cli._color_supported() is False


def test_cli_red_passes_through_when_disabled(monkeypatch):
    """When color is disabled, text is returned as-is."""
    monkeypatch.setattr(cli, "_COLOR_ENABLED", False)
    assert cli.cli_red("danger") == "danger"
    assert cli.cli_green("ok") == "ok"
    assert cli.cli_yellow("warn") == "warn"


def test_cli_red_emits_ansi_when_enabled(monkeypatch):
    """When color is enabled, ANSI escape wraps the text."""
    monkeypatch.setattr(cli, "_COLOR_ENABLED", True)
    out = cli.cli_red("danger")
    assert "\033[31m" in out
    assert "danger" in out
    assert out.endswith("\033[0m")


def test_cli_green_emits_correct_color_code(monkeypatch):
    """Green uses code 32."""
    monkeypatch.setattr(cli, "_COLOR_ENABLED", True)
    out = cli.cli_green("ok")
    assert "\033[32m" in out


def test_cli_yellow_emits_correct_color_code(monkeypatch):
    """Yellow uses code 33."""
    monkeypatch.setattr(cli, "_COLOR_ENABLED", True)
    out = cli.cli_yellow("caveat")
    assert "\033[33m" in out


def test_diagnose_error_unknown_returns_plain():
    """Unknown exception text passes through with `error:` prefix."""
    out = cli.diagnose_error(RuntimeError("something failed"))
    assert "error:" in out
    assert "something failed" in out


def test_diagnose_error_module_missing_suggests_install():
    """ImportError with 'No module named' → suggests pip install."""
    out = cli.diagnose_error(ModuleNotFoundError("No module named 'scipy'"))
    assert "hint" in out
    assert "scipy" in out
    assert "pip install" in out


def test_diagnose_error_all_dofs_fixed_suggests_bc():
    """SolverError 'all degrees of freedom are fixed' → BC hint."""
    out = cli.diagnose_error(RuntimeError("all degrees of freedom are fixed"))
    assert "hint" in out
    assert "boundary_conditions" in out


def test_diagnose_error_stress_constraint_disabled_suggests_enable():
    """Errors mentioning stress_constraint → enable hint."""
    out = cli.diagnose_error(ValueError("stress_constraint must be enabled"))
    assert "hint" in out
    assert "enabled" in out
