# v12 质量评分卡 — design-grade & adaptive (100 分)

> 由 `scripts/test_agent.py --rubric v12` 机械打分，写 `tests/v12_scorecard.json`。
> 与 v4-v11 同构：6 section / 100 分 / D033 pytest-green gate（不计入 100 分，hard-fail）
> / v4·v5·v6·v7·v8·v9·v10·v11 in-process 回归门（各须保持满分）。
> 评分项是 grep-based presence + 定量测试引用：对应 wave 落地前 FAIL，落地后 PASS。

主题：把 v11 的"屈曲驱动 deferred / 频带循环外固定 / R2 仅收敛 / 交换 copula / 朴素 Genz / fibre 非
周期感知 / CDT 无 flip 恢复"升到设计级 + 自适应。每项追溯到一条 v11（或更早）ADR 的 reopening
criterion（见 blueprint-v12）。**做不到时诚实 defer，不伪造**（沿用 D074 屈曲先例）。

## §1 鲁棒约束 driver（24 分）

| 项 | 分 | PASS 条件 | 源 |
|----|----|-----------|----|
| 1.1 设计级屈曲灵敏度（∂u/∂ρ + void-mode）| 8 | `buckling.py` 完整伴随 dλ/dρ + void-mode relaxation 测试 | D074 |
| 1.2 循环内自适应频带重采样 | 8 | `freq_response.py` in-loop re-grid + 收敛测试 | D075 |
| 1.3 增广 Tchebycheff R2 + 多样性指标 | 8 | `multi_objective_to.py` 增广 R2 + spacing/diversity 测试 | D076 |

## §2 不确定性（16 分）

| 项 | 分 | PASS 条件 | 源 |
|----|----|-----------|----|
| 2.1 分层 Archimedean copula（per-cluster θ）| 8 | `reliability.py` nested/hierarchical 条件 CDF + round-trip 测试 | D077 |
| 2.2 Korobov 点阵 Genz + 误差界 | 8 | `reliability.py` lattice/korobov Genz + 标准误测试 | D078 |

## §3 几何 + 场（15 分）

| 项 | 分 | PASS 条件 | 源 |
|----|----|-----------|----|
| 3.1 周期感知 fibre 连续性 + 层合 | 8 | `orthotropic_simp.py` 周期感知连续性 + laminate 测试 | D079 |
| 3.2 flip 约束恢复 CDT + 质量细化 | 7 | `stl_export.py` flip-recovery / refine 测试 | D080 |

## §4 测试基础设施（20 分）

| 项 | 分 | PASS 条件 |
|----|----|-----------|
| 4.1 Test count ≥ 1095 | 4 | `pytest --collect-only` ≥ 1095 |
| 4.2 Core coverage ≥ 95%（含 v12） | 4 | `--cov=core` TOTAL ≥ 95% |
| 4.3 Property tests ≥ 53 | 3 | `^def test_property_` ≥ 53 |
| 4.4 Mutation kill rate ≥ 75% | 3 | `tests/mutation_report.json` ≥ 0.75 |
| 4.5 Fingerprint DB ≥ 60 | 2 | `tests/fingerprints/*.json` ≥ 60 |
| 4.6 pytest gate green（D033） | 2 | `check_pytest_green` + D033 ADR 存在 |
| 4.7 v12 rubric 写入 agent + CI | 2 | `CHECKS_V12` in agent + `v12` in CI yaml |

## §5 用户面 demos（10 分）

| 项 | 分 | PASS 条件 |
|----|----|-----------|
| 5.1 设计级屈曲 / 自适应频带 demo | 3 | `design_buckling_demo`/`buckling_to_demo`/`inloop_band_demo` 引用 ≥1 |
| 5.2 增广 R2 / 多样性 demo | 3 | `augmented_r2_demo`/`diversity_demo`/`spacing_demo` 引用 ≥1 |
| 5.3 分层 copula / Korobov Genz demo | 2 | `nested_copula_demo`/`korobov_demo`/`lattice_genz_demo` 引用 ≥1 |
| 5.4 周期 fibre / flip-CDT demo | 2 | `laminate_demo`/`periodic_fibre_demo`/`cdt_refine_demo` 引用 ≥1 |

## §6 文档（15 分）

| 项 | 分 | PASS 条件 |
|----|----|-----------|
| 6.1 blueprint-v12 ≥6 ticks | 3 | `docs/blueprint-v12.md` `[x]` ≥ 6 |
| 6.2 tutorial v12 ≥4 new sections | 3 | `^### 22\.\d` ≥ 4 |
| 6.3 architecture v12 section | 3 | `docs/architecture.md` `## 22.` + "adaptive" |
| 6.4 ADRs D082+ ≥ 7 | 3 | `docs/decisions/D08[2-9]*.md` 编号 ≥ 82 共 ≥ 7 |
| 6.5 v12 quantitative anchors documented | 3 | 测试里 v12 锚点关键词 ≥ 3 |

## 完成度门控

`python scripts/test_agent.py --rubric v12 --strict` 须报告：v12 ≥ 99/100，v4-v11 全无回归
（各 = 100），pytest gate green（D033，0 failed/0 errors），全永久红线保持。
