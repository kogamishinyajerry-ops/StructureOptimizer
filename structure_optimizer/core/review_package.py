"""Shared review-package fragments for demo.html (single run) and study.html
(multi-candidate comparison).

Single source of truth for:

- Chinese status / check-name / stop-reason maps
- Status badge CSS palette + HTML
- Number formatting
- Limitation disclaimer in two tones:
    - ``evaluator``:    used by ``demo.html`` — soft, narrative, audience may
      include non-CFD reviewers. Avoids the literal phrase
      ``"2D/2.5D benchmark model"`` (asserted by tests/test_demo.py).
    - ``engineering``:  used by ``study.html`` — explicit reference to
      ``"2D/2.5D benchmark model"`` and ``"linear-elastic SIMP"`` so an
      engineering reviewer sees the modeling fidelity up front
      (asserted by tests/test_study.py).

The split is intentional and load-bearing. Do not collapse the two tones
without updating the corresponding test contracts.
"""

from __future__ import annotations

from html import escape
from typing import Any

ZH_STATUS_MAP: dict[str, str] = {
    "passed": "通过",
    "warning": "有警告",
    "failed": "失败",
    "missing": "缺失",
}

ZH_CHECK_NAME_MAP: dict[str, str] = {
    "isolated_islands": "孤立材料岛",
    "thin_member_warning": "薄构件风险",
    "local_density_warning": "灰度密度区域",
}

ZH_STOP_REASON_MAP: dict[str, str] = {
    "max_iterations": "达到最大迭代次数",
    "change_tolerance": "变化量达到收敛阈值",
}


def zh_status(status: Any) -> str:
    """Translate a verification status (e.g. ``"passed"``) to its Chinese label, or escape if unknown."""
    return ZH_STATUS_MAP.get(str(status), escape(str(status)))


def zh_check_name(name: str) -> str:
    """Translate a manufacturability check identifier to its Chinese label."""
    return ZH_CHECK_NAME_MAP.get(name, escape(name))


def zh_stop_reason(reason: Any) -> str:
    """Translate a SIMP-loop stop reason (e.g. ``"max_iterations"``) to its Chinese label."""
    return ZH_STOP_REASON_MAP.get(str(reason), escape(str(reason)))


def status_class(status: Any) -> str:
    """Map verification status to a CSS class fragment.

    ``passed`` → ``pass`` so existing demo.html selectors ``.status.pass``
    keep working; everything else → ``warn``.
    """
    return "pass" if str(status) == "passed" else "warn"


def format_metric_value(value: Any) -> str:
    """Numeric formatter shared by review HTML pages.

    Rules:
    - ``None`` → ``"n/a"``
    - bool → ``"true"`` / ``"false"``
    - very large / very small numbers → scientific notation
    - otherwise → 4 significant digits

    Existing demo.py and study.py had slightly divergent rules. This unifies
    on demo.py's behavior, which is the more common case in the review pages.
    """
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        # Empty string would render as a blank table cell — collapse to n/a
        # for visual consistency with None.
        return escape(value) if value else "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return escape(str(value))
    if abs(number) >= 1000 or (0 < abs(number) < 0.001):
        return f"{number:.3e}"
    return f"{number:.4g}"


def limitation_disclaimer_html(tone: str) -> str:
    """Return the limitation disclaimer block, in ``evaluator`` or
    ``engineering`` tone.

    Both tones share the same engineering reality (optimization candidate, not
    a certified part) but use different vocabulary. See module docstring.
    """
    if tone == "evaluator":
        return (
            '<section class="panel limitation" style="margin-top: 18px;">'
            "<h2>结果适用范围</h2>"
            "<p>本页展示的是结构优化候选方案，不是可直接投产的认证设计。"
            "后续仍需要工程师完成高保真校核、制造性复核和必要的物理测试，"
            "才能进入工程评审通过状态。</p>"
            "<p>密度图反映载荷路径分布；柔度、最大位移和近似应力为简化模型下的"
            "工程趋势指标，使用前请结合具体许用值与设计规范判断。</p>"
            "</section>"
        )
    if tone == "engineering":
        return (
            "<section>"
            "<h2>限制说明</h2>"
            '<p class="limits">这些结果是本地线弹性 SIMP 的 optimization candidate '
            "对比，不是生产认证结论。当前模型仅覆盖 2D/2.5D benchmark model，"
            "需要工程师继续做高保真校核、制造性复核和必要的物理测试。</p>"
            "</section>"
        )
    raise ValueError(f"Unknown limitation tone: {tone!r}; expected 'evaluator' or 'engineering'")


def status_badge_html(status: Any, label_zh: str | None = None) -> str:
    """Render a status pill with shared CSS classes (``status pass`` / ``status warn``).

    ``label_zh`` overrides the rendered label; defaults to the Chinese status word.
    """
    label = label_zh if label_zh is not None else zh_status(status)
    return f'<span class="status {status_class(status)}">{escape(label)}</span>'


def percent_reduction(baseline: Any, candidate: Any) -> str:
    """Format ``(baseline - candidate) / baseline`` as a signed percentage; ``"n/a"`` on bad inputs."""
    try:
        base = float(baseline)
        cand = float(candidate)
    except (TypeError, ValueError):
        return "n/a"
    if base == 0:
        return "n/a"
    return f"{(base - cand) / base * 100.0:.1f}%"
