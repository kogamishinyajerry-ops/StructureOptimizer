# v15 质量评分卡 — embedded constraints & rigorous closure（100 分 · 6 section）

> 与 v4-v14 同构：`python scripts/test_agent.py --rubric v15 [--strict]` 机械打分，写
> `tests/v15_scorecard.json`。`--strict` = total < 99 或任一回归（v4-v14 / D033 pytest-green）则 exit 1。
> 每个 wave 追溯一条 v14（D098-D104）/ 更早 ADR 的 "Reopening criteria"。
> **v15 特有**：embedding wave 把约束嵌入优化器循环，锚点必须证明约束**真绑定**
> （feasible + 改变无约束最优 + opt-in 默认逐位复现）。

## §1 embedded laminate constraints（24 分）

| 项 | 分 | 判据 |
|---|---|---|
| 1.1 balanced 约束嵌入 optimize_stacking_sequence | 8 | `core/orthotropic_simp.py` 排序优化器支持 balanced 约束 + 测试：balanced=True ⟹ A₁₆=A₂₆=0 + 约束**改变**结果 + **balanced=False 逐位复现 D095** |
| 1.2 约束化离散角选择（非退化最优）| 8 | `core/orthotropic_simp.py` 选择支持 balanced/symmetric 约束 + 测试：约束下非全选一角（退化消除）+ 仍最大化 D_11 s.t. 约束 + 无约束默认复现 D102 |
| 1.3 anti-symmetric 弯-剪解耦（D₁₆=D₂₆=0）| 8 | `core/orthotropic_simp.py` anti-symmetric 层合构造 + 测试：anti-symmetric ⟹ D₁₆=D₂₆=0 精确 + 对照 symmetric 仍 D₁₆≠0 |

## §2 embedded & rigorous geometry（15 分）

| 项 | 分 | 判据 |
|---|---|---|
| 2.1 concentric shells 接入 write_stl_cdt_multi_hole(refine) | 8 | `core/stl_export.py` STL writer 支持 concentric-shell 细化 + 测试：acute 截面 refine=True 水密 + 自然终止 + **refine=False byte-exact 复现 D100/D080** |
| 2.2 多-apex concentric-shell / 确定性 QMC 界（或诚实 defer）| 7 | `core/stl_export.py` 或 `core/reliability.py` 多小角 apex 终止+水密 / CBC lattice 确定性界 + 测试（**或诚实 defer**：probe 证据 + 先例记录）|

## §3 embedded dynamics & reliability（16 分）

| 项 | 分 | 判据 |
|---|---|---|
| 3.1 严格 KKT-binding peak-binding（或诚实 defer）| 8 | `core/freq_response.py` active 约束 regime（g₁≈0 + 正乘子 + 约束 design 的 J > 无约束 J）+ 测试（**或诚实 defer**：probe 证据 + D104 先例，8 分给"可证 defer 条件"或"成功 active 约束"二者之一）|
| 3.2 copula 系统可靠性接入 general Rosenblatt / 多 family | 8 | `core/reliability.py` copula 系统 P_f 接入 general-marginal 或多 family + 测试：多 family 对照 + 退化复现 D098 |

## §4 quality gates（20 分）

| 项 | 分 | 判据 |
|---|---|---|
| 4.1 Test count ≥ 1245 | 4 | `pytest --collect-only` |
| 4.2 Core coverage ≥ 95%（含 v15）| 4 | `pytest --cov=structure_optimizer/core` |
| 4.3 Property tests ≥ 62 | 3 | `^def test_property_` count |
| 4.4 Mutation kill rate ≥ 75% | 3 | `tests/mutation_report.json` |
| 4.5 Fingerprint DB ≥ 75 | 2 | `tests/fingerprints/*.json` count |
| 4.6 pytest gate green (D033) | 2 | D033 全绿门机制存在 |
| 4.7 v15 rubric 写入 agent + CI | 2 | `CHECKS_V15` + `.github/workflows/test.yml` |

## §5 demos（10 分）

| 项 | 分 | 判据 |
|---|---|---|
| 5.1 balanced-stacking / constrained-select demo | 3 | `scripts/v15_demos.py` |
| 5.2 concentric-export / multi-apex demo | 3 | 同上 |
| 5.3 anti-symmetric / copula-rosenblatt demo | 2 | 同上 |
| 5.4 peak-binding-active demo | 2 | 同上 |

## §6 docs（15 分）

| 项 | 分 | 判据 |
|---|---|---|
| 6.1 blueprint-v15 ≥6 wave ticks | 3 | `docs/blueprint-v15.md` |
| 6.2 tutorial v15 ≥4 §25.x sections | 3 | `docs/tutorial.md` |
| 6.3 architecture v15 section | 3 | `docs/architecture.md` `## 25.` + "embedded" |
| 6.4 ADRs D106+ ≥ 7 | 3 | `docs/decisions/D10[6-9]*.md` + `docs/decisions/D11*.md` |
| 6.5 v15 anchors documented | 3 | 测试里 v15 锚点关键词 ≥3 |

## 完成度门控

v15 release-ready = total ≥ 99/100 AND v4-v14 各 100（regression=False）AND D033 pytest gate green AND 全红线保持。

## v15 特有纪律（约束真绑定铁律）

- 每个把约束嵌入优化器的 wave：(a) 约束开启 ⟹ feasible；(b) 约束**改变**无约束最优（design 不同 / 目标可测代价 / 退化解消除）；(c) opt-in 默认 ⟹ 逐位复现原行为（v14 integration 铁律）。
- 叠加在"定量解析锚点（非 qualitative trend）"之上，不替代。
- DDDDDDD 严格 KKT-binding（D104 已证耦合但非 binding）与 GGGGGGG 形式终止/确定性界：若不成立 = **诚实 defer**（probe 证据 + 不伪造），该项 8/7 分给"可证 defer 条件 + 探针"或"成功成立"二者之一。
