# v15 蓝图 — embedded constraints & rigorous closure: 把 v14 standalone 原语接入生产优化器作真约束 + 关闭 v14 诚实 defer

> Status: opening (design SSOT). Charter (standing, user 2026-05-24):
> "瞄准蓝图迭代到 ≥99/100，绝对诚实评分，wave 自动推进；完成一个里程碑继续下一个。"
> v14 完成（rubric 100/100，8 wave AAAAAA-HHHHHH，scorecard e1a2dbe，pytest 1218 passed）后开 v15。

## 永久红线（v1-v14 已建立 · v15 不可破）

- 无 CAD / GUI / cloud / full-3D / commercial 求解器 / LLM
- 运行时 mandatory deps 仍仅 `numpy`（scipy / pyamg / meshio 全部 optional）
- 本地可跑 — `pytest -q` 不依赖网络
- 失败仍单行 stderr + 状态码字符串
- 自我贬低优先于自我吹嘘

v15 在以上约束**内**把能力推进，不在以外做任何让步。所有"3D-like"措辞仍是 2.5D。

## v15 主题 — 与 v14 的关键区别

v14 把 v13 孤立原语**接入既有生产函数**（integration），但多数是**浅集成**：D101 balanced 只是 construction+verification（`make_balanced_laminate` / `is_balanced_laminate`）**未接 optimize_stacking_sequence**；D102 angle selection 复用 D095 排序但 max_bending 最优**退化**（无约束 ⟹ 全选一角）；D103 concentric-shell 只在 `constrained_delaunay_ruppert` 可达**未接 write_stl_cdt_multi_hole 的 refine 路径**；D104 peak-binding 证了耦合但**非严格 KKT-binding**（约束未 active、J 未牺牲）。

**v15 = embedded constraints & rigorous closure**：把这些 standalone 原语**接入生产优化器/写出器作真正绑定的约束**，并用**更严格的表述关闭 v14 的诚实 defer**。

> **本里程碑的核心纪律变化**：v15 多数 wave **把约束嵌入既有优化器循环**（不是只加新函数也不是浅 wiring），所以每个 embedding wave 的锚点测试**必须证明约束真绑定**——(a) 约束开启时结果满足约束（feasible），(b) 约束**改变**了无约束最优（design 不同 / 目标有可测代价 / 退化解被消除），(c) 关闭约束（opt-in 默认）**逐位复现**原行为（沿用 v14 integration 铁律）。这是 v15 特有的"约束真绑定"铁律，叠加在"定量解析锚点"+"backward-compat 逐位复现"之上。

每个 wave 仍按 v14 节奏：模块 + 测试（定量解析锚点 + backward-compat 逐位复现 + **约束绑定证据**）+ ADR + blueprint tick + tutorial §25.x + 相邻回归 + 1 commit。**做不到的诚实 defer**（沿用 D074/D085/D091/D104 先例——尤其 DDDDDDD 严格 KKT-binding 与 GGGGGGG 形式终止证明，若不成立则诚实 defer，绝不伪造）。

| 来源 ADR reopening criterion | v15 升级 |
|---|---|
| D101「wire balanced=True into optimize_stacking_sequence」 | balanced 约束嵌入排序优化器（搜索限于 balanced/symmetric-balanced 层合） |
| D100/D103「expose concentric_shells through write_stl_cdt_multi_hole(refine=True)」 | acute-cornered 截面端到端细化导出（concentric shells 进 STL writer） |
| D102「constrained selection (balanced/symmetric/D₁₆) so optimum non-degenerate」 | 约束化离散角选择（balanced 约束 ⟹ 非退化最优） |
| D104「strictly KKT-binding peak-binding with J sacrifice」 | 严格 active 约束 peak-binding（正乘子 + 可测 J 牺牲，或诚实 defer） |
| D101「D₁₆/D₂₆ bending-shear decoupling (anti-symmetric stacks)」 | anti-symmetric 层合 ⟹ D₁₆=D₂₆=0 弯-剪解耦 |
| D098「general Rosenblatt beyond series safety / other families」 | copula 系统可靠性接入 general Rosenblatt 或多 family 混合 |
| D103/D099「Shewchuk Terminator / multi-apex / deterministic QMC bound」 | 多-apex concentric-shell 或 CBC-认证 lattice 确定性界（或诚实 defer） |

## v15 八波

