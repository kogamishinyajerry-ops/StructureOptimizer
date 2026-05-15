# StructureOptimizer v2.x 质量评分体系

> 本文件定义 **v2.x 的"优秀水准（≥95）"标准**。v1.x rubric 在 `docs/quality-rubric.md`（停留在 v1.4.0 100/100）。
>
> v2.x 标准比 v1.x **更严**：v1.x 已经把"基础工程化"做透，v2.x 必须证明物理 + 算法 + 后端 + I/O 都能扩展，否则不到 95。

> 评分原则（同 v1.x）：
> - 全部标准是 binary 或带阈值，避免主观打分
> - **自我贬低优先于自我吹嘘**；模糊可争辩条目 → 当不满足
> - 一次评分一次写入历史表，不回填

---

## v2.x 7 维度 100 分

### 1. 物理 + 算法扩展（30 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 1.1 | 多工况 worst-case formulation 实装 + 1 benchmark | `core/objectives.py` 含 worst-case + `benchmarks/` 含 ≥1 多工况配置 | 5 |
| 1.2 | 多工况 weighted_sum + average formulation | 同上 | 3 |
| 1.3 | 应力约束（p-norm 或 KS）实装 + 1 benchmark | `core/stress.py` + 应力约束 benchmark | 6 |
| 1.4 | stress_constraint_failed 错误状态码有专测 | `tests/test_failure_statuses.py` 含 stress_constraint_failed | 2 |
| 1.5 | BESO 算法完整实装 + 与 SIMP 等价 benchmark | `core/beso.py` + 等价测试（同 benchmark，不同算法，结果近似） | 6 |
| 1.6 | algorithm plug-in 抽象（基于 ABC） | `adapters/algorithm_base.py` 存在 + ≥2 实现 | 3 |
| 1.7 | CLI `--algorithm` flag 可切换 | `tests/test_cli.py` 测试 --algorithm simp / --algorithm beso | 2 |
| 1.8 | 算法选择有 ADR 文档化 | `docs/decisions/D00X-algorithm-plugin.md` | 3 |

### 2. 测试 + 正确性（20 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 2.1 | 全测试 ≥ 250 | `pytest -q` 退出码 + 计数 | 5 |
| 2.2 | core 覆盖率 ≥ 90% | `pytest --cov=structure_optimizer/core` | 5 |
| 2.3 | adapters 覆盖率 ≥ 80% | 同上 for adapters | 2 |
| 2.4 | 多工况 property test（worst-case ≥ average） | `tests/test_properties.py` 含 | 2 |
| 2.5 | sparse / dense backend 等价测试（≤ 1e-6 误差） | `tests/test_solver_adapter.py` 扩展 | 2 |
| 2.6 | meshio 读 + 优化 + 反读 round-trip 测试 | `tests/test_mesh_source.py` 含 | 2 |
| 2.7 | 几何导出（SVG/DXF/STL）解析回测试 | `tests/test_geometry_export.py` 含 | 2 |

### 3. 后端 + 网格（15 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 3.1 | scipy sparse optional backend 实装 | `adapters/solver_base.py` 含 ScipyCG / ScipyCholmod | 4 |
| 3.2 | 大网格 sparse vs dense 性能基准（≥3× 加速） | `docs/performance.md` 含表格 | 2 |
| 3.3 | optional dep 分类清晰（`[project.optional-dependencies].sparse` / `.mesh`） | `pyproject.toml` 含分组 | 2 |
| 3.4 | meshio adapter 读 2D 三角网格 | `adapters/mesh_source.py` 含 | 3 |
| 3.5 | 三角元素 stiffness 实装 + 测试 | `core/fem2d.py` 或新模块 | 2 |
| 3.6 | CI 同时跑 vanilla 和 with-extras 路径 | `.github/workflows/test.yml` 含 matrix | 2 |

### 4. 几何输出（10 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 4.1 | marching squares boundary extraction | `core/geometry_export.py` 含 | 3 |
| 4.2 | SVG 导出（含 element + boundary） | 同上 + 测试解析回 SVG | 2 |
| 4.3 | DXF R12 子集导出 | 同上 + 测试 DXF 文本 | 2 |
| 4.4 | STL ASCII 导出（2.5D extrusion） | 同上 + 测试 facet 数 | 2 |
| 4.5 | CLI `export` 子命令 | `tests/test_cli.py` 含 | 1 |

