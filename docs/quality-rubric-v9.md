# v9 质量评分卡 — second-order drivers: constrained optimisers + coupled fields + robust geometry (100 分)

> 由 `scripts/test_agent.py --rubric v9` 机械打分，写 `tests/v9_scorecard.json`。
> 与 v4-v8 同构：6 section / 100 分 / D033 pytest-green gate（不计入 100 分，hard-fail）
> / v4·v5·v6·v7·v8 in-process 回归门（各须保持满分）。
> 评分项是 grep-based presence + 定量测试引用：对应 wave 落地前 FAIL，落地后 PASS。

主题：把 v8 的"单移动极限 OC / 单场 / 独立优化 / 桥缝几何"升到二阶——真正的约束优化器
（MMA）、多场交替最小化、几何鲁棒化、可靠性从评估升成驱动 TO。每项追溯到一条 v8（或更早）
ADR 的 reopening criterion（见 blueprint-v9）。

## §1 driver 闭环（24 分）

| 项 | 分 | PASS 条件 | 源 |
|----|----|-----------|----|
| 1.1 MMA 驱动 TL 非线性 TO | 8 | `nonlinear_simp.py` MMA-TL 环 + 收敛 vs OC 终柔度测试 | D050 |
| 1.2 特征频率带隙 / minimax 频带 | 8 | `freq_response.py` 频带目标 + 灵敏度 vs FD + 带隙加宽测试 | D051 |
| 1.3 ≥3 目标多载况 NSGA-III | 8 | `multi_objective_to.py` 多载况 + 3-目标超体积测试 | D052 |

## §2 不确定性（16 分）

| 项 | 分 | PASS 条件 | 源 |
|----|----|-----------|----|
| 2.1 Rosenblatt 变换 | 8 | `reliability.py` Rosenblatt vs Nataf 一致 + round-trip 测试 | D053 |
| 2.2 系统可靠性驱动 TO | 8 | `rbto.py`/`reliability.py` 达到目标系统 β + 退化到 D042 测试 | D055 |

## §3 几何 + 场（15 分）

| 项 | 分 | PASS 条件 | 源 |
|----|----|-----------|----|
| 3.1 耦合密度+orientation 热 TO | 8 | `thermal_simp.py` 交替最小化 ≤ 单独优化 + 各向同性退化测试 | D054 |
| 3.2 slit-free 孔三角化（鲁棒水密） | 7 | `stl_export.py` 环形（曲线孔）水密 + 面积守恒 + 无桥缝边测试 | D056 |

## §4 测试基础设施（20 分）

| 项 | 分 | PASS 条件 |
|----|----|-----------|
| 4.1 Test count ≥ 960 | 4 | `pytest --collect-only` ≥ 960 |
| 4.2 Core coverage ≥ 95%（含 v9） | 4 | `--cov=core` TOTAL ≥ 95% |
| 4.3 Property tests ≥ 44 | 3 | `^def test_property_` ≥ 44 |
| 4.4 Mutation kill rate ≥ 75% | 3 | `tests/mutation_report.json` ≥ 0.75 |
| 4.5 Fingerprint DB ≥ 45 | 2 | `tests/fingerprints/*.json` ≥ 45 |
| 4.6 pytest gate green（D033） | 2 | `check_pytest_green` + D033 ADR 存在 |
| 4.7 v9 rubric 写入 agent + CI | 2 | `CHECKS_V9` in agent + `v9` in CI yaml |

## §5 用户面 demos（10 分）

| 项 | 分 | PASS 条件 |
|----|----|-----------|
| 5.1 MMA-TL / 带隙 demo | 3 | `mma_tl_demo`/`band_gap_demo` 引用 ≥1 |
| 5.2 ≥3 目标 NSGA demo | 3 | `three_objective_demo`/`multi_load_demo` 引用 ≥1 |
| 5.3 Rosenblatt / 系统 RBTO demo | 2 | `rosenblatt_demo`/`system_rbto_demo` 引用 ≥1 |
| 5.4 耦合场 / slit-free STL demo | 2 | `coupled_field_demo`/`slit_free_demo` 引用 ≥1 |

## §6 文档（15 分）

| 项 | 分 | PASS 条件 |
|----|----|-----------|
| 6.1 blueprint-v9 ≥6 ticks | 3 | `docs/blueprint-v9.md` `[x]` ≥ 6 |
| 6.2 tutorial v9 ≥4 new sections | 3 | `^### 19\.\d` ≥ 4 |
| 6.3 architecture v9 section | 3 | `docs/architecture.md` `## 19.` + "loop" |
| 6.4 ADRs D058+ ≥ 7 | 3 | `docs/decisions/D0[56]*.md` 编号 ≥ 58 共 ≥ 7 |
| 6.5 v9 quantitative anchors documented | 3 | 测试里 v9 锚点关键词 ≥ 3 |

## 完成度门控

`python scripts/test_agent.py --rubric v9 --strict` 须报告：v9 ≥ 99/100，v4/v5/v6/v7/v8
全无回归（各 = 100），pytest gate green（D033，0 failed/0 errors），全永久红线保持。
