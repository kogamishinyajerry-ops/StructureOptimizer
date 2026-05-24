# v7 蓝图 — production drivers & field-level fidelity（把 v6 的严格正向物理变成设计驱动器）

> Status: planned. Charter (standing, user 2026-05-24):
> "瞄准蓝图迭代到 ≥99/100，绝对诚实评分，wave 自动推进；完成一个里程碑继续下一个。"
> v6 完成（rubric 100/100，8 wave EE-LL）后开 v7。

## 永久红线（v1-v6 已建立 · v7 不可破）

- 无 CAD / GUI / cloud / full-3D / commercial 求解器 / LLM
- 运行时 mandatory deps 仍仅 `numpy`（scipy / pyamg / meshio 全部 optional）
- 本地可跑 — `pytest -q` 不依赖网络
- 失败仍单行 stderr + 状态码字符串
- 自我贬低优先于自我吹嘘

v7 在以上约束**内**把精度/能力推进，不在以外做任何让步。所有"3D-like"措辞仍是 2.5D。

## v7 主题

v6 把 7 处简化公式升级为**严格的正向求解器**。v7 = 把这些正向求解器**接入优化驱动器**，
并把 v6 仍残留的"全局/均匀"简化**提升到逐单元场级保真**。每个 wave 都源自 v6（或 v5）
ADR 明列的 "Reopening criteria"——延续 v6 的纪律：**每 wave 可追溯到一条已记录的
reopening criterion，不是数字追逐**。

| 来源 ADR reopening criterion | v7 升级 |
|---|---|
| D038「reliability-based TO driver」 | FORM 接入 SIMP → RBTO |
| D036「per-element fibre angle 场」+「anisotropic thermal TO sensitivity」 | 逐单元各向异性热场 + 各向异性热 TO |
| D034（完整 TL 正向 → 驱动器） | 几何非线性 TO（TL 伴随灵敏度） |
| D038「Nataf/Rosenblatt」 | 相关 / 非高斯不确定性变换 |
| D037 + D023「proxy → density field」 | NSGA-III 直接优化密度场 |
| D035（阻尼频响正向 → 驱动器） | 阻尼频响 TO（最小化动柔度） |
| D039「ear-clipping + holes」 | 通用多边形 STL 三角化 + 孔洞 |

## v7 八波

| Wave | 主题 | 关键模块 | 关键定量锚点 | ADR |
|------|------|----------|--------------|-----|
| MM | Reliability-based TO（FORM→SIMP 驱动） | `core/rbto.py` (+reliability) | 线性极限态下 RBTO 收敛到解析 β_target；可靠性拓扑 vs 确定性拓扑差异可量化 | D042 |
| NN | 逐单元各向异性热场 + 各向异性热 TO | `core/thermal.py` / `thermal_simp.py` (+per-elem) | per-element fibre-angle 场 patch test；各向异性热 SIMP 灵敏度 vs 中心差分 | D043 |
| OO | 几何非线性 TO（完整 TL 伴随灵敏度） | `core/nonlinear_simp.py` (+TL adjoint) | TL 伴随灵敏度 vs FD（≤1e-5）；大变形拓扑 vs 线性拓扑差异 | D044 |
| PP | 相关 / 非高斯不确定性（Nataf 变换） | `core/reliability.py` (+nataf) | 相关高斯→独立标准正态映射正确；已知相关线性极限态 β 解析 | D045 |
| QQ | NSGA-III 直接优化密度场（非 proxy） | `core/multi_objective_to.py` (+nsga3) | 真密度场 2-3 目标 Pareto；超体积随代单调；端点匹配单目标 SIMP | D046 |
| RR | 阻尼频响 TO（最小化动柔度） | `core/freq_response.py` (+dynamic TO) | 阻尼动柔度灵敏度 vs FD；共振规避拓扑（峰值幅值下降） | D047 |
| SS | Ear-clipping 通用多边形 STL + 孔洞 | `core/stl_export.py` (+earclip) | 非 star-convex 截面水密；带孔 even-odd；三角化面积守恒 ≤1e-12 | D048 |
| TT | v7 收口 | demos + tutorial §17 + architecture §17 + rubric | rubric ≥99；pytest gate green；v4/v5/v6 无回归 | D049 |

每波按 v6 节奏：模块 + 测试（定量解析锚点，非 qualitative trend）+ fingerprint（如适用）
+ ADR + tutorial §17.x + adjacent-regression check + 1 commit。

## 完成度门控

v7 完成 = `python scripts/test_agent.py --rubric v7` 报告：

- [x] v7 rubric total ≥ 99 / 100 — **100/100**
- [x] v6 regression = False（v6 = 100）
- [x] v5 regression = False（v5 = 100）
- [x] v4 regression = False（v4 = 100）
- [x] **pytest gate green**（D033 — 0 failed / 0 errors）
- [x] 全红线保持

## 进度（wave 勾选）

- [x] MM — Reliability-based TO（FORM→SIMP）（D042 · 9 tests green · 线性极限态 FORM β==解析闭式 + 高 β_target 需更多材料）
- [x] NN — 逐单元各向异性热场 + 各向异性热 TO（D043 · 5 tests green · uniform 场==global tensor 1e-12 + 各向异性灵敏度 vs 中心差分 1e-4）
- [x] OO — 几何非线性 TO（TL 伴随）（D044 · 4 tests green · TL 伴随灵敏度 vs 中心差分 rel 2e-4 + 非线性柔度≠线性 + 自伴随线性极限）
- [x] PP — 相关 / 非高斯不确定性（Nataf）（D045 · 8 tests green · 相关高斯线性极限态 β==(a₀−aᵀμ)/√(aᵀΣa) rel 1e-6 + 对数正态等效相关闭式 1e-12 + Φ⁻¹ 1e-10）
- [x] QQ — NSGA-III 直接优化密度场（D046 · 6 tests green · 2D 超体积精确解析 + 累积存档超体积单调 + 真密度场柔度/体积 Pareto + 梯度自由前沿不支配梯度 SIMP）
- [x] RR — 阻尼频响 TO（D047 · 5 tests green · 动柔度自伴随灵敏度 vs 中心差分 rel 1e-5 + 无阻尼退化实数 + 体积守恒下降使峰值幅值 2.60→0.97）
- [x] SS — Ear-clipping 通用多边形 STL + 孔洞（D048 · 8 tests green · 凹/非 star-convex 面积守恒 1e-12 + 双孔 even-odd 72−8−4 + 挤出水密 + 形心扇区在 L 形给错 11 vs 真 7）
- [x] TT — v7 收口（rubric 100/100 · D049 · demos + fingerprints 35 + CI + property 40 · v4/v5/v6 无回归 + pytest gate green）

> 注：v7 需在 `docs/quality-rubric-v7.md` + `scripts/test_agent.py` 的 `CHECKS_V7` 落地
> 评分项后才能 `--rubric v7` 打分（与 v6 同构：6 section / 100 分 / D033 gate / v4-v6 回归门）。
> 这是 Wave MM 实施前的前置脚手架步骤。
