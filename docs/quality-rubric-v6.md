# v6 质量评分表 — Production-grade formulations（100 分）

> 由 `scripts/test_agent.py --rubric v6` 机械评分（grep / file / pytest-collect / coverage）。
> 阈值故意定高、绝对诚实；写 rubric 的 agent 也实现 rubric，缓解靠机械可验 + CI + git 可审（D023）。
> v6 主题 = 把 v5 的 7 处有意简化升级为严格、可解析校验的生产级实现（见 blueprint-v6）。

## §1 严格公式升级（25 pts）

- **1.1 完整 Total-Lagrangian Green-strain Newton（8）** — `core/total_lagrangian.py`
  存在 + 测试断言对 Gere elastica 大变形 tip 挠度**定量**吻合（不是 v5 的 trend）。
- **1.2 Rayleigh 阻尼复频响（6）** — `core/freq_response.py` 有 damped harmonic（C = αM + βK）
  + 复数响应 + 测试。
- **1.3 各向异性 / 正交各向异性热传导（6）** — `core/thermal.py` 支持张量 k（kxx/kyy/kxy）
  + 正交各向异性 patch / 旋转不变测试。
- **1.4 NSGA-III ≥3 目标（5）** — `core/pareto_nsga.py` 有 NSGA-III（Das-Dennis 参考方向）
  + 3 目标测试。

## §2 高级可靠性 + 解析校验（20 pts）

- **2.1 FORM 可靠性指标 β（5）** — `core/reliability.py` 有 FORM（HL-RF）→ β / Pf + 测试。
- **2.2 Importance sampling（4）** — IS 估计器 + 相对 MC 的方差缩减测试。
- **2.3 SORM / 曲率修正（3）** — 二阶可靠性修正或曲率项 + 测试。
- **2.4 完整 TL objectivity + 解析 patch 校验（4）** — 有限刚体旋转 → Green 应变零（机器精度，
  区分完整 TL 与 v5 `K+½K_g` 近似）+ 均匀拉伸 E11 = ½(λ²−1) 解析定量断言。
  （比 continuum-vs-beam 的模糊 elastica 拟合更严谨可靠。）
- **2.5 半功率带宽解析校验（4）** — SDOF 阻尼共振半功率带宽 ≈ 解析，断言。

## §3 几何 + AD（15 pts）

- **3.1 Marching-squares 平滑边界 STL（5）** — `core/stl_export.py` 有平滑轮廓（非 voxel）
  + 面积收敛测试。
- **3.2 Reverse-mode AD（5）** — `core/autodiff.py` 有 reverse-mode（tape）。
- **3.3 AD reverse-vs-forward 一致性（5）** — reverse 梯度 == forward == 中心差分（多输入函数）测试。

## §4 工程质量（20 pts）

- **4.1 测试数 ≥ 850（4）** — pytest collect 计数。
- **4.2 core 覆盖率 ≥ 95%（4）** — 含 v6 新模块。
- **4.3 property 测试 ≥ 35（3）** — `def test_property_` 计数。
- **4.4 mutation kill rate ≥ 75%（3）** — `tests/mutation_report.json`。
- **4.5 fingerprint DB ≥ 30（2）** — `tests/fingerprints/*.json` 计数。
- **4.6 pytest gate green（2）** — D033：`pytest -q` 0 failed / 0 errors（`pytest_check.green`）。
- **4.7 v6 rubric 写入 agent + CI（2）** — `quality-rubric-v6` 被 test_agent 引用 + CI 跑 v6。

## §5 用户面（10 pts）

- **5.1 收敛研究 HTML（3）** — analytical-vs-numerical 收敛报告渲染。
- **5.2 阻尼频响图（3）** — magnitude/phase Bode-style 渲染。
- **5.3 3 目标 Pareto 渲染（2）** — NSGA-III front 可视化。
- **5.4 平滑 STL demo（2）** — smooth vs voxel 对比导出。

## §6 文档 + ADR（10 pts）

- **6.1 blueprint-v6 ≥6 wave ticks（2）** — `[x]` 计数。
- **6.2 tutorial v6 ≥4 新章节（3）** — `### 16.\d` / `### 17.\d` 计数。
- **6.3 architecture v6 段（2）** — `v6` + production-grade 段存在。
- **6.4 ADRs D034+ ≥ 7（3）** — `docs/decisions/D03[4-9]|D04[01]`。

## No-regression gates（hard fail, not part of 100）

- v5 rubric 仍 = 100/100
- v4 rubric 仍 = 100/100
- v3 ≥ 99 / v2 ≥ 97 / v1 = 100
- **`pytest -q` green**（D033）— 0 failed / 0 errors（skip ok）

任何 v1-v5 回归 **或 pytest red** 阻断 release，即使 v6 = 100。
