# v10 蓝图 — constraint-rich & manufacturable: multi-constraint optimisers + general copulas + smooth-watertight geometry

> Status: in progress. Charter (standing, user 2026-05-24):
> "瞄准蓝图迭代到 ≥99/100，绝对诚实评分，wave 自动推进；完成一个里程碑继续下一个。"
> v9 完成（rubric 100/100，8 wave CCC-JJJ）后开 v10。

## 永久红线（v1-v9 已建立 · v10 不可破）

- 无 CAD / GUI / cloud / full-3D / commercial 求解器 / LLM
- 运行时 mandatory deps 仍仅 `numpy`（scipy / pyamg / meshio 全部 optional）
- 本地可跑 — `pytest -q` 不依赖网络
- 失败仍单行 stderr + 状态码字符串
- 自我贬低优先于自我吹嘘

v10 在以上约束**内**把能力推进，不在以外做任何让步。所有"3D-like"措辞仍是 2.5D。

## v10 主题

v9 把 driver 升到二阶（MMA、耦合场、系统可靠性、鲁棒几何），但多处仍是**单约束 / 高斯
copula / 块坐标 / 阶梯几何**。v10 = **把这些推到约束丰富 + 可制造**：多约束优化器（应力/屈曲）、
一般 copula、同时多场 MMA、平滑且水密的几何。每个 wave 都源自 v9（或更早）ADR 明列的
"Reopening criteria"——延续纪律：**每 wave 可追溯到一条已记录的 reopening criterion，不是数字
追逐**。

| 来源 ADR reopening criterion | v10 升级 |
|---|---|
| D058「multi-constraint MMA-TL (stress/buckling alongside volume)」 | 多约束 MMA（应力 p-norm + 体积） |
| D059「target-band placement; repeated-eigenvalue」 | 目标频带放置（minimax around target） |
| D060「single generalised nsga3_density_to; many-objective IGD+」 | 泛化 NSGA driver + IGD+ 指标 |
| D061「non-Gaussian Rosenblatt (Clayton/Frank copulas)」 | Archimedean copula Rosenblatt |
| D062「simultaneous (ρ,θ) MMA」 | 同时 (ρ,θ) MMA 耦合 |
| D063「correlated system modes via system_reliability_series(ρ)」 | 相关系统模态驱动 TO |
| D064「constrained-Delaunay smooth + watertight holes」 | 平滑且水密的带孔三角化 |

## v10 八波

| Wave | 主题 | 关键模块 | 关键定量锚点 | ADR |
|------|------|----------|--------------|-----|
| KKK | 多约束 MMA（应力 p-norm + 体积） | `core/nonlinear_simp.py` / `mma.py` | 应力 p-norm 灵敏度 vs FD + MMA 同时满足应力≤lim ∧ 体积≤vf + 收敛 | D066 |
| LLL | 目标频带放置（minimax around target） | `core/freq_response.py` | 目标带内峰值灵敏度 vs FD + 优化后目标带峰值下降 + 体积守恒 | D067 |
| MMM | 泛化 NSGA driver + IGD+ 指标 | `core/multi_objective_to.py` | 重构后 2-obj/3-obj 前沿与重构前**逐位一致** + IGD+ vs 解析 Pareto front | D068 |
| NNN | Archimedean copula Rosenblatt | `core/reliability.py` | Clayton/Frank 条件 CDF round-trip + θ→0 退化到独立 + Kendall τ 闭式 | D069 |
| OOO | 同时 (ρ,θ) MMA 耦合 | `core/thermal_simp.py` / `mma.py` | 同时 MMA ≤ 交替最小化（GGG）+ 灵敏度合并正确 + 收敛 | D070 |
| PPP | 相关系统模态驱动 TO | `core/rbto.py` | 相关 vs 独立系统 β 方向正确（正相关降失效）+ 用 bivariate CDF + 退化到独立 | D071 |
| QQQ | 平滑且水密的带孔三角化 | `core/stl_export.py` | 环形孔**平滑轮廓**水密=True + 面积≈平滑轮廓（外−内）+ 每边恰 2 三角 | D072 |
| RRR | v10 收口 | demos + tutorial §20 + architecture §20 + rubric | rubric ≥99；pytest gate green；v4-v9 无回归 | D073 |

每波按 v9 节奏：模块 + 测试（定量解析锚点，非 qualitative trend）+ fingerprint（如适用）
+ ADR + tutorial §20.x + adjacent-regression check + 1 commit。

## 完成度门控

v10 完成 = `python scripts/test_agent.py --rubric v10` 报告：

- [ ] v10 rubric total ≥ 99 / 100
- [ ] v9/v8/v7/v6/v5/v4 regression = False（各 = 100）
- [ ] **pytest gate green**（D033 — 0 failed / 0 errors）
- [ ] 全红线保持

## 进度（wave 勾选）

- [x] KKK — 多约束 MMA（应力 p-norm + 体积）
- [x] LLL — 目标频带放置（minimax around target）
- [x] MMM — 泛化 NSGA driver + IGD+ 指标
- [x] NNN — Archimedean copula Rosenblatt
- [x] OOO — 同时 (ρ,θ) MMA 耦合
- [ ] PPP — 相关系统模态驱动 TO
- [ ] QQQ — 平滑且水密的带孔三角化
- [ ] RRR — v10 收口（rubric ≥ 99）

> 注：v10 需在 `docs/quality-rubric-v10.md` + `scripts/test_agent.py` 的 `CHECKS_V10`
> 落地评分项后才能 `--rubric v10` 打分（与 v9 同构：6 section / 100 分 / D033 gate /
> v4-v9 回归门）。这是 Wave KKK 实施前的前置脚手架步骤。