### 5. 文档（10 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 5.1 | `docs/blueprint-v2.md` 七波全勾 | 文件存在 + 全部 checked | 2 |
| 5.2 | `docs/tutorial.md` v2 升级（含多工况/应力/BESO/sparse/几何输出章节） | 文件存在 + ≥5 个新章节 | 3 |
| 5.3 | `docs/architecture.md` v2 升级（含算法/后端/网格抽象） | 文件存在 + 三块抽象图 | 2 |
| 5.4 | `docs/physics-reference.md` 含 formulation 公式 + 参考文献 | 文件存在 | 1 |
| 5.5 | CHANGELOG 含 v1.5 → v2.0 完整条目 | 七版本全有 entry | 1 |
| 5.6 | ADR ≥ 5 个新决策（v2 期间） | `docs/decisions/D00[2-6]-*.md` | 1 |

### 6. 代码质量 + CI（10 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 6.1 | `ruff check .` 0 issues | 退出码 | 2 |
| 6.2 | `ruff format --check .` 0 diff | 退出码 | 1 |
| 6.3 | `mypy structure_optimizer/` 0 errors | 退出码 | 2 |
| 6.4 | `pytest -q` < 60s | 总耗时 | 2 |
| 6.5 | CI workflow 双路径（vanilla + with-extras）全绿 | GH Actions latest run | 2 |
| 6.6 | 无新增死代码（ruff F401 / vulture） | 命令 | 1 |

### 7. 工程卫生 + 红线（5 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 7.1 | 永久红线未破（无 CAD/GUI/云/全 3D/商业求解器） | 人工 + grep（"ansys" / "tkinter" / "cad-kernel"等关键字应无） | 2 |
| 7.2 | `pyproject.toml` runtime mandatory deps 仍仅 NumPy | grep | 1 |
| 7.3 | 七波每波 atomic commit + SemVer tag | git log + tag list | 2 |

---

## 评级界线

| 总分 | 等级 | 含义 |
|---|---|---|
| ≥ 95 | **优秀** | v2.0 可发布 |
| 85–94 | 良好 | 大部分维度过关 |
| 70–84 | 合格 | 主线通 |
| < 70 | 不达标 | 不发 v2.0 |

---

## 评分历史（v2.x）

| 版本 | 总分 | 关键短板 | 备注 |
|---|---:|---|---|
| v1.4.0 (baseline) | 0/100 | v2 维度全空（仅有 v1.x 基线，无多工况/应力/BESO/sparse/meshio/export） | v2 roadmap 已签发；v1.x rubric 100/100 |
| v1.5.0 (Wave E) | 10/100 | F-K 波尚未开工：应力 / BESO / sparse / meshio / 几何输出 / tutorial v2 / CI 双路径 / etc | 多工况三 aggregator + 1 benchmark + 18 测试；core/objectives.py 100% 覆盖 |
| v1.6.0 (Wave F) | 18/100 | G-K 波尚未开工；测试 183 离 250 还差 67；CI 双路径未做；几何输出未做 | 应力 p-norm + KS + 1 benchmark + verification 集成 + 31 测试；core/stress.py 97.6% |
| v1.7.0 (Wave G) | 29/100 | H-K 波尚未开工；测试 205 离 250 还差 45；CI 双路径 / sparse / meshio / 几何输出 / tutorial v2 未做 | BESO + algorithm plug-in + CLI flag + 22 测试；algorithm_base.py 100%；core/beso.py 96.7% |

（每波结束后追加一行）

### 1.5.0 (Wave E) 评分明细
- 1.1 worst_case formulation + 1 benchmark: **+5/5**
- 1.2 weighted_sum + average formulation: **+3/3**
- 2.4 多工况 property test: **+2/2**

### 1.6.0 (Wave F) 评分明细
- 1.3 应力约束（p-norm + KS）+ 1 benchmark: **+6/6**
- 1.4 stress_constraint_failed 专测: **+2/2**

### 1.7.0 (Wave G) 评分明细
- 1.5 BESO + 与 SIMP 等价 benchmark: **+6/6**
- 1.6 algorithm plug-in 抽象 (ABC): **+3/3**
- 1.7 CLI --algorithm flag: **+2/2**



---

## 附录：v2.x → v1.x 标准对照

v1.x rubric 100 分项 → 在 v2.x 里**仍必须保持** 80%+。即 v2 不允许"扩展导致基础回退"。
v1.x rubric 文件保留只读，**不再修改**。v2.x 在新文件维护，新维度叠加。

具体保持要求（每 v2 commit 验证）：
- v1.4.0 全部 134 测试仍绿
- v1.x 覆盖率不回退（core ≥ 90%）
- v1.x 文档完整性不破（README / architecture / tutorial / ADR / CHANGELOG）

---

**评分签发完成。E 波即将开工。**
