# v14 质量评分卡 — integration & production-wiring（100 分 · 6 section）

> 与 v4-v13 同构：`python scripts/test_agent.py --rubric v14 [--strict]` 机械打分，写
> `tests/v14_scorecard.json`。`--strict` = total < 99 或任一回归（v4-v13 / D033 pytest-green）则 exit 1。
> 每个 wave 追溯一条 v13（D090-D096）/ 更早 ADR 的 "Reopening criteria"。
> **v14 特有**：integration wave 改既有生产函数，锚点必须含 backward-compat 逐位复现断言。

## §1 production-wired reliability（16 分）

| 项 | 分 | 判据 |
|---|---|---|
| 1.1 d-Gumbel 接入 system_reliability_series | 8 | `core/reliability.py` 串联系统可靠性支持上尾 Gumbel copula 相关 + 测试：上尾相关 P_f vs 独立/Gaussian 差异 + **copula=None/独立默认逐位复现既有路径** |
| 1.2 Genz 重排接入 system_reliability_series_exact | 8 | `core/reliability.py` 精确系统 P_f 支持变量重排 + 测试：reorder=True 固定 N 误差降（vs 未排）+ **reorder=False 逐位复现 D078 既有值** |

## §2 production-wired geometry（15 分）

| 项 | 分 | 判据 |
|---|---|---|
| 2.1 Ruppert 接入 write_stl_cdt_multi_hole | 8 | `core/stl_export.py` 多孔 STL 导出支持 Ruppert 质量细化 + 测试：refine=True 最小角≥阈值 + 仍水密 + **refine=False 逐位复现 D080 既有 cap** |
| 2.2 Ruppert concentric-shell 小输入角 | 7 | `core/stl_export.py` acute 输入角 concentric-shell 分裂 + 测试：acute 角输入终止（无 max_steiner 兜底命中）+ 最小角达标 + 水密 |

## §3 generalized laminate & dynamics（24 分）

| 项 | 分 | 判据 |
|---|---|---|
| 3.1 balanced laminate 约束（A₁₆=A₂₆=0）| 8 | `core/orthotropic_simp.py` 有 balanced (+θ/−θ) 约束 + 测试：配对 ⟹ A₁₆=A₂₆=0 精确 + 与 symmetric B=0 同时成立 |
| 3.2 离散角集选择（非仅排序）| 8 | `core/orthotropic_simp.py` 从离散角集选 ply 组成 + 测试：最大化 D_11 / 最小化耦合 = brute-force 全局最优 |
| 3.3 peak-binding flanking-mode（细网格）| 8 | `core/freq_response.py` 细网格 peak-binding 产生不同设计 + 测试（**或诚实 defer**：probe 证据 + D091 先例记录，仍给 8 分如锚点是"defer 的可证条件"）|

## §4 quality gates（20 分）

| 项 | 分 | 判据 |
|---|---|---|
| 4.1 Test count ≥ 1185 | 4 | `pytest --collect-only` |
| 4.2 Core coverage ≥ 95%（含 v14）| 4 | `pytest --cov=structure_optimizer/core` |
| 4.3 Property tests ≥ 59 | 3 | `^def test_property_` count |
| 4.4 Mutation kill rate ≥ 75% | 3 | `tests/mutation_report.json` |
| 4.5 Fingerprint DB ≥ 70 | 2 | `tests/fingerprints/*.json` count |
| 4.6 pytest gate green (D033) | 2 | D033 全绿门机制存在 |
| 4.7 v14 rubric 写入 agent + CI | 2 | `CHECKS_V14` + `.github/workflows/test.yml` |

## §5 demos（10 分）

| 项 | 分 | 判据 |
|---|---|---|
| 5.1 Gumbel-series / Genz-reorder-series demo | 3 | `scripts/v14_demos.py` |
| 5.2 Ruppert-export / concentric-shell demo | 3 | 同上 |
| 5.3 balanced-laminate / angle-select demo | 2 | 同上 |
| 5.4 peak-binding demo | 2 | 同上 |

## §6 docs（15 分）

| 项 | 分 | 判据 |
|---|---|---|
| 6.1 blueprint-v14 ≥6 wave ticks | 3 | `docs/blueprint-v14.md` |
| 6.2 tutorial v14 ≥4 §24.x sections | 3 | `docs/tutorial.md` |
| 6.3 architecture v14 section | 3 | `docs/architecture.md` `## 24.` + "integration" |
| 6.4 ADRs D098+ ≥ 7 | 3 | `docs/decisions/D09[8-9]*.md` + `docs/decisions/D10[0-5]*.md` |
| 6.5 v14 anchors documented | 3 | 测试里 v14 锚点关键词 ≥3 |

## 完成度门控

v14 release-ready = total ≥ 99/100 AND v4-v13 各 100（regression=False）AND D033 pytest gate green AND 全红线保持。

## v14 特有纪律（integration 铁律）

- 每个改既有生产函数的 wave：新参数 **opt-in 默认**，且锚点测试**逐位复现**原行为（证明集成不回归）。
- 这叠加在原有"定量解析锚点（非 qualitative trend）"纪律之上，不替代。
- GGGGGG peak-binding 已在 v13 smoke mesh defer 过一次；细网格若仍不成立 = **再次诚实 defer**（probe 证据 + 不伪造），§3.3 的 8 分给"可证的 defer 条件 + 探针"或"成功的不同设计"二者之一。
