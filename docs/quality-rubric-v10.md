# v10 质量评分卡 — constraint-rich & manufacturable (100 分)

> 由 `scripts/test_agent.py --rubric v10` 机械打分，写 `tests/v10_scorecard.json`。
> 与 v4-v9 同构：6 section / 100 分 / D033 pytest-green gate（不计入 100 分，hard-fail）
> / v4·v5·v6·v7·v8·v9 in-process 回归门（各须保持满分）。
> 评分项是 grep-based presence + 定量测试引用：对应 wave 落地前 FAIL，落地后 PASS。

主题：把 v9 的"单约束 / 高斯 copula / 块坐标 / 阶梯几何"升到约束丰富 + 可制造。每项追溯到一条
v9（或更早）ADR 的 reopening criterion（见 blueprint-v10）。

## §1 约束丰富 driver（24 分）

| 项 | 分 | PASS 条件 | 源 |
|----|----|-----------|----|
| 1.1 多约束 MMA（应力 p-norm + 体积） | 8 | `nonlinear_simp.py` 多约束 MMA + 应力 p-norm 灵敏度测试 | D058 |
| 1.2 目标频带放置（minimax around target） | 8 | `freq_response.py` 目标带 + 带内峰值灵敏度测试 | D059 |
| 1.3 泛化 NSGA driver + IGD+ | 8 | `multi_objective_to.py` nsga3_density_to + IGD+ 测试 | D060 |

## §2 不确定性（16 分）

| 项 | 分 | PASS 条件 | 源 |
|----|----|-----------|----|
| 2.1 Archimedean copula Rosenblatt | 8 | `reliability.py` Clayton/Frank 条件 CDF + round-trip 测试 | D061 |
| 2.2 相关系统模态 RBTO | 8 | `rbto.py` 相关系统 β 驱动 + 退化到独立测试 | D063 |

## §3 几何 + 场（15 分）

| 项 | 分 | PASS 条件 | 源 |
|----|----|-----------|----|
| 3.1 同时 (ρ,θ) MMA 耦合 | 8 | `thermal_simp.py` 同时 MMA + vs 交替最小化测试 | D062 |
| 3.2 平滑且水密带孔三角化 | 7 | `stl_export.py` 平滑轮廓 + 环形孔水密测试 | D064 |

## §4 测试基础设施（20 分）

| 项 | 分 | PASS 条件 |
|----|----|-----------|
| 4.1 Test count ≥ 1000 | 4 | `pytest --collect-only` ≥ 1000 |
| 4.2 Core coverage ≥ 95%（含 v10） | 4 | `--cov=core` TOTAL ≥ 95% |
| 4.3 Property tests ≥ 46 | 3 | `^def test_property_` ≥ 46 |
| 4.4 Mutation kill rate ≥ 75% | 3 | `tests/mutation_report.json` ≥ 0.75 |
| 4.5 Fingerprint DB ≥ 50 | 2 | `tests/fingerprints/*.json` ≥ 50 |
| 4.6 pytest gate green（D033） | 2 | `check_pytest_green` + D033 ADR 存在 |
| 4.7 v10 rubric 写入 agent + CI | 2 | `CHECKS_V10` in agent + `v10` in CI yaml |

## §5 用户面 demos（10 分）

| 项 | 分 | PASS 条件 |
|----|----|-----------|
| 5.1 多约束 / 目标频带 demo | 3 | `multi_constraint_demo`/`target_band_demo` 引用 ≥1 |
| 5.2 泛化 NSGA / IGD+ demo | 3 | `igd_plus_demo`/`generalized_nsga_demo` 引用 ≥1 |
| 5.3 copula / 相关系统 demo | 2 | `clayton_demo`/`correlated_system_demo` 引用 ≥1 |
| 5.4 同时 MMA / 平滑水密 demo | 2 | `simultaneous_mma_demo`/`smooth_watertight_demo` 引用 ≥1 |

## §6 文档（15 分）

| 项 | 分 | PASS 条件 |
|----|----|-----------|
| 6.1 blueprint-v10 ≥6 ticks | 3 | `docs/blueprint-v10.md` `[x]` ≥ 6 |
| 6.2 tutorial v10 ≥4 new sections | 3 | `^### 20\.\d` ≥ 4 |
| 6.3 architecture v10 section | 3 | `docs/architecture.md` `## 20.` + "constraint" |
| 6.4 ADRs D066+ ≥ 7 | 3 | `docs/decisions/D0[67]*.md` 编号 ≥ 66 共 ≥ 7 |
| 6.5 v10 quantitative anchors documented | 3 | 测试里 v10 锚点关键词 ≥ 3 |

## 完成度门控

`python scripts/test_agent.py --rubric v10 --strict` 须报告：v10 ≥ 99/100，v4-v9 全无回归
（各 = 100），pytest gate green（D033，0 failed/0 errors），全永久红线保持。
