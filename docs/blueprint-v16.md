# v16 蓝图 — deep embedding & exact generalization: 把 v15 构造/验证原语接入生产优化器/估计器更深一层 + 把 proxy 升级为精确量

> Status: opening (design SSOT). Charter (standing, user 2026-05-24):
> "瞄准蓝图迭代到 ≥99/100，绝对诚实评分，wave 自动推进；完成一个里程碑继续下一个。"
> v15 完成（rubric 100/100，8 wave AAAAAAA-HHHHHHH，scorecard 2f27e41，pytest 1268 passed）后开 v16。

## 永久红线（v1-v15 已建立 · v16 不可破）

- 无 CAD / GUI / cloud / full-3D / commercial 求解器 / LLM
- 运行时 mandatory deps 仍仅 `numpy`（scipy / pyamg / meshio 全部 optional）
- 本地可跑 — `pytest -q` 不依赖网络
- 失败仍单行 stderr + 状态码字符串
- 自我贬低优先于自我吹嘘

v16 在以上约束**内**把能力推进，不在以外做任何让步。所有"3D-like"措辞仍是 2.5D。

## v16 主题 — 与 v15 的关键区别

v15 把 v14 浅集成原语接入生产优化器/写出器作**真绑定约束**，并关闭 v14 的诚实 defer。但 v15 自身留下两类残口：(a) 一批仍是 **construction+verification 未接优化器**的原语（D110 anti-symmetric 未接 `optimize_stacking_sequence`；D112 CBC 未接 `genz_mvn_cdf_lattice`）；(b) 一批用了 **proxy / 受限假设**（D109 `active_multiplier` 是 J/J_ref−1 相对牺牲 proxy 非精确 MMA 对偶 λ；D111 仅 CDF 级 + 正态边缘 + 仅 series；D112 仅 α=1 乘积权重 + naive O(dN²) CBC）。

**v16 = deep embedding & exact generalization**：(a) 把 v15 standalone 原语**再深一层接入生产估计器/优化器**，(b) 把 **proxy 升级为精确量、把受限假设泛化**。每条 wave 都追溯一条 D106-D112 reopening criterion。

> **本里程碑的核心纪律**（继承 v14 byte-exact 铁律 + v15 约束真绑定铁律）：
> - **embedding wave**（接入既有生产函数）：必证 (a) opt-in 默认**逐位复现**原行为 (b) 开启时结果**改变**且满足新语义。
> - **exactness/generalization wave**（把 proxy 升精确 / 受限升一般）：必证 (a) 退化到旧受限情形**精确复现**旧量 (b) 一般情形给出旧量给不出的**新正确量**，且对独立参考（central-FD / 闭式 / 高 N 数值）定量吻合。
> - **诚实 defer 仍是一等公民**（沿用 D074/D091/D104/D112 先例）——尤其 GGGGGGGG 的 fast-CBC FFT 与 DDDDDDDD 的精确 MMA 对偶 λ，若不成立则诚实 defer 带探针证据，绝不伪造。

每个 wave 仍按节奏：模块 + 测试（定量解析锚点 + backward-compat 逐位复现 + 泛化/精确证据）+ ADR + blueprint tick + tutorial §26.x + 相邻回归 + 1 commit。

| 来源 ADR reopening criterion | v16 升级 |
|---|---|
| D110「embed anti-symmetry into optimize_stacking_sequence (bending_shear_decoupled flag)」 | anti-symmetric **排序约束**嵌入排序优化器（搜索限于 anti-symmetric 排列 ⟹ D₁₆=D₂₆=0） |
| D111「general non-normal marginals Rosenblatt」 | mixture-copula 系统可靠性接入**一般非正态边缘**（Weibull/Gumbel/lognormal per-mode） |
| D112「wire CBC z into genz_mvn_cdf_lattice」 | CBC 确定性生成向量接入 Genz lattice 估计器（opt-in，报告 e(z) 确定性界） |
| D109「strictly KKT-binding with exact MMA dual λ (not J/J_ref proxy)」 | peak-binding **精确 KKT 乘子**（梯度 stationarity 解 λ，替代相对牺牲 proxy）或诚实 defer |
| D112「higher smoothness α≥2 (B_{2α} kernel)」 | α≥2 高阶光滑加权 Korobov 最坏情况误差（B_{2α} 核 ⟹ 更快衰减） |
| D111「parallel / general system events beyond series safety」 | copula **并联/一般系统**可靠性（system fails iff all fail / k-out-of-n） |
| D112「fast-CBC (FFT, O(d·N·log N))」 | fast-CBC（Nuyens–Cools FFT）= naive-CBC 同结果但快 **或诚实 defer** |

## v16 八波

