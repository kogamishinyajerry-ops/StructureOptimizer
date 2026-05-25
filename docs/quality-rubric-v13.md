# v13 质量评分卡 — robust drivers & validated geometry（100 分 · 6 section）

> 与 v4-v12 同构：`python scripts/test_agent.py --rubric v13 [--strict]` 机械打分，写
> `tests/v13_scorecard.json`。`--strict` = total < 99 或任一回归（v4-v12 / D033 pytest-green）则 exit 1。
> 每个 wave 追溯一条 v12（D082-D088）ADR 的 "Reopening criteria"。

## §1 robust drivers（24 分）

| 项 | 分 | 判据 |
|---|---|---|
| 1.1 屈曲约束 MMA（λ_crit ≥ λ_safety）| 8 | `core/buckling.py` 有屈曲约束驱动 + 测试：三约束 MMA（compliance↓ + volume≤vf + λ_crit≥λ_safety），用 D082 设计级灵敏度 |
| 1.2 峰约束驱动产生不同设计 | 8 | `core/freq_response.py` 有 peak-binding 驱动 + 测试：min dynamic compliance @ ω_op s.t. tracked-peak≤limit，in-loop vs fixed **设计可测不同** |
| 1.3 extent 指标 + range-adaptive ρ | 8 | `core/multi_objective_to.py` 有 extent/spread 指标 + 尺度自适应 ρ + 测试 |

## §2 robust reliability（16 分）

| 项 | 分 | 判据 |
|---|---|---|
| 2.1 d 维交换 Gumbel copula | 8 | `core/reliability.py` 有 d 维 Gumbel + 测试：闭式条件 CDF round-trip + Kendall τ=1−1/θ + 退化双变量 |
| 2.2 Genz 变量重排序 | 8 | `core/reliability.py` 有积分范围宽度重排 + 测试：同值更快收敛（vs 未排）+ 排列不变正确性 |

## §3 validated geometry（15 分）

| 项 | 分 | 判据 |
|---|---|---|
| 3.1 铺层顺序优化 | 8 | `core/orthotropic_simp.py` 有 stacking-sequence 优化 + 测试：离散 ply 角最小化耦合 B / 最大化弯曲 D + 对称约束保 B=0 |
| 3.2 Ruppert 质量细化（Steiner 插点）| 7 | `core/stl_export.py` 有 Ruppert 细化 + 测试：circumcenter 插点把最小角抬到 ≥ 阈值（Lawson 做不到）+ 仍水密 |

## §4 quality gates（20 分）

| 项 | 分 | 判据 |
|---|---|---|
| 4.1 Test count ≥ 1140 | 4 | `pytest --collect-only` |
| 4.2 Core coverage ≥ 95%（含 v13）| 4 | `pytest --cov=structure_optimizer/core` |
| 4.3 Property tests ≥ 56 | 3 | `^def test_property_` count |
| 4.4 Mutation kill rate ≥ 75% | 3 | `tests/mutation_report.json` |
| 4.5 Fingerprint DB ≥ 65 | 2 | `tests/fingerprints/*.json` count |
| 4.6 pytest gate green (D033) | 2 | D033 全绿门机制存在 |
| 4.7 v13 rubric 写入 agent + CI | 2 | `CHECKS_V13` + `.github/workflows/test.yml` |

## §5 demos（10 分）

| 项 | 分 | 判据 |
|---|---|---|
| 5.1 屈曲约束 / 峰约束 demo | 3 | `scripts/v13_demos.py` |
| 5.2 extent / range-adaptive demo | 3 | 同上 |
| 5.3 d-Gumbel / Genz-reorder demo | 2 | 同上 |
| 5.4 铺层 / Ruppert demo | 2 | 同上 |

## §6 docs（15 分）

| 项 | 分 | 判据 |
|---|---|---|
| 6.1 blueprint-v13 ≥6 wave ticks | 3 | `docs/blueprint-v13.md` |
| 6.2 tutorial v13 ≥4 §23.x sections | 3 | `docs/tutorial.md` |
| 6.3 architecture v13 section | 3 | `docs/architecture.md` `## 23.` + "robust" |
| 6.4 ADRs D090+ ≥ 7 | 3 | `docs/decisions/D09[0-7]*.md` |
| 6.5 v13 anchors documented | 3 | 测试里 v13 锚点关键词 ≥3 |

## 完成度门控

v13 release-ready = total ≥ 99/100 AND v4-v12 各 100（regression=False）AND D033 pytest gate green AND 全红线保持。
