"""Tests for the shared review-package fragments module.

The two HTML pages (demo.html, study.html) intentionally use different
disclaimer tones — see core/review_package.py docstring. These tests pin
that contract so a future refactor cannot accidentally collapse them.
"""

import pytest
from structure_optimizer.core.review_package import (
    format_metric_value,
    limitation_disclaimer_html,
    percent_reduction,
    status_badge_html,
    status_class,
    zh_check_name,
    zh_status,
    zh_stop_reason,
)


def test_zh_status_maps_known_statuses_to_chinese():
    assert zh_status("passed") == "通过"
    assert zh_status("warning") == "有警告"
    assert zh_status("failed") == "失败"
    assert zh_status("missing") == "缺失"


def test_zh_status_passes_unknown_through_html_escaped():
    assert zh_status("custom_state") == "custom_state"
    assert zh_status("<bad>") == "&lt;bad&gt;"


def test_zh_check_name_maps_known_manufacturability_checks():
    assert zh_check_name("isolated_islands") == "孤立材料岛"
    assert zh_check_name("thin_member_warning") == "薄构件风险"
    assert zh_check_name("local_density_warning") == "灰度密度区域"


def test_zh_stop_reason_maps_known_reasons():
    assert zh_stop_reason("max_iterations") == "达到最大迭代次数"
    assert zh_stop_reason("change_tolerance") == "变化量达到收敛阈值"


def test_status_class_returns_pass_only_for_passed():
    assert status_class("passed") == "pass"
    assert status_class("warning") == "warn"
    assert status_class("failed") == "warn"
    assert status_class(None) == "warn"


def test_format_metric_value_handles_special_cases():
    assert format_metric_value(None) == "n/a"
    assert format_metric_value(True) == "true"
    assert format_metric_value(False) == "false"
    assert format_metric_value("text") == "text"
    assert format_metric_value(1234.5) == "1.234e+03"
    assert format_metric_value(0.0001) == "1.000e-04"
    assert format_metric_value(0.5) == "0.5"
    assert format_metric_value(42.0) == "42"


def test_percent_reduction_computes_relative_drop():
    assert percent_reduction(1.0, 0.4) == "60.0%"
    assert percent_reduction(0.0, 0.4) == "n/a"
    assert percent_reduction(None, 0.4) == "n/a"


def test_status_badge_html_uses_shared_status_class():
    pass_badge = status_badge_html("passed")
    warn_badge = status_badge_html("failed")
    assert 'class="status pass"' in pass_badge
    assert 'class="status warn"' in warn_badge
    assert "通过" in pass_badge


def test_status_badge_html_accepts_label_override():
    badge = status_badge_html("passed", "验证状态：通过")
    assert "验证状态：通过" in badge


def test_evaluator_tone_disclaimer_uses_soft_vocabulary():
    """demo.html disclaimer must NOT contain engineering jargon string.

    This contract is enforced from the other side by tests/test_demo.py
    which asserts the string is absent from the rendered demo.html.
    """
    html = limitation_disclaimer_html("evaluator")
    assert "结构优化候选方案" in html
    assert "高保真校核" in html
    assert "2D/2.5D benchmark model" not in html
    assert "linear-elastic SIMP" not in html


def test_engineering_tone_disclaimer_uses_explicit_modeling_terms():
    """study.html disclaimer must include the explicit modeling terms so
    engineering reviewers see fidelity boundaries up front.

    This contract is enforced from the other side by tests/test_study.py
    which asserts both strings appear in the rendered study.html.
    """
    html = limitation_disclaimer_html("engineering")
    assert "optimization candidate" in html
    assert "2D/2.5D benchmark model" in html
    assert "高保真校核" in html
    assert 'class="limits"' in html


def test_limitation_disclaimer_rejects_unknown_tone():
    with pytest.raises(ValueError, match="Unknown limitation tone"):
        limitation_disclaimer_html("informal")
