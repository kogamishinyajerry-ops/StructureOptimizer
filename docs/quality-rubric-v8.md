# v8 质量评分卡 — closing the loop: gradient drivers + general distributions (100 分)

> 由 `scripts/test_agent.py --rubric v8` 机械打分，写 `tests/v8_scorecard.json`。
> 与 v4-v7 同构：6 section / 100 分 / D033 pytest-green gate（不计入 100 分，hard-fail）
> / v4·v5·v6·v7 in-process 回归门（各须保持满分）。
> 评分项是 grep-based presence + 定量测试引用：对应 wave 落地前 FAIL，落地后 PASS。

主题：把 v7 的半成品 driver **闭成完整环**，并把不确定性/几何提升到一般情形。每项追溯到
一条 v7（或更早）ADR 的 reopening criterion（见 blueprint-v8）。

## §1 driver 闭环（24 分）

| 项 | 分 | PASS 条件 | 源 |
|----|----|-----------|----|
| 1.1 几何非线性 TO 完整 OC 环 | 8 | `nonlinear_simp.py` OC 环 + 大变形 vs 线性拓扑差异测试 | D044 |
| 1.2 滤波动态柔度 TO 环（多频带） | 8 | `freq_response.py` 多频 OC 环 + 滤波 + 峰值下降测试 | D047 |
| 1.3 梯度种子 NSGA-III | 8 | `multi_objective_to.py` warm-start + HV-vs-budget 测试 | D046 |

## §2 不确定性（16 分）

| 项 | 分 | PASS 条件 | 源 |
|----|----|-----------|----|
| 2.1 一般 marginal Nataf（Gauss-Hermite） | 8 | `reliability.py` GH 积分 + Weibull/Gumbel 等效相关测试 | D045 |
| 2.2 系统可靠性（串/并联，Ditlevsen） | 8 | `reliability.py` system + Ditlevsen 上下界测试 | D042 |

## §3 几何 + 场（15 分）

| 项 | 分 | PASS 条件 | 源 |
|----|----|-----------|----|
| 3.1 纤维转向热 TO（优化 orientation 场） | 8 | `thermal_simp.py` orientation 灵敏度 vs FD 测试 | D043 |
| 3.2 MS 嵌套环 → ear-clipping 封顶 | 7 | `stl_export.py` 嵌套检测 + 带孔密度场水密 STL 测试 | D048 |

## §4 测试基础设施（20 分）

| 项 | 分 | PASS 条件 |
|----|----|-----------|
| 4.1 Test count ≥ 920 | 4 | `pytest --collect-only` ≥ 920 |
| 4.2 Core coverage ≥ 95%（含 v8） | 4 | `--cov=core` TOTAL ≥ 95% |
| 4.3 Property tests ≥ 42 | 3 | `^def test_property_` ≥ 42 |
| 4.4 Mutation kill rate ≥ 75% | 3 | `tests/mutation_report.json` ≥ 0.75 |
| 4.5 Fingerprint DB ≥ 40 | 2 | `tests/fingerprints/*.json` ≥ 40 |
| 4.6 pytest gate green（D033） | 2 | `check_pytest_green` + D033 ADR |
| 4.7 v8 rubric 写入 agent + CI | 2 | `CHECKS_V8` + CI `v8` step |

## §5 用户面 demos（10 分）

| 项 | 分 | PASS 条件 |
|----|----|-----------|
| 5.1 非线性/动态 OC-loop demo | 3 | `scripts/v8_demos.py` 真 demo |
| 5.2 梯度种子 NSGA demo | 3 | 同上 |
| 5.3 系统/一般分布可靠性 demo | 2 | 同上 |
| 5.4 纤维转向/带孔 STL demo | 2 | 同上 |

## §6 文档（15 分）

| 项 | 分 | PASS 条件 |
|----|----|-----------|
| 6.1 blueprint-v8 ≥6 ticks | 3 | `[x]` ≥ 6 |
| 6.2 tutorial v8 ≥4 new sections | 3 | `### 18.x` ≥ 4 |
| 6.3 architecture v8 section | 3 | `## 18.` + "loop" |
| 6.4 ADRs D050+ ≥ 7 | 3 | `docs/decisions/D05*.md` ≥ 7 |
| 6.5 v8 quantitative anchors documented | 3 | 测试中 v8 anchor 引用 ≥ 3 |

## 完成度门控

`--rubric v8` total ≥ 99 + v4/v5/v6/v7 regression=False + pytest gate green +
全永久红线保持。
