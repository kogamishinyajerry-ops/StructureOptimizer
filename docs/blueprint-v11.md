# v11 蓝图 — exact & robust: 应力奇异性 + 一般 copula 维度 + 精确系统积分 + 约束 Delaunay

> Status: in progress. Charter (standing, user 2026-05-24):
> "瞄准蓝图迭代到 ≥99/100，绝对诚实评分，wave 自动推进；完成一个里程碑继续下一个。"
> v10 完成（rubric 100/100，8 wave KKK-RRR）后开 v11。

## 永久红线（v1-v10 已建立 · v11 不可破）

- 无 CAD / GUI / cloud / full-3D / commercial 求解器 / LLM
- 运行时 mandatory deps 仍仅 `numpy`（scipy / pyamg / meshio 全部 optional）
- 本地可跑 — `pytest -q` 不依赖网络
- 失败仍单行 stderr + 状态码字符串
- 自我贬低优先于自我吹嘘

v11 在以上约束**内**把能力推进，不在以外做任何让步。所有"3D-like"措辞仍是 2.5D。

## v11 主题

v10 把 driver 升到约束丰富 + 可制造，但多处仍是**未处理应力奇异性 / 仅双变量 copula / 界中点近似 /
单孔几何 / 一阶投影梯度**。v11 = **精确化 + 鲁棒化**：解应力奇异性（SIMP-松弛/qp-stress）+ 屈曲约束、
一般维度 copula、精确多元系统积分、约束 Delaunay 多孔几何。每个 wave 都源自 v10（或更早）ADR 明列的
"Reopening criteria"——延续纪律：**每 wave 可追溯到一条已记录的 reopening criterion，不是数字追逐**。

| 来源 ADR reopening criterion | v11 升级 |
|---|---|
| D066「SIMP-relaxed/qp-stress + buckling eigenvalue constraint」 | 应力奇异性松弛 + 屈曲约束多约束 MMA |
| D067「adaptive band sampling; peak-as-constraint」 | 自适应频带采样 + peak-as-constraint |
| D068「reference-free quality indicators (hypervolume-only / R2)」 | reference-free 多目标质量指标 |
| D069「d-dimensional / Gumbel copulas」 | d 维 / Gumbel Archimedean copula |
| D071「full correlation matrix; exact multivariate system P_f (Genz)」 | 全相关矩阵 + Genz 精确多元系统 P_f |
| D070「elastic simultaneous (ρ,θ) MMA; fibre-continuity」 | 弹性同时 (ρ,θ) MMA + fibre-continuity |
| D072「constrained-Delaunay multi-hole smooth+watertight」 | 约束 Delaunay 多孔平滑+水密 |

## v11 八波

| Wave | 主题 | 关键模块 | 关键定量锚点 | ADR |
|------|------|----------|--------------|-----|
| SSS | 应力奇异性松弛（qp-relaxed）| `core/stress.py` / `core/nonlinear_simp.py` | qp-relaxed 应力灵敏度 vs central-FD ≤1e-4 + 松弛消除奇异性（σ̃=ρ^q·raw）+ qp-stress 约束 MMA 双约束生效。**屈曲约束驱动 deferred**（analysis-grade `buckling_sensitivity` 忽略 ∂u/∂ρ + 无 void-mode relaxation，探针显示 ascent 反而把 λ_crit 从 20.1 拉到 8.1）→ D074 reopening | D074 |
| TTT | 自适应频带采样 + peak-as-constraint | `core/freq_response.py` | 自适应采样捕获移动峰 vs 固定采样 + peak 作约束进 MMA + 收敛 | D075 |
| UUU | reference-free 多目标质量指标 | `core/multi_objective_to.py` | hypervolume-only / R2 vs IGD+ 一致排序 + 无需参考前沿 + 单调 | D076 |
| VVV | d 维 / Gumbel Archimedean copula | `core/reliability.py` | Gumbel 条件 CDF round-trip + d 维嵌套生成元 + Kendall τ 闭式 | D077 |
| WWW | 全相关矩阵 + Genz 精确多元系统 P_f | `core/reliability.py` | Genz vs Ditlevsen 界内 + 全相关矩阵 + 退化到二元精确 | D078 |
| XXX | 弹性同时 (ρ,θ) MMA + fibre-continuity | `core/orthotropic_simp.py` | 正交各向异性弹性合并灵敏度 vs FD + fibre-continuity 约束 + 同时 ≤ 交替 | D079 |
| YYY | 约束 Delaunay 多孔平滑+水密 | `core/stl_export.py` | 多孔平滑轮廓水密=True + 面积≈外−Σ孔 + 每边恰 2 三角 | D080 |
| ZZZ | v11 收口 | demos + tutorial §21 + architecture §21 + rubric | rubric ≥99；pytest gate green；v4-v10 无回归 | D081 |

每波按 v10 节奏：模块 + 测试（定量解析锚点，非 qualitative trend）+ fingerprint（如适用）
+ ADR + tutorial §21.x + adjacent-regression check + 1 commit。

## 完成度门控

v11 完成 = `python scripts/test_agent.py --rubric v11` 报告：

- [ ] v11 rubric total ≥ 99 / 100
- [ ] v10/v9/v8/v7/v6/v5/v4 regression = False（各 = 100）
- [ ] **pytest gate green**（D033 — 0 failed / 0 errors）
- [ ] 全红线保持

## 进度（wave 勾选）

- [x] SSS — 应力奇异性松弛（qp-relaxed）；屈曲约束驱动 deferred 到 D074 reopening
- [x] TTT — 自适应频带采样 + peak-as-constraint
- [x] UUU — reference-free 多目标质量指标
- [x] VVV — d 维 / Gumbel Archimedean copula
- [x] WWW — 全相关矩阵 + Genz 精确多元系统 P_f
- [x] XXX — 弹性同时 (ρ,θ) MMA + fibre-continuity
- [x] YYY — 约束 Delaunay 多孔平滑+水密
- [ ] ZZZ — v11 收口（rubric ≥ 99）

> 注：v11 需在 `docs/quality-rubric-v11.md` + `scripts/test_agent.py` 的 `CHECKS_V11`
> 落地评分项后才能 `--rubric v11` 打分（与 v10 同构：6 section / 100 分 / D033 gate /
> v4-v10 回归门）。这是 Wave SSS 实施前的前置脚手架步骤。