| Wave | 主题 | 关键模块 | 关键定量锚点 | ADR |
|------|------|----------|--------------|-----|
| AAAAAAAA | anti-symmetric 排序约束嵌入 optimize_stacking_sequence | `core/orthotropic_simp.py` | bending_shear_decoupled=True ⟹ 优化排序 D₁₆=D₂₆=0 + 约束**改变**排序 + =False byte-exact 复现 D106/D095 | D114 |
| BBBBBBBB | mixture-copula 系统可靠性接入一般非正态边缘 | `core/reliability.py` | 一般边缘 P_f 接入 + 正态边缘退化 byte-exact 复现 D111 + 非正态改变 P_f（vs 独立参考） | D115 |
| CCCCCCCC | CBC 确定性向量接入 genz_mvn_cdf_lattice | `core/reliability.py` | opt-in CBC z + 报告 e(z) 确定性界 + 默认(随机 Korobov)byte-exact 复现 D086 | D116 |
| DDDDDDDD | peak-binding 精确 KKT 乘子（或诚实 defer） | `core/freq_response.py` | 梯度 stationarity 解精确 λ>0 + 退化吻合 D109 proxy 符号 **或诚实 defer 见 D109/D104 先例** | D117 |
| EEEEEEEE | α≥2 高阶光滑加权 Korobov 最坏情况误差 | `core/reliability.py` | B_{2α} 核 ⟹ α=1 byte-exact 复现 D112 + α=2 更快衰减（同 N e 更小）+ 双形式一致 | D118 |
| FFFFFFFF | copula 并联/一般系统可靠性 | `core/reliability.py` | 并联 P_f=C̄(survival) / k-out-of-n + 独立退化 ∏ + parallel ≤ series + 退化复现 D111 | D119 |
| GGGGGGGG | fast-CBC（FFT）或诚实 defer | `core/reliability.py` | fast-CBC z == naive-CBC z（同贪心结果）+ O(dNlogN) 加速 **或诚实 defer** | D120 |
| HHHHHHHH | v16 收口 | demos + tutorial §26 + architecture §26 + rubric | rubric ≥99；pytest gate green；v4-v15 无回归 | D121 |

## 完成度门控

v16 完成 = `python scripts/test_agent.py --rubric v16` 报告：

- [ ] v16 rubric total ≥ 99 / 100
- [ ] v15/v14/.../v4 regression = False（各 = 100）
- [ ] **pytest gate green**（D033 — 0 failed / 0 errors）
- [ ] 全红线保持

## 进度（wave 勾选）

- [x] AAAAAAAA — anti-symmetric 排序约束嵌入 optimize_stacking_sequence（bending_shear_decoupled 参数；输入当半层 ⟹ rearrangement 排序后建 [half,−reversed(half)] ⟹ 优化输出 D₁₆=D₂₆=0 + A₁₆=A₂₆=0；Q̄₁₁ 偶 ⟹ rearrangement 仍 anti-symmetric 排序闭式全局 max_bending；绑定 [plain 同输入 D₁₆≠0]；=False 逐位复现 D095/D106；与 symmetric/balanced 互斥；诚实：仅 max_bending 闭式、trade B₁₆≠0、min_coupling 搜索留 reopening；D114）
- [x] BBBBBBBB — mixture-copula 一般非正态边缘（system_reliability_series_copula_marginals：u_k=F_k(x_k)=Φ(Marginal.to_standard_normal(x_k)) per-mode 任意边缘[normal/lognormal/weibull/gumbel]+copula 耦合；正态(0,1)+β 逐位复现 D098[normal.to_standard_normal(β)=β 无 round-trip]；独立 copula ⟹ 1−∏F_k 对闭式 1e-10；非正态改变 P_f；copula 仍绑定；诚实：Sklar 分离非 Nataf 物理联合 Rosenblatt、CDF 级 series、仅 4 边缘；D115）
- [x] CCCCCCCC — CBC 向量接入 genz_mvn_cdf（genz_mvn_cdf_cbc + GenzCBCResult：CBC 生成向量 + 单不移位 lattice ⟹ 无 seed 逐位可复现 + 报告确定性 e(z) 证书；m=1 精确；收敛到 GH 参考[N≈2039 abs<5e-4]；z==cbc_korobov + e(z)≤Korobov；e(z) 随 N 降；纯新增 D086/D078 不动；诚实：e(z) 证规则质量非本被积函数紧界、单不移位无统计误差、plain Cholesky；D116）
- [x] DDDDDDDD — peak-binding 精确 KKT 影子价乘子（peak_binding_exact_multiplier：λ=−dJ*/d(limit) 包络定理精确 Lagrange 乘子，升级 D109 J/J_ref proxy；对可微 J* 精确[线性精确/否则 O(δ²)]；**探针**：active 0.08·init λ=+0.73 可靠，inactive 0.40·init 真 λ=0 但 MMA regrid path-noise J* 摆动 40%>信号 ⟹ **cross-regime 稳定 λ 诚实 defer**[D074/D091 先例]，D109 proxy 保留为指示器；6 fast 锚点[A/L 闭式还原/线性精确/inactive λ=0/active λ>0/FD 收敛/guards]+1 --run-slow 生产 active λ>0；D117）
- [ ] EEEEEEEE — α≥2 高阶光滑 Korobov 最坏情况误差
- [ ] FFFFFFFF — copula 并联/一般系统可靠性
- [ ] GGGGGGGG — fast-CBC FFT（或诚实 defer）
- [ ] HHHHHHHH — v16 收口（rubric ≥ 99）

> 注：v16 需在 `docs/quality-rubric-v16.md` + `scripts/test_agent.py` 的 `CHECKS_V16`
> 落地评分项后才能 `--rubric v16` 打分（与 v15 同构：6 section / 100 分 / D033 gate /
> v4-v15 回归门）。本 blueprint + rubric 是 scaffold 前置设计 SSOT。
>
> **v16 特有提醒**：embedding wave 必证 opt-in 默认逐位复现；exactness wave 必证退化精确
> 复现旧量。`--rubric v16 --strict` 预计比 v15 ~6h 更久（回归链增至 v4-v15 共 12 里程碑全量
> coverage pass）——**用 harness run_in_background:true 跑（别 nohup &）**；别误杀轮替的
> `pytest --cov` 子进程。
