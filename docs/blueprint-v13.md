# v13 蓝图 — robust drivers & validated geometry: 屈曲约束 + 峰约束驱动 + 多样性指标 + d 维 Gumbel + 重排序点阵 + 铺层优化 + Ruppert 细化

> Status: in progress. Charter (standing, user 2026-05-24):
> "瞄准蓝图迭代到 ≥99/100，绝对诚实评分，wave 自动推进；完成一个里程碑继续下一个。"
> v12 完成（rubric 100/100，8 wave AAAA-HHHH，commit 8cbf362）后开 v13。

## 永久红线（v1-v12 已建立 · v13 不可破）

- 无 CAD / GUI / cloud / full-3D / commercial 求解器 / LLM
- 运行时 mandatory deps 仍仅 `numpy`（scipy / pyamg / meshio 全部 optional）
- 本地可跑 — `pytest -q` 不依赖网络
- 失败仍单行 stderr + 状态码字符串
- 自我贬低优先于自我吹嘘

v13 在以上约束**内**把能力推进，不在以外做任何让步。所有"3D-like"措辞仍是 2.5D。

## v13 主题

v12 把 driver 升到设计级 + 自适应，但留下若干 honestly-recorded 限制：**屈曲是 ascent 非约束 / in-loop 在刚度对齐
问题上不产生不同设计 / spacing 无 extent 配对、未接 selection / copula 只交换 Clayton（非 d 维 Gumbel）/ Genz
无变量重排 / laminate 未接铺层优化 / CDT 细化只 Lawson 无最小角下界**。v13 = **robust drivers & validated
geometry**：每个 wave 追溯一条 v12（或更早）ADR 明列的 "Reopening criteria"——延续纪律：**每 wave 可追溯到一条
已记录的 reopening criterion，不是数字追逐**，做不到时**诚实 defer 而非伪造**。

| 来源 ADR reopening criterion | v13 升级 |
|---|---|
| D082「buckling-*constrained* MMA (λ_crit ≥ λ_safety 第三不等式)」 | 屈曲约束 TO（compliance + volume + 屈曲）|
| D083「bandwidth-adaptive window（half-power）」 | 半功率带宽自适应窗口（peak-binding-不同设计 claim 诚实 defer，见 D091）|
| D084「extent/spread 指标 + range-adaptive ρ」 | 多样性 extent (Δ) 指标 + 尺度自适应 ρ |
| D085「non-Clayton d-dim copula」 | d 维交换 Gumbel copula（闭式条件 CDF）|
| D086「Genz 变量重排序 + (CBC)」 | Genz 积分范围宽度重排序（MC + lattice 共享）|
| D087「laminate 铺层顺序优化」 | 铺层顺序优化（离散 ply 角 + 对称/平衡约束）|
| D088「Ruppert 细化（Steiner 插点保最小角下界）」 | Ruppert 质量细化（circumcenter 插点）|

## v13 八波

| Wave | 主题 | 关键模块 | 关键定量锚点 | ADR |
|------|------|----------|--------------|-----|
| AAAAA | 屈曲约束 MMA（λ_crit ≥ λ_safety 第三不等式）| `core/buckling.py` | 三约束 MMA（compliance↓ + volume≤vf + λ_crit≥λ_safety）绑定到 λ_safety + 设计级灵敏度 | D090 |
| BBBBB | 半功率带宽自适应窗口 | `core/freq_response.py` | 窗口宽 = half-power 带宽（α/ω+βω）跨 sharpness 鲁棒（fixed 5% 在 ζ≈0.009 误 62% vs 自适应 ~11%）；peak-binding-不同设计诚实 defer | D091 |
| CCCCC | extent/spread 指标 + range-adaptive ρ | `core/multi_objective_to.py` | Δ-spread 闭式（两点极端 → 大）+ range-adaptive ρ 尺度不变区分 | D092 |
| DDDDD | d 维交换 Gumbel copula | `core/reliability.py` | 闭式条件 CDF round-trip + Kendall τ=1−1/θ + 退化到双变量 Gumbel | D093 |
| EEEEE | Genz 变量重排序 | `core/reliability.py` | 按积分范围宽度重排 → 同值更快收敛（vs 未排）+ 排列不变正确性 | D094 |
| FFFFF | 铺层顺序优化 | `core/orthotropic_simp.py` | 离散 ply 角优化最小化耦合 B / 最大化弯曲 D + 对称约束保 B=0 | D095 |
| GGGGG | Ruppert 质量细化（Steiner 插点）| `core/stl_export.py` | circumcenter 插点把最小角抬到 ≥ 阈值（Lawson 做不到）+ 仍水密 | D096 |
| HHHHH | v13 收口 | demos + tutorial §23 + architecture §23 + rubric | rubric ≥99；pytest gate green；v4-v12 无回归 | D097 |

每波按 v12 节奏：模块 + 测试（定量解析锚点，非 qualitative trend）+ fingerprint（如适用）
+ ADR + tutorial §23.x + adjacent-regression check + 1 commit。**做不到的诚实 defer**（沿用 D074/D085 先例）。

## 完成度门控

v13 完成 = `python scripts/test_agent.py --rubric v13` 报告：

- [ ] v13 rubric total ≥ 99 / 100
- [ ] v12/v11/v10/v9/v8/v7/v6/v5/v4 regression = False（各 = 100）
- [ ] **pytest gate green**（D033 — 0 failed / 0 errors）
- [ ] 全红线保持

## 进度（wave 勾选）

- [x] AAAAA — 屈曲约束 MMA（λ_crit ≥ λ_safety）
- [x] BBBBB — 半功率带宽自适应窗口（peak-binding-不同设计 claim defer，D091）
- [x] CCCCC — extent/spread 指标 + range-adaptive ρ（extent 与 spacing 互补：两点极端 Δ 同密集前沿，spacing 却都报 S=0；D092）
- [x] DDDDD — d 维交换 Gumbel copula（ψ^{(k)}=ψ·g_k 精确递推闭式条件 CDF + Kendall τ=1−1/θ + d=2 退化到双变量；D093）
- [x] EEEEE — Genz 变量重排序（Genz–Bretz priority ordering：固定 N=400 误差降 ~9× + 高 N 同值 + 退化到精确 equicorr 参考；D094）
- [x] FFFFF — 铺层顺序优化（max_bending = rearrangement 闭式全局最优 = brute force + symmetric ⟹ B=0 精确 + min_coupling 穷举到 0；D095）
- [x] GGGGG — Ruppert 质量细化（Steiner 插点把 14°→≥20°，Lawson 在固定顶点集做不到；仍水密；D096）
- [ ] HHHHH — v13 收口（rubric ≥ 99）

> 注：v13 需在 `docs/quality-rubric-v13.md` + `scripts/test_agent.py` 的 `CHECKS_V13`
> 落地评分项后才能 `--rubric v13` 打分（与 v12 同构：6 section / 100 分 / D033 gate /
> v4-v12 回归门）。这是 Wave AAAAA 实施前的前置脚手架步骤。
