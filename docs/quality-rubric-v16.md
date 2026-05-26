# v16 质量评分卡 — deep embedding & exact generalization（100 分 · 6 section）

> 与 v4-v15 同构：`python scripts/test_agent.py --rubric v16 [--strict]` 机械打分，写
> `tests/v16_scorecard.json`。`--strict` = total < 99 或任一回归（v4-v15 / D033 pytest-green）则 exit 1。
> 每个 wave 追溯一条 v15（D106-D112）/ 更早 ADR 的 "Reopening criteria"。
> **v16 特有**：embedding wave 必证 opt-in 默认逐位复现 + 开启改变语义；exactness/generalization
> wave 必证退化精确复现旧量 + 一般情形给出旧量给不出的新正确量（对独立参考定量吻合）。

## §1 deep embedding into production estimators/optimizers（24 分）

| 项 | 分 | 判据 |
|---|---|---|
| 1.1 anti-symmetric 排序约束嵌入 optimize_stacking_sequence | 8 | `core/orthotropic_simp.py` 排序优化器支持 `bending_shear_decoupled` + 测试：True ⟹ 优化排序 D₁₆=D₂₆=0 + 约束**改变**排序 + **False 逐位复现 D106/D095** |
| 1.2 CBC 确定性向量接入 genz_mvn_cdf（cbc lattice）| 8 | `core/reliability.py` Genz MVN CDF 支持 CBC 确定性 lattice + 报告 e(z) + 测试：确定性(无 seed)复现 + 默认随机路径不回归 D086 |
| 1.3 mixture-copula 系统可靠性接入一般非正态边缘 | 8 | `core/reliability.py` 系统 P_f 接 per-mode 一般边缘（`copula_marginals`）+ 测试：正态边缘退化复现 D111 + 非正态改变 P_f（vs 独立参考）|

## §2 exact generalization — QMC（15 分）

| 项 | 分 | 判据 |
|---|---|---|
| 2.1 α≥2 高阶光滑加权 Korobov 最坏情况误差 | 8 | `core/reliability.py` `korobov_worst_case_error` 支持 `smoothness`（B_{2α} 核）+ 测试：α=1 byte-exact 复现 D112 + α=2 更快衰减（同 N e 更小）+ 双形式一致 |
| 2.2 fast-CBC（FFT）或诚实 defer | 7 | `core/reliability.py` `fast_cbc` FFT 构造 == naive-CBC z（同贪心结果）+ O(dNlogN) + 测试（**或诚实 defer**：probe 证据 + D112/D120 先例）|

## §3 exact multipliers & general system reliability（16 分）

| 项 | 分 | 判据 |
|---|---|---|
| 3.1 peak-binding 精确 KKT 乘子（或诚实 defer）| 8 | `core/freq_response.py` `exact_multiplier`（梯度 stationarity 解精确 λ，替代 J/J_ref proxy）+ 测试：active regime λ>0 + 退化吻合 D109 proxy 符号（**或诚实 defer**：probe + D109 先例，8 分给"可证 defer"或"成功精确 λ"二者之一）|
| 3.2 copula 并联/一般系统可靠性 | 8 | `core/reliability.py` `parallel_copula`（system fails iff all fail / k-out-of-n）+ 测试：独立退化 ∏ + parallel ≤ series + 退化复现 D111 |

## §4 quality gates（20 分）

| 项 | 分 | 判据 |
|---|---|---|
| 4.1 Test count ≥ 1290 | 4 | `pytest --collect-only` |
| 4.2 Core coverage ≥ 95%（含 v16）| 4 | `pytest --cov=structure_optimizer/core` |
| 4.3 Property tests ≥ 65 | 3 | `^def test_property_` count |
| 4.4 Mutation kill rate ≥ 75% | 3 | `tests/mutation_report.json` |
| 4.5 Fingerprint DB ≥ 80 | 2 | `tests/fingerprints/*.json` count |
| 4.6 pytest gate green (D033) | 2 | D033 全绿门机制存在 |
| 4.7 v16 rubric 写入 agent + CI | 2 | `CHECKS_V16` + `.github/workflows/test.yml` |

## §5 demos（10 分）

| 项 | 分 | 判据 |
|---|---|---|
| 5.1 anti-symmetry-embed / cbc-lattice demo | 3 | `scripts/v16_demos.py` |
| 5.2 general-marginals / parallel-system demo | 3 | 同上 |
| 5.3 alpha2-korobov / fast-cbc demo | 2 | 同上 |
| 5.4 exact-kkt-multiplier demo | 2 | 同上 |

## §6 docs（15 分）

| 项 | 分 | 判据 |
|---|---|---|
| 6.1 blueprint-v16 ≥6 wave ticks | 3 | `docs/blueprint-v16.md` |
| 6.2 tutorial v16 ≥4 §26.x sections | 3 | `docs/tutorial.md` |
| 6.3 architecture v16 section | 3 | `docs/architecture.md` `## 26.` + "embedding" |
| 6.4 ADRs D114+ ≥ 7 | 3 | `docs/decisions/D11[4-9]*.md` + `docs/decisions/D12*.md` |
| 6.5 v16 anchors documented | 3 | 测试里 v16 锚点关键词 ≥3 |

## 完成度门控

v16 release-ready = total ≥ 99/100 AND v4-v15 各 100（regression=False）AND D033 pytest gate green AND 全红线保持。

## v16 特有纪律（deep embedding + exact generalization 铁律）

- **embedding wave**（接入既有生产函数）：(a) opt-in 默认逐位复现原行为；(b) 开启时结果改变且满足新语义。
- **exactness/generalization wave**：(a) 退化到旧受限情形精确复现旧量；(b) 一般情形给出旧量给不出的新正确量，且对独立参考（central-FD / 闭式 / 高 N 数值）定量吻合。
- 叠加在"定量解析锚点（非 qualitative trend）"之上，不替代。
- DDDDDDDD 精确 MMA 对偶 λ 与 GGGGGGGG fast-CBC FFT：若不成立 = **诚实 defer**（probe 证据 + 不伪造），该项 8/7 分给"可证 defer 条件 + 探针"或"成功成立"二者之一。
