# v14 蓝图 — integration & production-wiring: 把 v13 孤立原语接入生产驱动器 + 完成 robustness 收尾

> Status: opening (design SSOT). Charter (standing, user 2026-05-24):
> "瞄准蓝图迭代到 ≥99/100，绝对诚实评分，wave 自动推进；完成一个里程碑继续下一个。"
> v13 完成（rubric 100/100，8 wave AAAAA-HHHHH，commit b8ef676）后开 v14。

## 永久红线（v1-v13 已建立 · v14 不可破）

- 无 CAD / GUI / cloud / full-3D / commercial 求解器 / LLM
- 运行时 mandatory deps 仍仅 `numpy`（scipy / pyamg / meshio 全部 optional）
- 本地可跑 — `pytest -q` 不依赖网络
- 失败仍单行 stderr + 状态码字符串
- 自我贬低优先于自我吹嘘

v14 在以上约束**内**把能力推进，不在以外做任何让步。所有"3D-like"措辞仍是 2.5D。

## v14 主题 — 与 v6-v13 的关键区别

v6-v13 每个 wave 加的是**孤立新能力**（每 wave = 新模块函数 + 锚点测试，彼此独立、低耦合）。v13 收口的 D097 诚实记录了一批**未接入生产驱动器**的原语：d-Gumbel(D093) / Genz-reorder(D094) 未进 `system_reliability_series`；Ruppert(D096) 未进 `write_stl_cdt_multi_hole`；铺层(D095) 只优化排列非角度值、无 balanced 约束；Ruppert 无小输入角处理；peak-binding 不同设计(D091/D083) 在 smoke mesh deferred。

**v14 = integration & production-wiring**：把这些原语**接入既有生产函数** + 完成 robustness 收尾。

> **本里程碑的核心风险与纪律变化**：v14 多数 wave **修改既有生产函数**（不是只加新函数），所以每个 integration wave 的锚点测试**必须包含 backward-compatibility 断言**——新参数默认值（opt-in）必须**逐位复现**原行为，证明集成不回归。这是 v14 特有的"集成不破坏"铁律，叠加在原有"定量解析锚点"纪律之上。

每个 wave 仍按 v13 节奏：模块 + 测试（定量解析锚点 + **backward-compat 逐位复现**）+ ADR + blueprint tick + tutorial §24.x + 相邻回归 + 1 commit。**做不到的诚实 defer**（沿用 D074/D085/D091 先例——尤其 GGGGGG peak-binding 在 smoke 上已 defer 过一次，细网格若仍不成立则再 defer，绝不伪造）。

| 来源 ADR reopening criterion | v14 升级 |
|---|---|
| D093「wire d-Gumbel into system_reliability_series」 | 上尾相关串联系统可靠性（Gumbel copula 进生产路径）|
| D094「wire Genz reordering into series / lattice」 | 方差缩减的生产可靠性路径（reorder 进 system_reliability_series_exact）|
| D096「wire Ruppert into write_stl_cdt_multi_hole」 | 质量细化的导出 STL cap |
| D095「balanced laminate constraint (+θ/−θ ⟹ A₁₆=A₂₆=0)」 | balanced + symmetric 铺层约束 |
| D095「angle-value selection beyond ordering」 | 离散角集**选择**（选哪些角，非仅排序）|
| D096「small-input-angle handling (concentric-shell)」 | acute 角 concentric-shell 分裂（Ruppert 无 max_steiner 兜底也终止）|
| D091/D083「peak-binding 不同设计（细网格反共振 flanking-mode）」 | 细网格证明 in-loop re-gridding 改变设计（或再次诚实 defer）|

## v14 八波

| Wave | 主题 | 关键模块 | 关键定量锚点 | ADR |
|------|------|----------|--------------|-----|
| AAAAAA | d-Gumbel 接入 system_reliability_series | `core/reliability.py` | 上尾相关串联 P_f（Gumbel copula）+ **独立 copula 默认逐位复现既有 Gaussian/独立路径** | D098 |
| BBBBBB | Genz 重排接入 system_reliability_series_exact | `core/reliability.py` | reorder=True 固定 N 误差降 + **reorder=False 逐位复现 D078 既有值** | D099 |
| CCCCCC | Ruppert 接入 write_stl_cdt_multi_hole | `core/stl_export.py` | refine=True 最小角≥阈值 + 水密 + **refine=False 逐位复现 D080/既有 cap** | D100 |
| DDDDDD | balanced laminate 约束 | `core/orthotropic_simp.py` | +θ/−θ 配对 ⟹ A₁₆=A₂₆=0 精确 + 与 symmetric B=0 同时成立 | D101 |
| EEEEEE | 离散角集选择（非仅排序）| `core/orthotropic_simp.py` | 从 {0,±45,90} 选 ply 集最大化 D_11 / 最小化耦合 = brute-force 全局 | D102 |
| FFFFFF | Ruppert concentric-shell 小输入角 | `core/stl_export.py` | acute 角输入终止（无 max_steiner 兜底）+ 最小角达标 + 水密 | D103 |
| GGGGGG | peak-binding flanking-mode（细网格）| `core/freq_response.py` | 细网格 min J(ω_op) 升带内 flanking 峰 → in-loop 改变设计（**或诚实 defer 见 D091 先例**）| D104 |
| HHHHHH | v14 收口 | demos + tutorial §24 + architecture §24 + rubric | rubric ≥99；pytest gate green；v4-v13 无回归 | D105 |

## 完成度门控

v14 完成 = `python scripts/test_agent.py --rubric v14` 报告：

- [ ] v14 rubric total ≥ 99 / 100
- [ ] v13/v12/v11/v10/v9/v8/v7/v6/v5/v4 regression = False（各 = 100）
- [ ] **pytest gate green**（D033 — 0 failed / 0 errors）
- [ ] 全红线保持

## 进度（wave 勾选）

- [x] AAAAAA — d-Gumbel 接入 system_reliability_series（P_f=1−C(Φ(β)); Gumbel θ=1 bit-exact 复现独立串联; θ↑ 单调降至 comonotone max P_i; D098）
- [ ] BBBBBB — Genz 重排接入 system_reliability_series_exact
- [ ] CCCCCC — Ruppert 接入 write_stl_cdt_multi_hole
- [ ] DDDDDD — balanced laminate 约束
- [ ] EEEEEE — 离散角集选择
- [ ] FFFFFF — Ruppert concentric-shell 小输入角
- [ ] GGGGGG — peak-binding flanking-mode（细网格，或诚实 defer）
- [ ] HHHHHH — v14 收口（rubric ≥ 99）

> 注：v14 需在 `docs/quality-rubric-v14.md` + `scripts/test_agent.py` 的 `CHECKS_V14`
> 落地评分项后才能 `--rubric v14` 打分（与 v13 同构：6 section / 100 分 / D033 gate /
> v4-v13 回归门）。本 blueprint + rubric 是 scaffold 前置设计 SSOT；CHECKS_V14 wiring +
> 各 wave 实施按 cadence 推进。
>
> **v14 特有提醒**：integration wave 改既有生产函数，必须 opt-in 默认 + backward-compat
> 逐位复现断言。`--rubric v14 --strict` 预计比 v13 的 ~6h 更久（回归链增至 v4-v13 共 10
> 里程碑全量 coverage pass）——别误杀轮替的 `pytest --cov` 子进程。
