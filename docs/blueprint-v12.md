# v12 蓝图 — design-grade & adaptive: 设计级屈曲 + 循环内自适应 + 增广指标 + 分层 copula + 点阵积分 + 周期感知几何

> Status: in progress. Charter (standing, user 2026-05-24):
> "瞄准蓝图迭代到 ≥99/100，绝对诚实评分，wave 自动推进；完成一个里程碑继续下一个。"
> v11 完成（rubric 100/100，8 wave SSS-ZZZ，commit 92ec3e9）后开 v12。

## 永久红线（v1-v11 已建立 · v12 不可破）

- 无 CAD / GUI / cloud / full-3D / commercial 求解器 / LLM
- 运行时 mandatory deps 仍仅 `numpy`（scipy / pyamg / meshio 全部 optional）
- 本地可跑 — `pytest -q` 不依赖网络
- 失败仍单行 stderr + 状态码字符串
- 自我贬低优先于自我吹嘘

v12 在以上约束**内**把能力推进，不在以外做任何让步。所有"3D-like"措辞仍是 2.5D。

## v12 主题

v11 把 driver 升到精确 + 鲁棒，但留下若干 honestly-recorded 限制：**屈曲驱动 deferred（分析级灵敏度
反向）/ 频带采样循环外固定 / R2 仅收敛无多样性 / copula 仅交换 Clayton / Genz 朴素 MC 无误差界 /
fibre 连续性非周期感知 / CDT 无 flip 约束恢复**。v12 = **设计级 + 自适应（design-grade & adaptive）**：
每个 wave 追溯到一条 v11（或更早）ADR 明列的 "Reopening criteria"——延续纪律：**每 wave 可追溯到一条已
记录的 reopening criterion，不是数字追逐**，并在做不到时**诚实 defer 而非伪造**（沿用 D074 屈曲先例）。

| 来源 ADR reopening criterion | v12 升级 |
|---|---|
| D074「design-grade buckling sensitivity (∂u/∂ρ + void-mode relaxation)」 | 设计级屈曲灵敏度 → 屈曲约束/驱动 TO |
| D075「in-loop adaptive re-gridding」 | 循环内自适应频带重采样 |
| D076「augmented Tchebycheff R2 + diversity indicator」 | 增广 Tchebycheff R2 + 多样性/spacing 指标 |
| D077「nested / hierarchical & non-Clayton d-dim copulas」 | 分层 Archimedean copula（per-cluster θ）|
| D078「randomised-lattice (Korobov) Genz with error bounds」 | Korobov 点阵 Genz + 报告标准误 |
| D079「period-aware fibre continuity + laminates」 | 周期感知 fibre 连续性（sin²Δθ）+ 层合 |
| D080「flip-based CDT constraint recovery + quality refinement」 | flip 约束恢复 CDT + 质量细化 |

## v12 八波

| Wave | 主题 | 关键模块 | 关键定量锚点 | ADR |
|------|------|----------|--------------|-----|
| AAAA | 设计级屈曲灵敏度（∂u/∂ρ adjoint + void-mode relaxation）| `core/buckling.py` | 完整伴随 dλ/dρ vs central-FD ≤1e-3（含 ∂u/∂ρ 项）+ void-mode 抑制 + 定容 ascent 升 λ_crit（entry condition）| D082 |
| BBBB | 循环内自适应频带重采样 | `core/freq_response.py` | 循环内每步 re-grid 跟踪移动共振 + 峰约束收敛 vs 固定网格 | D083 |
| CCCC | 增广 Tchebycheff R2 + 多样性指标 | `core/multi_objective_to.py` | 增广 R2 闭式 + spacing/diversity 指标解析 + 退化到纯 R2 | D084 |
| DDDD | 分层 Archimedean copula（per-cluster θ）| `core/reliability.py` | 嵌套生成元条件 CDF round-trip + per-cluster Kendall τ + 退化到交换 | D085 |
| EEEE | Korobov 点阵 Genz + 误差界 | `core/reliability.py` | 点阵 Genz vs 朴素 MC 同值更快收敛 + 报告标准误 + 退化到精确 Φ₂ | D086 |
| FFFF | 周期感知 fibre 连续性（sin²Δθ）+ 层合 | `core/orthotropic_simp.py` | 周期感知度量 ±89° 不误罚 + 层合 [A,B,D] + 灵敏度 vs FD | D087 |
| GGGG | flip 约束恢复 CDT + 质量细化 | `core/stl_export.py` | flip 恢复非凸/稀疏边界水密（不报错）+ 最小角细化 + 仍水密 | D088 |
| HHHH | v12 收口 | demos + tutorial §22 + architecture §22 + rubric | rubric ≥99；pytest gate green；v4-v11 无回归 | D089 |

每波按 v11 节奏：模块 + 测试（定量解析锚点，非 qualitative trend）+ fingerprint（如适用）
+ ADR + tutorial §22.x + adjacent-regression check + 1 commit。**屈曲 entry condition**：AAAA 先
探针验证设计级灵敏度能让定容 ascent 升 λ_crit（D074 设的 reopening 闸）；若仍不能则诚实 defer，不伪造。

## 完成度门控

v12 完成 = `python scripts/test_agent.py --rubric v12` 报告：

- [ ] v12 rubric total ≥ 99 / 100
- [ ] v11/v10/v9/v8/v7/v6/v5/v4 regression = False（各 = 100）
- [ ] **pytest gate green**（D033 — 0 failed / 0 errors）
- [ ] 全红线保持

## 进度（wave 勾选）

- [x] AAAA — 设计级屈曲灵敏度（∂u/∂ρ + void-mode relaxation）
- [x] BBBB — 循环内自适应频带重采样
- [x] CCCC — 增广 Tchebycheff R2 + 多样性指标
- [x] DDDD — 分层 Archimedean copula（per-cluster θ）
- [ ] EEEE — Korobov 点阵 Genz + 误差界
- [ ] FFFF — 周期感知 fibre 连续性 + 层合
- [ ] GGGG — flip 约束恢复 CDT + 质量细化
- [ ] HHHH — v12 收口（rubric ≥ 99）

> 注：v12 需在 `docs/quality-rubric-v12.md` + `scripts/test_agent.py` 的 `CHECKS_V12`
> 落地评分项后才能 `--rubric v12` 打分（与 v11 同构：6 section / 100 分 / D033 gate /
> v4-v11 回归门）。这是 Wave AAAA 实施前的前置脚手架步骤。
