# v11 质量评分卡 — exact & robust (100 分)

> 由 `scripts/test_agent.py --rubric v11` 机械打分，写 `tests/v11_scorecard.json`。
> 与 v4-v10 同构：6 section / 100 分 / D033 pytest-green gate（不计入 100 分，hard-fail）
> / v4·v5·v6·v7·v8·v9·v10 in-process 回归门（各须保持满分）。
> 评分项是 grep-based presence + 定量测试引用：对应 wave 落地前 FAIL，落地后 PASS。

主题：把 v10 的"未处理应力奇异性 / 双变量 copula / 界中点近似 / 单孔几何 / 一阶投影梯度"升到
精确 + 鲁棒。每项追溯到一条 v10（或更早）ADR 的 reopening criterion（见 blueprint-v11）。

## §1 鲁棒约束 driver（24 分）

| 项 | 分 | PASS 条件 | 源 |
|----|----|-----------|----|
| 1.1 应力奇异性松弛 + 屈曲约束 | 8 | `stress.py`/`nonlinear_simp.py` qp-relaxed + 屈曲特征值约束测试 | D066 |
| 1.2 自适应频带采样 + peak-as-constraint | 8 | `freq_response.py` 自适应采样 + peak 约束测试 | D067 |
| 1.3 reference-free 多目标质量指标 | 8 | `multi_objective_to.py` hypervolume-only / R2 测试 | D068 |

## §2 不确定性（16 分）

| 项 | 分 | PASS 条件 | 源 |
|----|----|-----------|----|
| 2.1 d 维 / Gumbel Archimedean copula | 8 | `reliability.py` Gumbel/nested 条件 CDF + round-trip 测试 | D069 |
| 2.2 全相关矩阵 + Genz 精确多元系统 P_f | 8 | `reliability.py` Genz/MVN-CDF + 退化到二元测试 | D071 |

## §3 几何 + 场（15 分）

| 项 | 分 | PASS 条件 | 源 |
|----|----|-----------|----|
| 3.1 弹性同时 (ρ,θ) MMA + fibre-continuity | 8 | `orthotropic_simp.py` 弹性同时 MMA + 连续性约束测试 | D070 |
| 3.2 约束 Delaunay 多孔平滑+水密 | 7 | `stl_export.py` 约束 Delaunay 多孔水密测试 | D072 |

## §4 测试基础设施（20 分）

| 项 | 分 | PASS 条件 |
|----|----|-----------|
| 4.1 Test count ≥ 1050 | 4 | `pytest --collect-only` ≥ 1050 |
| 4.2 Core coverage ≥ 95%（含 v11） | 4 | `--cov=core` TOTAL ≥ 95% |
| 4.3 Property tests ≥ 48 | 3 | `^def test_property_` ≥ 48 |
| 4.4 Mutation kill rate ≥ 75% | 3 | `tests/mutation_report.json` ≥ 0.75 |
| 4.5 Fingerprint DB ≥ 55 | 2 | `tests/fingerprints/*.json` ≥ 55 |
| 4.6 pytest gate green（D033） | 2 | `check_pytest_green` + D033 ADR 存在 |
| 4.7 v11 rubric 写入 agent + CI | 2 | `CHECKS_V11` in agent + `v11` in CI yaml |

## §5 用户面 demos（10 分）

| 项 | 分 | PASS 条件 |
|----|----|-----------|
| 5.1 应力松弛+屈曲 / 自适应频带 demo | 3 | `qp_stress_demo`/`buckling_demo`/`adaptive_band_demo` 引用 ≥1 |
| 5.2 reference-free 指标 demo | 3 | `hypervolume_indicator_demo`/`r2_demo`/`reference_free_demo` 引用 ≥1 |
| 5.3 Gumbel copula / Genz 系统 demo | 2 | `gumbel_demo`/`genz_demo`/`mvn_cdf_demo` 引用 ≥1 |
| 5.4 弹性同时 MMA / 约束 Delaunay demo | 2 | `elastic_mma_demo`/`cdt_demo`/`constrained_delaunay_demo` 引用 ≥1 |

## §6 文档（15 分）

| 项 | 分 | PASS 条件 |
|----|----|-----------|
| 6.1 blueprint-v11 ≥6 ticks | 3 | `docs/blueprint-v11.md` `[x]` ≥ 6 |
| 6.2 tutorial v11 ≥4 new sections | 3 | `^### 21\.\d` ≥ 4 |
| 6.3 architecture v11 section | 3 | `docs/architecture.md` `## 21.` + "robust" |
| 6.4 ADRs D074+ ≥ 7 | 3 | `docs/decisions/D0[78]*.md` 编号 ≥ 74 共 ≥ 7 |
| 6.5 v11 quantitative anchors documented | 3 | 测试里 v11 锚点关键词 ≥ 3 |

## 完成度门控

`python scripts/test_agent.py --rubric v11 --strict` 须报告：v11 ≥ 99/100，v4-v10 全无回归
（各 = 100），pytest gate green（D033，0 failed/0 errors），全永久红线保持。
