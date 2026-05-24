# v9 蓝图 — second-order drivers: constrained optimisers + coupled fields + robust geometry

> Status: in progress. Charter (standing, user 2026-05-24):
> "瞄准蓝图迭代到 ≥99/100，绝对诚实评分，wave 自动推进；完成一个里程碑继续下一个。"
> v8 完成（rubric 100/100，8 wave UU-BBB）后开 v9。

## 永久红线（v1-v8 已建立 · v9 不可破）

- 无 CAD / GUI / cloud / full-3D / commercial 求解器 / LLM
- 运行时 mandatory deps 仍仅 `numpy`（scipy / pyamg / meshio 全部 optional）
- 本地可跑 — `pytest -q` 不依赖网络
- 失败仍单行 stderr + 状态码字符串
- 自我贬低优先于自我吹嘘

v9 在以上约束**内**把能力推进，不在以外做任何让步。所有"3D-like"措辞仍是 2.5D。

## v9 主题

v8 把 v7 的"灵敏度 + 紧凑投影梯度"闭成了 OC 环，并把分布/几何一般化，但多处仍停在
**单移动极限 OC / 单场 / 独立优化 / 桥缝几何**。v9 = **把这些 driver 升到二阶**：用真正的
约束优化器（MMA）替代单移动极限 OC、把单场优化耦合成多场交替最小化、把几何鲁棒化
（slit-free 水密）、把可靠性从"评估"升成"驱动 TO"。每个 wave 都源自 v8（或更早）ADR 明列
的 "Reopening criteria"——延续纪律：**每 wave 可追溯到一条已记录的 reopening criterion，
不是数字追逐**。

| 来源 ADR reopening criterion | v9 升级 |
|---|---|
| D050「MMA driving the TL adjoint」 | MMA 约束优化器驱动 TL 非线性 TO |
| D051「eigenfrequency-gap (band-stop) objective built on the modal solver」 | 特征频率带隙 / minimax 频带目标 |
| D052「≥3 objectives (multi-load-case) with seeded warm-start」 | ≥3 目标多载况 NSGA-III + 种子 warm-start |
| D053「Rosenblatt transform (conditional CDFs) for known joint distributions」 | Rosenblatt 变换（已知联合分布） |
| D054「coupled density + orientation TO (alternating minimisation)」 | 耦合密度 + orientation 热 TO |
| D055「system-reliability-based TO (drive a topology to a target system β)」 | 系统可靠性驱动 TO |
| D056「slit-free hole triangulation (constrained Delaunay / monotone polygon)」 | slit-free 孔三角化（曲线孔鲁棒水密） |

## v9 八波

| Wave | 主题 | 关键模块 | 关键定量锚点 | ADR |
|------|------|----------|--------------|-----|
| CCC | MMA 驱动 TL 非线性 TO | `core/nonlinear_simp.py` (+MMA driver) | MMA-TL 环收敛 + 柔度单调下降 + ≤ OC 终柔度（同预算）+ 体积约束满足 | D058 |
| DDD | 特征频率带隙 / minimax 频带目标 | `core/freq_response.py` / `modal.py` (+band objective) | minimax 频带目标灵敏度 vs FD + 带隙加宽（优化后峰值带内下降）+ 体积守恒 | D059 |
| EEE | ≥3 目标多载况 NSGA-III + 种子 | `core/multi_objective_to.py` (+3-obj) | 3D Das-Dennis 参考点精确组合数 + 3-目标超体积单调 + 种子前沿 ⊇ 随机端点 | D060 |
| FFF | Rosenblatt 变换（已知联合分布） | `core/reliability.py` (+rosenblatt) | Rosenblatt vs Nataf 在高斯 copula 下一致 + round-trip x→u→x 1e-10 + 条件 CDF 单调 | D061 |
| GGG | 耦合密度 + orientation 热 TO | `core/thermal_simp.py` (+coupled) | 交替最小化热柔度 ≤ 单独优化密度 or orientation + 单调收敛 + 各向同性退化到纯密度 TO | D062 |
| HHH | 系统可靠性驱动 TO | `core/rbto.py` / `reliability.py` (+system RBTO) | 达到目标系统 β（串联 2 模式）+ 体积随目标 β 单调 + 退化到单模式=D042 RBTO | D063 |
| III | slit-free 孔三角化（鲁棒水密） | `core/stl_export.py` (+monotone/CDT) | 环形（曲线孔）密度场**水密** + 面积=外环−内环 1e-9 + 无桥缝边（每边恰 2 三角） | D064 |
| JJJ | v9 收口 | demos + tutorial §19 + architecture §19 + rubric | rubric ≥99；pytest gate green；v4/v5/v6/v7/v8 无回归 | D065 |

每波按 v8 节奏：模块 + 测试（定量解析锚点，非 qualitative trend）+ fingerprint（如适用）
+ ADR + tutorial §19.x + adjacent-regression check + 1 commit。

## 完成度门控

v9 完成 = `python scripts/test_agent.py --rubric v9` 报告：

- [ ] v9 rubric total ≥ 99 / 100
- [ ] v8 regression = False（v8 = 100）
- [ ] v7 regression = False（v7 = 100）
- [ ] v6 regression = False（v6 = 100）
- [ ] v5 regression = False（v5 = 100）
- [ ] v4 regression = False（v4 = 100）
- [ ] **pytest gate green**（D033 — 0 failed / 0 errors）
- [ ] 全红线保持

## 进度（wave 勾选）

- [x] CCC — MMA 驱动 TL 非线性 TO（D058 · 4 tests green · 全 TL 端柔度 2066→553（3.7× 降）+ 体积可行 0.4497≤0.45 + MMA/OC 比 0.946（MMA 比 OC 低 5.4%）+ 确定性 + 体积尾部贴约束；诚实：compliance-only 上 MMA≈OC，多约束才是真优势，是 reopening 项）
- [x] DDD — 特征频率带隙 / minimax 频带目标（D059 · 5 tests green · 带隙灵敏度 dg/dρ vs 中心 FD rel 1.76e-6（mass-normalized 模态特征值灵敏度精确）+ 体积守恒爬升使带隙加宽 2.2× + 模态被推开 + 确定性 + 契约；诚实：假设非重根、投影梯度爬升非 MMA、未做目标频带放置）
- [ ] EEE — ≥3 目标多载况 NSGA-III + 种子
- [ ] FFF — Rosenblatt 变换（已知联合分布）
- [ ] GGG — 耦合密度 + orientation 热 TO
- [ ] HHH — 系统可靠性驱动 TO
- [ ] III — slit-free 孔三角化（鲁棒水密）
- [ ] JJJ — v9 收口（rubric ≥ 99）

> 注：v9 需在 `docs/quality-rubric-v9.md` + `scripts/test_agent.py` 的 `CHECKS_V9` 落地
> 评分项后才能 `--rubric v9` 打分（与 v8 同构：6 section / 100 分 / D033 gate / v4-v8 回归门）。
> 这是 Wave CCC 实施前的前置脚手架步骤。
