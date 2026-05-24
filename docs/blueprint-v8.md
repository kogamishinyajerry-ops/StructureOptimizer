# v8 蓝图 — closing the loop: gradient drivers + general distributions + integrated geometry

> Status: in progress. Charter (standing, user 2026-05-24):
> "瞄准蓝图迭代到 ≥99/100，绝对诚实评分，wave 自动推进；完成一个里程碑继续下一个。"
> v7 完成（rubric 100/100，8 wave MM-TT）后开 v8。

## 永久红线（v1-v7 已建立 · v8 不可破）

- 无 CAD / GUI / cloud / full-3D / commercial 求解器 / LLM
- 运行时 mandatory deps 仍仅 `numpy`（scipy / pyamg / meshio 全部 optional）
- 本地可跑 — `pytest -q` 不依赖网络
- 失败仍单行 stderr + 状态码字符串
- 自我贬低优先于自我吹嘘

v8 在以上约束**内**把能力推进，不在以外做任何让步。所有"3D-like"措辞仍是 2.5D。

## v8 主题

v7 把 v6 的严格正向求解器**接成了 driver**，但多处刻意停在"灵敏度正确 + 紧凑投影梯度"
而非完整闭环优化器，且分布/几何仍有简化。v8 = **把这些半成品 driver 闭成完整环**，并把
不确定性/几何提升到一般情形。每个 wave 都源自 v7（或更早）ADR 明列的 "Reopening
criteria"——延续纪律：**每 wave 可追溯到一条已记录的 reopening criterion，不是数字追逐**。

| 来源 ADR reopening criterion | v8 升级 |
|---|---|
| D044「TL-in-the-loop 优化器 + 大变形 vs 线性拓扑差异」 | 几何非线性 TO 完整 OC 环 |
| D047「filtered MMA/OC dynamic-TO loop + multi-ω」 | 滤波动态柔度 TO 完整环（多频带平均） |
| D046「gradient-seeded initial population」 | 梯度种子 NSGA-III + hypervolume-vs-budget |
| D045「general marginals via Gauss-Hermite」 | 一般 marginal Nataf 积分（Weibull/Gumbel） |
| D043「optimising the orientation field itself（fibre-steering TO）」 | 纤维转向热 TO |
| D042「system reliability / nonlinear limit-state RBTO」 | 系统可靠性（多极限态串/并联） |
| D048「auto-detect nested MS loops → ear-clipping caps」 | marching-squares 嵌套环 → ear-clipping 封顶 |

## v8 八波

| Wave | 主题 | 关键模块 | 关键定量锚点 | ADR |
|------|------|----------|--------------|-----|
| UU | 几何非线性 TO 完整 OC 环 | `core/nonlinear_simp.py` (+driver) | TL-in-the-loop 收敛 + 柔度单调下降 + 大变形拓扑 ≠ 线性拓扑（可量化差异） | D050 |
| VV | 滤波动态柔度 TO 完整环（多频带） | `core/freq_response.py` (+driver) | 多频带平均动柔度 OC 环收敛 + 滤波后无 checkerboard + 峰值下降 | D051 |
| WW | 梯度种子 NSGA-III | `core/multi_objective_to.py` (+warm-start) | 种子前沿超体积 > 随机前沿（同预算）+ 端点匹配单目标 SIMP | D052 |
| XX | 一般 marginal Nataf（Gauss-Hermite） | `core/reliability.py` (+nataf integral) | Weibull/Gumbel 等效相关 vs 文献/数值积分基准；Gauss-Hermite 收敛 | D053 |
| YY | 纤维转向热 TO（优化 orientation 场） | `core/thermal_simp.py` (+orientation sens) | orientation 灵敏度 vs FD；转向后热柔度下降 vs 固定场 | D054 |
| ZZ | 系统可靠性（多极限态串/并联） | `core/reliability.py` (+system) | 串联 P_f 上下界（Ditlevsen）；独立情形精确；单极限态退化 | D055 |
| AAA | MS 嵌套环 → ear-clipping 封顶 | `core/stl_export.py` (+nesting) | 带内孔密度场水密 STL + 面积 = 外环−内环；偶奇嵌套检测正确 | D056 |
| BBB | v8 收口 | demos + tutorial §18 + architecture §18 + rubric | rubric ≥99；pytest gate green；v4/v5/v6/v7 无回归 | D057 |

每波按 v7 节奏：模块 + 测试（定量解析锚点，非 qualitative trend）+ fingerprint（如适用）
+ ADR + tutorial §18.x + adjacent-regression check + 1 commit。

## 完成度门控

v8 完成 = `python scripts/test_agent.py --rubric v8` 报告：

- [ ] v8 rubric total ≥ 99 / 100
- [ ] v7 regression = False（v7 = 100）
- [ ] v6 regression = False（v6 = 100）
- [ ] v5 regression = False（v5 = 100）
- [ ] v4 regression = False（v4 = 100）
- [ ] **pytest gate green**（D033 — 0 failed / 0 errors）
- [ ] 全红线保持

## 进度（wave 勾选）

- [x] UU — 几何非线性 TO 完整 OC 环（D050 · 2 tests green · TL 端柔度 2066→584 + 体积守恒 + TL-aware 比线性优化在 TL 柔度下低 8% + 拓扑可区分 L2/√n 0.066）
- [ ] VV — 滤波动态柔度 TO 完整环（多频带）
- [ ] WW — 梯度种子 NSGA-III
- [ ] XX — 一般 marginal Nataf（Gauss-Hermite）
- [ ] YY — 纤维转向热 TO
- [ ] ZZ — 系统可靠性（多极限态串/并联）
- [ ] AAA — MS 嵌套环 → ear-clipping 封顶
- [ ] BBB — v8 收口（rubric ≥ 99）

> 注：v8 需在 `docs/quality-rubric-v8.md` + `scripts/test_agent.py` 的 `CHECKS_V8` 落地
> 评分项后才能 `--rubric v8` 打分（与 v7 同构：6 section / 100 分 / D033 gate / v4-v7 回归门）。
> 这是 Wave UU 实施前的前置脚手架步骤。
