# v7 质量评分卡 — production drivers & field-level fidelity (100 分)

> 由 `scripts/test_agent.py --rubric v7` 机械打分，写 `tests/v7_scorecard.json`。
> 与 v4/v5/v6 同构：6 section / 100 分 / D033 pytest-green gate（不计入 100 分，hard-fail）
> / v4·v5·v6 in-process 回归门（各须保持满分）。
> 评分项是 grep-based presence + 定量测试引用：对应 wave 落地前 FAIL，落地后 PASS。

主题：把 v6 的严格**正向求解器**接入**优化驱动器**，并把残留的全局/均匀简化提升到
**逐单元场级保真**。每项追溯到一条 v5/v6 ADR 的 reopening criterion（见 blueprint-v7）。

## §1 优化驱动器（24 分）

| 项 | 分 | PASS 条件 | 源 |
|----|----|-----------|----|
| 1.1 Reliability-based TO（FORM→SIMP） | 8 | `core/rbto.py` + 线性极限态解析 β_target 测试 | D038 |
| 1.2 几何非线性 TO（TL 伴随灵敏度） | 8 | `nonlinear_simp.py` TL 伴随 + 灵敏度 vs FD 测试 | D034 |
| 1.3 阻尼频响 TO（动柔度） | 8 | `freq_response.py` 动柔度驱动 + 灵敏度测试 | D035 |

## §2 场级保真 + 多目标（16 分）

| 项 | 分 | PASS 条件 | 源 |
|----|----|-----------|----|
| 2.1 逐单元各向异性热场 | 5 | `thermal.py` per-element tensor 场 + patch 测试 | D036 |
| 2.2 各向异性热 TO 灵敏度 | 4 | `thermal_simp.py` 各向异性灵敏度 vs FD 测试 | D036 |
| 2.3 NSGA-III 直接优化密度场 | 7 | `multi_objective_to.py` + hypervolume 单调测试 | D037/D023 |

## §3 不确定性 + 几何（15 分）

| 项 | 分 | PASS 条件 | 源 |
|----|----|-----------|----|
| 3.1 Nataf 变换（相关高斯） | 4 | `reliability.py` nataf + 相关映射测试 | D038 |
| 3.2 相关/非高斯 FORM | 4 | 已知相关线性极限态 β 解析测试 | D038 |
| 3.3 Ear-clipping 通用多边形 STL | 4 | `stl_export.py` earclip + 凹多边形面积守恒测试 | D039 |
| 3.4 STL 孔洞（even-odd） | 3 | 带孔（annulus）轮廓测试 | D039 |

## §4 测试基础设施（20 分）

| 项 | 分 | PASS 条件 |
|----|----|-----------|
| 4.1 Test count ≥ 900 | 4 | `pytest --collect-only` ≥ 900 |
| 4.2 Core coverage ≥ 95%（含 v7） | 4 | `pytest --cov=structure_optimizer/core` TOTAL ≥ 95% |
| 4.3 Property tests ≥ 40 | 3 | `^def test_property_` ≥ 40 |
| 4.4 Mutation kill rate ≥ 75% | 3 | `tests/mutation_report.json` aggregate ≥ 0.75 |
| 4.5 Fingerprint DB ≥ 35 | 2 | `tests/fingerprints/*.json` ≥ 35 |
| 4.6 pytest gate green（D033） | 2 | `check_pytest_green` + D033 ADR 存在 |
| 4.7 v7 rubric 写入 agent + CI | 2 | `CHECKS_V7` in agent + "v7" in CI yml |

## §5 用户面 demos（10 分）

| 项 | 分 | PASS 条件 |
|----|----|-----------|
| 5.1 RBTO 收敛 demo | 3 | `scripts/v7_demos.py` rbto demo 引用 |
| 5.2 非线性/阻尼 TO demo | 3 | nonlinear/damped-TO demo 引用 |
| 5.3 密度场 Pareto 渲染 | 2 | density-field Pareto render 引用 |
| 5.4 Ear-clipping STL demo | 2 | earclip/concave STL demo 引用 |

## §6 文档（15 分）

| 项 | 分 | PASS 条件 |
|----|----|-----------|
| 6.1 blueprint-v7 ≥6 wave ticks | 3 | `[x]` ≥ 6 |
| 6.2 tutorial v7 ≥4 new sections | 3 | `### 17.x` ≥ 4 |
| 6.3 architecture v7 section | 3 | `## 17.` + "driver" |
| 6.4 ADRs D042+ ≥ 7 | 3 | `docs/decisions/D04*.md` (≥42) ≥ 7 |
| 6.5 v7 quantitative anchors documented | 3 | 测试含 ≥3 个 v7 锚点引用（adjoint-vs-fd / hypervolume / nataf / beta_target / earclip-area / dynamic_compliance） |

## 完成度门控

v7 release-ready ⇔ total ≥ 99 / 100 **且** v4=v5=v6=100 无回归 **且** pytest gate green
（857+ passed / 0 failed / 0 errors）**且** 全永久红线保持。
