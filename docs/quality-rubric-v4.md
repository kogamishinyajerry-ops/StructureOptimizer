# StructureOptimizer v4.x 质量评分体系

> 本文件定义 **v4.x "优秀水准（≥99/100）" 标准**。
> v1.x rubric 在 `docs/quality-rubric.md`（100/100，只读）。
> v2.x rubric 在 `docs/quality-rubric-v2.md`（97/100，只读）。
> v3.x rubric 在 `docs/quality-rubric-v3.md`（99/100，只读）。
>
> v4.x 比 v3.x **更严**：
> - 算法深度从"研究演示"升到"工业 MMA + Augmented Lagrangian + 屈曲 + robust"
> - 性能从"500K DOF"升到"2M DOF + AMG"
> - 测试规模从"≥ 400"升到"≥ 600" + mutation testing
> - 新增"专门测试 agent"维度（必须有 scripts/test_agent.py + CI 集成）
>
> 评分原则（同前三版）：
> - 全部标准是 binary 或带阈值，避免主观打分
> - **自我贬低优先于自我吹嘘**；模糊可争辩条目 → 当不满足
> - 一次评分一次写入历史表，不回填
> - **专门测试 agent 自动验证** —— 不接受人工声明

---

## v4.x 7 维度 100 分

### 1. 算法 / 物理深度（30 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 1.1 | Augmented Lagrangian stress constraint — σ_PN ≤ limit ± 1% | benchmark + scorecard | 8 |
| 1.2 | MMA / GCMMA optimizer 实装 + 与 OC 收敛性对比 | `core/mma.py` + comparison test | 8 |
| 1.3 | BESO-on-triangle 实装（闭合 D013） | `core/triangle_beso.py` + benchmark | 4 |
| 1.4 | Manufacturing projections 在 triangle 上实装（闭合 D008） | `core/triangle_manufacturing.py` + test | 3 |
| 1.5 | Buckling eigenvalue 约束 | `core/buckling.py` + benchmark + sensitivity test | 4 |
| 1.6 | Heaviside / robust formulation (η-min, mean, max) | `core/robust.py` + benchmark | 3 |

### 2. 性能 + 规模（15 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 2.1 | 1000×1000 mesh (≥2M DOFs) 跑通 + < 10 分钟 | benchmark + timing assertion | 5 |
| 2.2 | AMG preconditioner via pyamg (optional) — sparse_cg 500×500 收敛 | optional dep + sparse_cg test | 4 |
| 2.3 | Matrix-free CG operator — 内存 < 2× density × 64 bytes | `core/matrix_free_cg.py` + memory probe | 3 |
| 2.4 | 性能 baseline 扩展到 ≥3 mesh sizes | `tests/test_performance.py` ≥3 size cells | 3 |

### 3. 可复现 + 工程卫生（15 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 3.1 | Fingerprint DB ≥ 20 benchmarks (含 triangle) | count `tests/fingerprints/` | 4 |
| 3.2 | Triangle SIMP fingerprints ≥ 3 | grep "tri" in fingerprint dir | 3 |
| 3.3 | Mutation testing kill rate ≥ 70% | mutmut report | 4 |
| 3.4 | Cross-version drift detection script | `scripts/drift_check.py` | 2 |
| 3.5 | Reproducibility tests ≥ 30 | grep count | 2 |

### 4. 测试 + 测试基础设施（20 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 4.1 | 全测试 ≥ 600 | `pytest --collect-only` | 4 |
| 4.2 | core 覆盖率 ≥ 95% | `pytest --cov` | 4 |
| 4.3 | adapters 覆盖率 ≥ 90% | `pytest --cov=adapters` | 2 |
| 4.4 | Property tests ≥ 15 | grep `test_property_*` | 3 |
| 4.5 | **专用 test agent 实装** (`scripts/test_agent.py`) | 文件存在 + JSON 输出 + 各 item 可独立验证 | 4 |
| 4.6 | Test agent 集成到 CI | `.github/workflows/test.yml` 含 step | 3 |

### 5. 用户面 / 流程（10 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 5.1 | Bayesian optimization study driver | `core/bayesian_opt.py` + test | 3 |
| 5.2 | Auto-refinement loop（闭合 D010） | `core/refinement.py` + benchmark | 3 |
| 5.3 | Comparative study HTML report (compare 2+ runs) | `core/compare.py` + test | 2 |
| 5.4 | CLI color output + better error suggestions | `cli.py` + test | 2 |

### 6. 文档（10 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 6.1 | blueprint-v4.md 六波全勾 | 文件 + ✅ | 2 |
| 6.2 | tutorial.md v4 升级 (≥ 4 新章节) | 章节计数 | 3 |
| 6.3 | architecture.md v4 升级 + test agent 文档 | 章节计数 | 2 |
| 6.4 | ADR ≥ 8 个新决策 (D017-D024+) | 文件计数 | 3 |

---

## 评级界线

| 总分 | 等级 | 含义 |
|---|---:|---|
| ≥ 99 | **优秀** | v4.0 可发布 |
| 90-98 | 良好 | 大部分维度过关 |
| 80-89 | 合格 | 主线通 |
| < 80 | 不达标 | 不发 v4.0 |

---

## 评分历史（v4.x）

| 版本 | 总分 | 关键短板 | 备注 |
|---|---:|---|---|
| v3.0.0 (baseline) | 0/100 | v4 维度全空（无 MMA / 无 AugLag / 无 buckling / 无 robust / 无 1000×1000 / 无 mutation / 无 test agent） | v4 roadmap 已签发；v3 rubric 99/100 |

（每波结束后追加一行）

---

## 永久红线传承（v4 必须保持）

- **v1.x rubric 仍 = 100/100** —— 红线 7.4 + D015 reaffirmed
- **v2.x rubric 仍 ≥ 95/100** —— 实际 97/100，红线 7.3
- **v3.x rubric 仍 ≥ 99/100** —— v4 新红线，由 test agent 强制
- v1+v2+v3 共 705 测试 (134 + 264 + 407) 仍绿
- v1+v2+v3 core 覆盖率 ≥ 各自阈值
- v1+v2+v3 文档完整性不破

---

**评分签发完成。S 波即将开工。**
