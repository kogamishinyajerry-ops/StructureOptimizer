# StructureOptimizer v3.x 质量评分体系

> 本文件定义 **v3.x 的"优秀水准（≥95）"标准**。
> v1.x rubric 在 `docs/quality-rubric.md`（100/100，只读）。
> v2.x rubric 在 `docs/quality-rubric-v2.md`（97/100，只读）。
>
> v3.x 标准比 v2.x **更严**：v2 把"广度扩展"做透，v3 必须证明**深度**（算法严谨度、性能规模、跨平台可复现、用户面成熟度），否则不到 95。

> 评分原则（同前两版）：
> - 全部标准是 binary 或带阈值，避免主观打分
> - **自我贬低优先于自我吹嘘**；模糊可争辩条目 → 当不满足
> - 一次评分一次写入历史表，不回填

---

## v3.x 7 维度 100 分

### 1. 物理 / 算法深度（25 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 1.1 | 应力约束 SIMP **集成到梯度** (adjoint method) + benchmark 收敛 | `core/simp.py` 在 stress_constraint.enabled 时调 adjoint solve；benchmark 显示 stress 真实下降到 limit | 8 |
| 1.2 | SIMP-on-triangle **完整实装** + benchmark | `core/triangle.py` 含 SIMP 主循环 (或 mesh-agnostic 重构) + triangle 上跑通的 benchmark | 8 |
| 1.3 | stress + multi-case **同时启用** 的 benchmark | benchmarks/ 含一个配置同时打开 multi-case + stress_constraint | 5 |
| 1.4 | algorithm × mesh × backend **矩阵全跑通** | 测试矩阵：simp/beso × quad/triangle × dense/sparse | 4 |

### 2. 性能 + 规模（15 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 2.1 | 500×500 网格 (≥500K DOFs) 能跑通 + 时间 < 5 分钟 | benchmark + 时间记录 | 5 |
| 2.2 | incremental sparse assembly (重用模板) | `core/fem2d.py` 单独的"重用"路径；性能 vs 全重建 ≥2× | 4 |
| 2.3 | 多进程 study 并行 ≥3× 加速（4 核） | `core/study.py` 支持 workers 参数；benchmark 时间表 | 4 |
| 2.4 | 性能 baseline regression test | `tests/test_performance.py` 含 baseline 时间断言 | 2 |

### 3. 可复现 + 工程卫生（15 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 3.1 | 跨 Python 版本 (3.11/12/13) bit-exact 关键数值 | CI matrix 测试 + 数值对比 | 5 |
| 3.2 | 跨 OS (Linux + macOS) bit-exact 关键数值 | CI matrix；显式 cross-OS 测试 | 4 |
| 3.3 | benchmark fingerprint DB（每个 release 存 SHA） | `tests/fingerprints/*.json` + 比对测试 | 3 |
| 3.4 | reproducibility 测试 ≥10 benchmark | `tests/test_reproducibility.py` 覆盖 ≥10 | 3 |

### 4. 测试 + 正确性（15 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 4.1 | 全测试 ≥ 400 | `pytest -q` 计数 | 5 |
| 4.2 | core 覆盖率 ≥ 92% | `pytest --cov=structure_optimizer/core` | 5 |
| 4.3 | adapters 覆盖率 ≥ 85% | 同上 | 3 |
| 4.4 | property tests ≥ 5 总数（worst-case / aggregator / sensitivity / DOE coverage / lineage acyclic） | grep `_property_` or `for _ in range` 测试 | 2 |

### 5. 用户面 / 流程（10 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 5.1 | DOE study runner ≥2 sampling methods (LHS + Sobol) | `core/study.py` 含两种；测试覆盖 | 3 |
| 5.2 | 设计 lineage tracking | run 目录含 parent_id；study 含 lineage tree | 3 |
| 5.3 | Jupyter rich display (`_repr_html_` / `_repr_png_`) | `OptimizationResult.__repr_html__` 等存在；测试覆盖 | 2 |
| 5.4 | Interactive review HTML 升级 (toggle / pan / zoom) | demo.html / study.html 含 JavaScript / SVG interactivity | 2 |

### 6. 文档（10 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 6.1 | `docs/blueprint-v3.md` 七波全勾 | 文件存在 + 全 ✅ | 2 |
| 6.2 | `docs/tutorial.md` v3 升级（含 adjoint / DOE / lineage / Jupyter 章节） | 文件存在 + ≥5 个新章节 | 3 |
| 6.3 | `docs/architecture.md` v3 升级（含 adjoint / DOE / lineage 抽象） | 文件存在 + 新章节 | 2 |
| 6.4 | ADR ≥10 个新决策（D007-D016+） | `docs/decisions/D00[7-9]*.md` + `D01*.md` | 3 |

### 7. 永久红线 + 无回退（10 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 7.1 | runtime mandatory deps 仍仅 NumPy | grep pyproject.toml | 2 |
| 7.2 | 无 GUI / 无 cloud / 无 3D / 无 commercial | 人工 + grep | 3 |
| 7.3 | v2.x rubric **不回退** (仍 ≥ 95/100) | 重测 v2 rubric | 3 |
| 7.4 | v1.x rubric **不回退** (仍 100/100) | 重测 v1 rubric | 2 |

---

## 评级界线

| 总分 | 等级 | 含义 |
|---|---|---|
| ≥ 95 | **优秀** | v3.0 可发布 |
| 85–94 | 良好 | 大部分维度过关 |
| 70–84 | 合格 | 主线通 |
| < 70 | 不达标 | 不发 v3.0 |

---

## 评分历史（v3.x）

| 版本 | 总分 | 关键短板 | 备注 |
|---|---:|---|---|
| v2.0.0-final (baseline) | 0/100 | v3 维度全空（无 adjoint / SIMP-tri / 大网格 / DOE / lineage / 跨平台 / Jupyter） | v3 roadmap 已签发；v2.x rubric 97/100；v1.x rubric 100/100 |

（每波结束后追加一行）

---

## 附录：v3.x → v2.x → v1.x 标准对照

v1.x rubric 100 分项 → 在 v3.x 里**仍必须 100/100**（红线 7.4）。
v2.x rubric 100 分项 → 在 v3.x 里**仍必须 ≥ 95/100**（红线 7.3）。

v3.x 不允许任何 wave 让前两版 rubric 回退。具体保持要求（每 v3 commit 验证）：

- **v1.4.0 全部 134 测试仍绿** — 任何 commit 必须先确认 v1 测试不破
- **v2.0.0-final 全部 264 测试仍绿** — 任何 commit 必须先确认 v2 测试不破
- **v1.x core 覆盖率仍 ≥ 90%**
- **v2.x core 覆盖率仍 ≥ 90%**
- **v1.x + v2.x 文档完整性不破**（README / architecture / tutorial / ADR / CHANGELOG）

---

**评分签发完成。L 波即将开工。**