| Wave | 主题 | 关键模块 | 关键定量锚点 | ADR |
|------|------|----------|--------------|-----|
| AAAAAAA | balanced 约束嵌入 optimize_stacking_sequence | `core/orthotropic_simp.py` | balanced=True 搜索限 balanced 层合 ⟹ A₁₆=A₂₆=0 + symmetric-balanced 同时 B=0 + **balanced=False 逐位复现 D095** + 约束**改变**排序结果 | D106 |
| BBBBBBB | concentric shells 接入 write_stl_cdt_multi_hole(refine) | `core/stl_export.py` | acute 截面 refine=True 水密 STL + 自然终止 + **concentric_shells=False/refine=False byte-exact 复现 D100/D080** | D107 |
| CCCCCCC | 约束化离散角选择（非退化最优） | `core/orthotropic_simp.py` | balanced 约束下 select 非全选一角（退化消除）+ 仍最大化 D_11 s.t. 约束 + **无约束默认复现 D102** | D108 |
| DDDDDDD | 严格 KKT-binding peak-binding（或诚实 defer） | `core/freq_response.py` | 找到 active 约束 regime（g₁≈0 + 正乘子 + 约束 design 的 J > 无约束 J）**或诚实 defer 见 D104 先例** | D109 |
| EEEEEEE | anti-symmetric 层合 D₁₆=D₂₆=0 弯-剪解耦 | `core/orthotropic_simp.py` | anti-symmetric (+θ 上/−θ 镜像) ⟹ D₁₆=D₂₆=0 精确 + 对照 symmetric 仍 D₁₆≠0 | D110 |
| FFFFFFF | copula 系统可靠性接入 general Rosenblatt / 多 family | `core/reliability.py` | copula 系统 P_f 接入 general-marginal 路径 + 多 family（Gumbel/Clayton）对照 + 退化复现 D098 | D111 |
| GGGGGGG | 多-apex concentric-shell 或确定性 QMC 界（或诚实 defer） | `core/stl_export.py` / `core/reliability.py` | 多小角 apex 输入终止 + 水密 **或** CBC lattice 确定性界 **或诚实 defer** | D112 |
| HHHHHHH | v15 收口 | demos + tutorial §25 + architecture §25 + rubric | rubric ≥99；pytest gate green；v4-v14 无回归 | D113 |

## 完成度门控

v15 完成 = `python scripts/test_agent.py --rubric v15` 报告：

- [ ] v15 rubric total ≥ 99 / 100
- [ ] v14/v13/v12/v11/v10/v9/v8/v7/v6/v5/v4 regression = False（各 = 100）
- [ ] **pytest gate green**（D033 — 0 failed / 0 errors）
- [ ] 全红线保持

## 进度（wave 勾选）

- [x] AAAAAAA — balanced 约束嵌入 optimize_stacking_sequence（balanced=True ⟹ 输入 +θ/−θ 配对 multiset 再排序 ⟹ A₁₆=A₂₆=0；symmetric+balanced 同时 B=0；balanced=False byte-exact 复现 D095；约束改变设计[balanced=False 同输入 A₁₆≠0]；A 与序无关故构造非搜索限制；D106）
- [x] BBBBBBB — concentric shells 接入 write_stl_cdt_multi_hole(refine)（write_stl_cdt_multi_hole 加 concentric_shells 参数 + write_stl_concentric_export 包装；acute 截面 refine+concentric ⟹ 水密 STL 端到端，plain-refine 同输入 raise not_watertight；concentric_shells=False+refine byte-exact 复现 D100，refine=False 复现 D080；guard concentric-requires-refine；D107）
- [x] CCCCCCC — 约束化离散角选择（select_ply_angles 加 balanced；±候选 multiset 过滤到 balanced ⟹ 移除 D102 退化 all-one-angle 最优；非退化 ≥2 distinct + A₁₆=A₂₆=0；**D_11 零代价**（Q̄₁₁ 偶）；balanced=False byte-exact 复现 D102；D108）
- [x] DDDDDDD — 严格 KKT-binding peak-binding（**关闭 D104 defer**！）：kkt_binding_status 诊断（g₁=flank/limit−1，|g₁|≤tol ⟹ active；active_multiplier=J/J_ref−1>0 ⟹ 目标被牺牲）；**tight limit ≲0.1·init ⟹ 约束 active + J 牺牲**（实测 0.08·init: g₁≈−0.03 active, mult +0.37）；loose limit = D104 basin-selector（inactive, mult<0）；D109
- [ ] EEEEEEE — anti-symmetric 弯-剪解耦
- [ ] FFFFFFF — copula 系统可靠性 general Rosenblatt / 多 family
- [ ] GGGGGGG — 多-apex concentric-shell / 确定性 QMC 界（或诚实 defer）
- [ ] HHHHHHH — v15 收口（rubric ≥ 99）

> 注：v15 需在 `docs/quality-rubric-v15.md` + `scripts/test_agent.py` 的 `CHECKS_V15`
> 落地评分项后才能 `--rubric v15` 打分（与 v14 同构：6 section / 100 分 / D033 gate /
> v4-v14 回归门）。本 blueprint + rubric 是 scaffold 前置设计 SSOT；CHECKS_V15 wiring +
> 各 wave 实施按 cadence 推进。
>
> **v15 特有提醒**：embedding wave 把约束嵌入优化器循环，必须证明约束**真绑定**
> （feasible + 改变无约束最优 + opt-in 默认逐位复现）。`--rubric v15 --strict` 预计比
> v14 的 ~5.5h 更久（回归链增至 v4-v14 共 11 里程碑全量 coverage pass）——别误杀轮替的
> `pytest --cov` 子进程；nohup 启动不被 harness 追踪须自己 poll。
