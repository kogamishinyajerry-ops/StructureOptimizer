# StructureOptimizer 架构

日期：2026-05-16
状态：v0.4 frozen baseline

本文档描述模块边界、数据流和扩展点。属于 M0 工程基线的一部分，目的是让陌生工程师 10 分钟读完知道每个目录在做什么、不在做什么。

---

## 1. 数据流（黑盒视角）

```text
BenchmarkConfig (JSON)
        │
        ▼
   structured mesh (mesh.py)
        │
        ▼
   baseline FEA (fem2d.py)  ──► baseline metrics (mass / compliance / max_displacement / max_stress)
        │
        ▼
   SIMP loop (simp.py)
        │   ├─ 每轮：刚度插值 → FEA → 灵敏度 → 密度过滤 → OC update
        │   └─ 终止条件：max_iterations 或 change_tolerance
        ▼
   final density field (numpy ndarray)
        │
        ▼
   run directory artifacts
        │   ├─ input.json / metrics.csv / density.npy / summary.json
        │   ├─ baseline.png / loadcase.png / density.png / convergence.png
        │   └─ optimization.gif / optimization_frames/
        ▼
   independent verification (verification.py)  ──► verification.json
        │   不复用迭代指标，最终密度场重新装配并求解
        ▼
   report (reporting.py)   ──► report.md
        │
        ▼
   (可选) demo (demo.py)   ──► demo.html
        │
        ▼
   (可选) study runner (study.py) 把上述 run → verify → report → demo 流水线
        │   批量执行不同参数候选，并生成 candidates.csv + study.html
```

`workflow.run_config` 是这条流水线的入口；`cli.py` 把它包装成 `run` / `verify` / `report` / `demo` / `study` 五个子命令。

---

## 2. 模块边界

| 模块 | 职责 | 不做的事 |
|---|---|---|
| `structure_optimizer/benchmarks/` | 内置 benchmark JSON 配置 + registry + preset 解析 | 不做配置校验（在 `core/config.py`） |
| `structure_optimizer/core/config.py` | `BenchmarkConfig` dataclass 解析 + 完整工程校验 | 不读写文件 |
| `structure_optimizer/core/mesh.py` | structured quad mesh 节点/单元生成 | 不做 CAD 几何输入 |
| `structure_optimizer/core/design_space.py` | `RegionSelector` → frozen/void mask | 不影响 FEM 装配，仅影响 SIMP update |
| `structure_optimizer/core/fem2d.py` | 线弹性 2D 平面应力 FEM 装配 + 求解 | 仅 NumPy dense；不做 sparse / 3D / 非线性 |
| `structure_optimizer/core/filtering.py` | SIMP 灵敏度密度过滤 | 仅做卷积核风格的简单过滤 |
| `structure_optimizer/core/simp.py` | SIMP 主循环（刚度插值 / 灵敏度 / OC update / 多工况权重柔度） | 仅最小柔度目标 |
| `structure_optimizer/core/manufacturability.py` | v0.2 粗 warnings：isolated_islands / thin_member / local_density | 不作为优化约束（v0.6 计划升级） |
| `structure_optimizer/core/verification.py` | 独立验证：最终密度场重装配 + 重求解 + 约束检查 | 不能与迭代指标混用 |
| `structure_optimizer/core/reporting.py` | 生成 `report.md` | 不生成 HTML（`demo.py` / `study.py` 各自负责） |
| `structure_optimizer/core/run_store.py` | run 目录创建 + 输入/输出文件序列化 + input hash | 不知道任何模型语义 |
| `structure_optimizer/core/workflow.py` | 流水线编排：mesh → SIMP → 产物落盘 → verify → report | 不直接做计算 |
| `structure_optimizer/core/demo.py` | 单次运行的 `demo.html` 静态评审页 | 不做服务端渲染 |
| `structure_optimizer/core/study.py` | 参数 grid search + 候选排名 + `study.html` | 不做通用优化驱动 |
| `structure_optimizer/visualization/` | matplotlib 出 PNG / GIF | 不依赖 GUI backend（headless 安全） |
| `structure_optimizer/adapters/` | 后续替换的边界（求解器 / 优化器 / 文件导出） | 当前是 Protocol stub，不强制使用 |
| `structure_optimizer/cli.py` | argparse 命令行入口 | 不做业务逻辑 |
| `tests/` | pytest；冒烟 + 集成 + 输入校验 | 不做性能基准（v1.0 计划） |

---

## 3. 关键数据对象

### 3.1 `BenchmarkConfig`
位于 `core/config.py`。字段族：

- `name` / `dimension` / `units`
- `mesh`：`StructuredQuadMesh(nelx, nely)`
- `material`：`Material(young_modulus, poisson_ratio, density)`
- `boundary_conditions`：节点/边/区域约束
- `loads` *或* `load_cases`：单工况兼容旧 schema；多工况走 `load_cases` + 权重
- `optimization`：`Optimization(objective, volume_fraction, penalty, filter_radius, max_iterations, change_tolerance)`
- `design_space`（可选）：`frozen_solid` + `void` `RegionSelector` 列表

校验规则在 `validate_config()`，包括：
- `volume_fraction ∈ (0, 1]`
- `young_modulus / density / penalty / filter_radius > 0`
- 至少一个载荷 + 至少一个约束
- frozen/void 区域不重叠
- 多工况权重归一化后非零

### 3.2 `verification.json`
独立验证产物，统一 schema：

```json
{
  "status": "passed | warning | failed",
  "objective": {"name": "compliance|weighted_compliance", "value": ..., "source": "independent_verification"},
  "responses": [{"name": "mass|compliance|max_displacement|max_stress", "value": ..., "source": ...}],
  "constraints": [{"name": ..., "value": ..., "limit": ..., "unit": ..., "source": ..., "status": "passed|failed|missing"}],
  "baseline": {...},  // 原始实心结构指标
  "candidate": {...},  // 优化后候选指标
  "load_cases": [...],  // 多工况 baseline/candidate 独立指标
  "manufacturability": {...},  // v0.2 粗检查
  "actual_volume_fraction": ...,
  "target_volume_fraction": ...
}
```

### 3.3 失败状态分类
`core/verification.py` 中的 `FAILURE_STATUSES`：

- `invalid_config` — 配置层不通过
- `solver_failed` — FEA 求解失败
- `singular_matrix` — 刚度矩阵奇异
- `volume_constraint_failed` — 体积分数超目标
- `connectivity_failed` — 候选结构从载荷区到支撑区无材料连通路径
- `design_space_constraint_failed` — frozen/void mask 被破坏
- `report_failed` — 报告生成失败

---

## 4. 扩展点（adapters/）

### 4.1 LinearSolver（v0.8 起实装）

`adapters/solver_base.py` 已从 Protocol stub 升级为真实抽象：

- `LinearSolver` ABC：抽象方法 `solve(matrix, rhs) -> np.ndarray`
- `NumpyDenseSolver`：`np.linalg.solve` 直解；O(N³) cost、O(N²) memory；小规模主线
- `NumpyCGSolver`：纯 NumPy Jacobi-preconditioned 共轭梯度迭代解；更省内存
- `get_linear_solver(backend)` 工厂：`"dense"`（默认）/ `"cg"`
- `available_backends()` 列出已注册名

`BenchmarkConfig.solver.backend` 配置字段（默认 `"dense"`）控制选用哪个 backend，校验会拒绝未注册的名字。`fem2d.solve_linear_elastic` 内部仅通过 `get_linear_solver` 拿到实例，不直接调用 `np.linalg.solve` — 这就是抽象屏障。

**未来扩展方向**（不在 v0.x 范围）：
- scipy.sparse.linalg.spsolve / cg / minres backend：要求把 scipy 加入依赖；先评估能否被本地 NumPy CG 满足
- CalculiX / Code_Aster file-based adapter：写入 deck → shell out → parse；引入文件 IO 路径
- JAX-FEM 后端：评估 GPL 影响（v1+ spike）

### 4.2 其他扩展点（仍为 Protocol stub）

- `adapters/optimizer_base.py` — 替换优化算法（MMA / 多目标 Pareto driver / robust formulation）
- `adapters/file_export.py` — 文件导出边界（VTK / mesh 格式 / 后处理）

**约束**：
- 引入真实实现时必须保持 `core/` 内部默认路径仍可走（不强制依赖 adapter 配置）
- adapter 实例化由 `core/` 内部通过工厂函数装配（如 `get_linear_solver`），CLI/workflow 不直接 import 具体类

---

## 5. 永久不变量（invariants）

这些是项目的硬性约束，任何 PR 都不能破坏：

1. **本地优先**：不依赖任何外部服务 / 网络 / 云 SDK 才能跑测试
2. **配置优先**：每个 benchmark 由显式 JSON 驱动，无硬编码工况
3. **验证优先**：迭代指标与独立验证指标在所有产物中明确区分（前缀 `baseline` / `candidate` / `optimized` 必须出现）
4. **`runs/<benchmark>/<run_id>/` 目录结构稳定**：`input.json` + `metrics.csv` + `density.npy` + `density.png` + `verification.json` + `report.md` 是 v0.1 起的契约
5. **无 CAD 内核 / GUI / 完整 3D / 商业求解器**（永久红线，见 CHANGELOG 与 PRD）
6. **测试全绿** 是 commit/tag 前置条件

---

## 6. 当前已知限制

- FEM 实现是 dense NumPy，仅适用于小 benchmark 网格（典型 ≤ 200 × 200）
- 仅平面应力 2D / 2.5D 厚度模型
- `simple_bracket` 的 3D 维度只是数据模型预留，未做 3D 求解
- `design_space` 选择器仅支持结构化网格上的 `box` / `circle`，不支持任意几何
- 制造性是 v0.2 粗 warning，不构成优化约束（v0.6 计划升级）
- study runner 只做 grid search，无 DOE / 主动学习

详见 `docs/PRD-v0.1.md` §8 风险与约束。

---

## 7. 如何添加新 benchmark（操作清单）

1. 在 `structure_optimizer/benchmarks/configs/<name>.json` 写完整配置（含至少一个载荷 + 一个约束）
2. 在 `structure_optimizer/benchmarks/registry.py` 注册名字（必要时加 preset）
3. 在 `tests/` 加一个冒烟测试覆盖该 benchmark 小网格 run → verify
4. `python -m pytest` 全绿后 commit

不要为单个新 benchmark 引入新依赖；如必须，先在 PR 中说明真实问题与替代方案。

---

## 8. v2.x 抽象与扩展点（Waves E → J）

v2.x 在不破红线的前提下加了三类 plug-in 抽象 + 多工况/应力 objectives + 几何输出层。模块边界：

```
                ┌─ TopologyAlgorithm ABC ─┐
config + mesh ──┤   SimpAlgorithm         ├──┐
                │   BesoAlgorithm         │  │
                └─────────────────────────┘  │
                                             ▼
                ┌─ Mesh ───────────────┐     ┌─ Solve loop ────┐
                │  StructuredMesh      │ ──▶ │  density →      │ ──▶ OptimizationResult
                │  TriangleMesh*       │     │  FEM → grad     │
                └──────────────────────┘     └────┬────────────┘
                  ▲                                │
                  │ load via                       ▼
                  │                          ┌─ LinearSolver ABC ┐
        ┌─ MeshSource ABC ─┐                 │  NumpyDenseSolver │
        │   MeshioReader   │                 │  NumpyCGSolver    │
        └──────────────────┘                 │  ScipySparseSolver│
                                             │  ScipySparseCG    │
                                             └───────────────────┘
                                                       │
                                                       ▼
                                            OptimizationResult
                                                       │
                                                       ▼
                                      ┌─ geometry_export ─┐
                                      │  SVG / DXF / STL  │
                                      └───────────────────┘

* TriangleMesh: linear-elastic solve only, not SIMP (see D005).
```

### 8.1 Algorithm plug-in (`adapters/algorithm_base.py`)

- `TopologyAlgorithm` ABC，方法 `run(config, mesh) → OptimizationResult`
- 内置 `simp` (default) + `beso`；选择由 `OptimizationConfig.algorithm`，CLI `--algorithm` flag 可覆盖
- 新算法接入：写一个类 + 注册到 `_REGISTRY`
- 决策：`docs/decisions/D002-algorithm-plugin-abstraction.md`

### 8.2 Linear-solver backend plug-in (`adapters/solver_base.py`)

- `LinearSolver` ABC + `prefers_sparse` 标志（决定 dense vs CSR assembly）
- 内置 4 backend：`dense` / `cg`（NumPy）/ `sparse` / `sparse_cg`（scipy，optional）
- scipy 缺失时 sparse backend 自动不注册；`available_backends()` 动态返回
- 决策：`docs/decisions/D004-sparse-optional-dep.md`

### 8.3 Mesh source plug-in (`adapters/mesh_source.py`)

- `MeshSource` ABC + `MeshioReader`（optional [mesh] extra）
- 未来 reader（FreeCAD、自定义 .ply、Gmsh script）写一个类即可
- 决策：`docs/decisions/D005-triangle-mesh-no-simp.md`

### 8.4 Multi-load-case aggregation (`core/objectives.py`)

- `AGGREGATORS = {"weighted_sum", "average", "worst_case"}`
- SIMP 与 BESO 都用；selected via `OptimizationConfig.case_aggregator`
- 数学：`docs/physics-reference.md` §3

### 8.5 Stress aggregation (`core/stress.py`)

- p-norm + KS smooth-max 两种 aggregator
- verification-time 检查，不进 SIMP 主循环（D003 决策）
- 新 failure status：`stress_constraint_failed`

### 8.6 Geometry export (`core/geometry_export.py`)

- 元素级 marching squares 简化 → axis-aligned 边界段
- 三种 writer：SVG / DXF R12 / STL ASCII (2.5D 挤出)
- CLI `export` subcommand
- 决策：`docs/decisions/D006-geometry-export-scope.md`

### 8.7 永久红线在 v2 内（重申）

- runtime mandatory deps 仍仅 NumPy；scipy / meshio 进 `[project.optional-dependencies]`
- 无 GUI、无 cloud、无 commercial-solver、无 full-3D
- TriangleMesh 是 2D；STL 是 2.5D 挤出（不是真 3D）
- failure 仍单行 stderr + 状态码字符串，无 traceback 泄漏

---

## 9. v2.0 已知限制（更新版）

- 仅 2D / 2.5D（永久红线）
- SIMP-on-triangle 未做（D005 留白）— TriangleMesh 仅支持 linear elastic solve
- 应力约束仅 verification-time（D003 留白）— 未集成到 SIMP 梯度（需 adjoint method）
- overhang 制造约束 deferred 到 v3+（D001）
- LLM / AI 顾问能力 not in scope（永久红线）
- benchmark coverage 集中在 mbb_beam / cantilever / l_bracket / loaded_hook / simple_bracket / stress_limited_bracket / multi_load_cantilever

详见 `CHANGELOG.md` v2.0.0 条目的 honest caveat 节 + 各 ADR 的 "Reopening criteria"。

---

## 10. v3.x 抽象与扩展点（Waves L → R）

### 10.1 Stress adjoint (`core/adjoint.py`)

Wave L 填补 v1.6 D003 留白。`adjoint_stress_sensitivity(config, mesh, densities, displacements)` 解 K λ = ∂σ_PN/∂u 并返回 dσ_PN/dρ_e；`run_simp` 在 `stress_constraint.enabled and stress_penalty > 0` 时按 Le et al. 2010 normalization 加权叠加 stress sens 到 compliance sens。详 D007。

### 10.2 Triangle SIMP (`core/triangle_simp.py` + `core/triangle_filter.py`)

Wave M 填补 v1.9 D005 留白。`run_simp_triangle` 与 quad `run_simp` 并行存在；不共享 mesh-abstraction（v2.2 是 "two-loops" 风险更低，参 D008 § "Why parallel loops"）。centroid-distance Sigmund filter 取代 grid-neighbor filter；面积加权体积约束取代 unit-area 假设。

### 10.3 增量 sparse 装配 (`core/fem2d.SparseAssemblyTemplate`)

Wave N。`build_sparse_assembly_template(mesh, ke)` 一次性算 (rows, cols, ke_flat) pattern，`assemble_with_template(template, density_scale)` 每次只重算 vals。SIMP main loop 在 sparse backend 时一次建模板复用所有迭代。详 D009。

### 10.4 并行 study (`core/study.run_study(workers=N)`)

Wave N。`ProcessPoolExecutor` 跑独立 candidate；每 worker 重建 config（picklable），写入独立 subdir。`workers=1` 是默认，与 v1.x 行为完全一致。

### 10.5 DOE 采样 (`core/sampling.py`)

Wave O。`lhs_samples(n, n_dims, rng)` 纯 NumPy；`sobol_samples(n, n_dims, rng)` 包 scipy.stats.qmc.Sobol（缺 scipy 时 clear error）。`map_samples_to_grid(samples, parameters)` 把 unit-cube 样本映射到具体参数值。`StudyConfig.sampling` 字段 ∈ `{grid, lhs, sobol}`，默认 grid 保持 v1.x JSON 兼容。

### 10.6 设计 lineage (`core/lineage.py`)

Wave O。`LineageRecord(run_id, parent_id, study_id, generation)` 数据类；`write_lineage` / `read_lineage` 写读 `lineage.json`；`build_lineage_tree(study_dir)` 走 candidate_*/lineage.json 拼成 JSON tree。workflow.run_config 接 parent_id/study_id/generation kwargs。

### 10.7 Fingerprint 数据库 (`tests/fingerprints/`)

Wave P。每 benchmark 一个 JSON，含 input_hash / density_sha256 / scalar_sha256 + 人类可读的前 8 个值 + 全精度 scalars。`scripts/generate_fingerprints.py` 重新生成（仅在故意改 benchmark 行为时）。CI 在 canonical cell 严比对（`REQUIRE_BIT_EXACT_FINGERPRINT=1`），其他 cell 容忍 ≤1e-9（跨 LAPACK build 物理限制，详 D011）。

### 10.8 Jupyter rich display (`core/repr_html.py`)

Wave Q。`OptimizationResult` / `TriangleOptimizationResult` / `FEMResult` / `BenchmarkConfig` 都有 `_repr_html_`；`OptimizationResult` 还有 `_repr_png_`（pure NumPy + zlib 编 PNG，不引 Pillow）。`OptimizationResult.mesh_shape` 字段记录 (nelx, nely) 让 `_repr_png_` 知道 reshape 形状；默认 `(0, 0)` 时 graceful return None（向后兼容）。

### 10.9 v3 永久红线（重申 + 增量）

- 运行时仅依赖 NumPy（包 scipy / meshio 始终 optional）
- 无 GUI / 无 cloud / 无 full-3D / 无 commercial CAE 求解器
- 失败仍单行 stderr + 状态码字符串（v1 红线，v3 不破）
- 跨平台 bit-exact 在 canonical CI cell 之外 **不强求**（D011 § "Reproducibility tolerance philosophy"）
- demo HTML 仍 self-contained 单文件（D012 § "Why vanilla JS"）

---

## 11. v3.0 已知限制

- 仍 2D（3D 永久红线）
- Stress-adjoint 仅 quad SIMP；triangle 路径无 stress adjoint（D008 defer）
- BESO 仅 quad（无 BESO-on-triangle；D013 defer）
- 经典 penalty method 不保证 σ_PN ≤ limit 严格满足（D007 honest scope note）
- AMG preconditioner / pyamg 未引（D009 defer；500×500 用 sparse direct）
- 自动 refinement loop 未做（D010 只提供 lineage **机制** + parent_id，不规定 **策略**）
- `_repr_png_` 仅 quad SIMP（triangle 是非结构化拓扑，需要多边形 raster）
- LLM / AI 顾问能力 not in scope（永久红线）

详 ADR D001-D016 各自的 "Reopening criteria" 节。

---

## 12. v4.x 抽象与扩展点（Waves S → X · D017-D024）

### 12.1 MMA + Augmented Lagrangian (`core/mma.py`, `core/augmented_lagrangian.py`)

Wave S。`mma_step(x, df, fval, dfdx, xmin, xmax, state)` 一步 Method of Moving Asymptotes 更新；
内部以渐进可移动凸子问题 + 对偶分解（block-coordinate bisection on λ）解 m 个对偶变量。
`augmented_objective(f, df, g, dg, state)` 把 m 个不等式约束并入目标，`update_multipliers`
按 Powell-Hestenes 更新 μ 与 ρ。`run_simp_with_mma(config, mesh)` 整合两者作为 SIMP 主循环
的可选 driver；与 OC 对照通过 `tests/test_mma_vs_oc.py`。详 D017。

### 12.2 Triangle BESO + 三角制造投影 (`core/triangle_beso.py`, `core/triangle_manufacturing.py`)

Wave T 填补 D013 defer。BESO 的元素增删按 area-weighted 排序（不是 unit-count），
保证非均匀三角网格的体积分数正确；制造投影改为 centroid-based pairing。3 个
triangle benchmark 已 fingerprint 化。详 D018。

### 12.3 屈曲特征值 + Heaviside 三场 (`core/buckling.py`, `core/robust.py`)

Wave U。`linearized_buckling(config, mesh, densities)` 解 K φ = λ K_G φ 的最小本征值
（power iteration on K⁻¹ K_G）；`project_robust_fields(rho, eta_eroded, eta_dilated, beta)`
返回 eroded/nominal/dilated 三场。`heaviside_project(rho, params)` + `heaviside_project_grad`
是基础投影 + 链式导数。详 D019。

### 12.4 Bayesian opt + 自动加密 + 对比 + CLI 增强 (`core/bayesian_opt.py`, `core/refinement.py`, `core/compare.py`, `cli.py`)

Wave V。`bayes_optimize(objective, bounds, n_init, n_iter, rng)` 是纯 NumPy
GP + EI 采集函数（无 scikit-learn 依赖）。`refine_loop` 在感兴趣 region 自动局部加密
（闭合 D010 留白）。`render_side_by_side(result_a, result_b, html_path)` 写并排对比报告。
CLI 加 `cli_red/green/yellow` ANSI helpers + `diagnose_error`（单行 stderr 不破红线，
`NO_COLOR=1` 关闭）。详 D020。

### 12.5 AMG + 矩阵自由 CG + 1000×1000 + 突变测试 (`adapters/solver_base.AMGCGSolver`, `core/matrix_free_cg.py`)

Wave W。`AMGCGSolver` (`backend="amg"`) 把 pyamg `smoothed_aggregation_solver`
作 CG preconditioner（O(n) setup，迭代次数从 1000+ 降到 ~50）；`matrix_free_apply` /
`matrix_free_diagonal` / `matrix_free_cg` 按 element-by-element 计算 K·v，
内存 O(n_elem) 而非 O(n_elem²)。`benchmarks/configs/xlarge_cantilever.json` 是
1000×1000 = 2M-DOF 标杆。`scripts/run_mutation_test.py` 是 4-mutator
in-house 变异测试（70%+ 杀伤率门槛）；`scripts/drift_check.py` 比对当前
benchmark 输出哈希 vs 历史指纹。详 D021。

### 12.6 测试 agent + v4 评分体系 (`scripts/test_agent.py`)

Wave W/X。`test_agent.py` 是 v4 阶段引入的**独立机械验证器**，按
`docs/quality-rubric-v4.md` 100 分制 23 个条目扫描整个代码库，
逐项输出 PASS/PARTIAL/FAIL + 文件级证据，并把分数写入 `tests/v4_scorecard.json`。

设计原则：
1. **机械可验**：每个条目用 grep/coverage/pytest 计数，不靠人工判断
2. **诚实优先**：阈值故意定高（核心覆盖率 ≥ 95% 而非 ≥ 80%），不达就 fail
3. **零回归**：同时检查 v1/v2/v3 rubric 不能回归，保证向前没有性能/算法/复现退化
4. **CI 集成**：`.github/workflows/test.yml` 把 test_agent 作为独立 step，rubric ≥ 99 才放行 release

调用：

```bash
python scripts/test_agent.py                    # 跑完整 rubric
cat tests/v4_scorecard.json | jq '.total_earned'  # 当前分数
```

详 D022 / D023 / D024。

### 12.7 v4 永久红线（重申 + 增量）

- 运行时仅依赖 NumPy（pyamg / scipy / meshio / matplotlib 全部 optional）
- 无 GUI / 无 cloud / 无 full-3D / 无 commercial CAE 求解器
- 失败仍单行 stderr + 状态码字符串（v1 红线，v4 不破）
- 测试 agent 的评分必须诚实——v3 不能因为 v4 蓝图变化就回归

---

## 13. v4.0 已知限制

- 仍 2D（3D 永久红线）
- 矩阵自由 CG 暂无前置条件（朴素 Jacobi），AMG 路径走 sparse 装配
- BESO-on-triangle 不带 stress adjoint（与 D008 一致 defer）
- 1000×1000 网格 dense 路径需要 ≥ 30 GB 内存，必须走 `sparse` / `amg` 后端
- pyamg 与 scipy 是 optional dep；不装时 `solver.backend="amg"` 报错列出可用后端
- LLM / AI 顾问能力 not in scope（永久红线）

详 ADR D017-D024 各自的 "Reopening criteria" 节。

---

## 14. v5.x 抽象与扩展点（multi-physics · Waves Y → DD · D025-D032）

v5 把 v1-v4 的"单物理场 + 工程纪律"模式推广到 **multi-physics 2D**。所有新模块
仍在 numpy-only + no-3D + no-GUI + no-commercial-solver 红线内。

### 14.1 热传导 FEM + SIMP (`core/thermal.py`, `core/thermal_simp.py`)

Wave Y, D025. 2D Poisson 热传导。Element matrix 形如
`Ke = k·t/6 · [[4,-1,-2,-1],...]`（Cook 1989 §10.2）。
DOF/node = 1 (scalar T)。`heat_sink` benchmark + 1D-rod 解析校验。

### 14.2 模态 + 频响 (`core/modal.py`, `core/freq_response.py`)

Wave Z, D026. 广义本征值问题 K φ = ω² M φ 用纯-numpy Cholesky 变换 + eigh
求解（避免 scipy 依赖）。Consistent + lumped mass 两种 element matrix。
Frequency-domain harmonic response (K - ω²M) u = f 无 damping。

### 14.3 几何非线性 FEM + SIMP (`core/nonlinear_fem.py`, `core/nonlinear_simp.py`)

Wave AA, D027. 简化的 Total-Lagrangian Newton-Raphson + 增量加载。复用
v4 的 `core/buckling.assemble_geometric_stiffness`（同 SIMP penalty + 同符号约定）。
Gere elastica 趋势校验（qualitative, not bit-exact）。

### 14.4 多材料 SIMP (`core/multi_material.py`)

Wave BB, D028. Sigmund-Tortorelli 形式：M 个独立 density field 每元素，
`E_eff = E_min + Σᵢ ρ_{i,e}^p · (Eᵢ - E_min)`。Per-material 体积约束 +
per-material OC update。

### 14.5 随机 / 可靠性 (`core/stochastic.py`, `core/reliability.py`)

Wave CC, D029. Monte Carlo UQ over uncertain loads / materials；预采样
K 个 scenarios 的 worst-case (minimax) SIMP。所有 RNG 走 `default_rng(seed)`
保证给定 seed + 平台 bit-exact 可复现；跨平台 bit-exact 不强求。

### 14.6 Pareto + STL + Autodiff (`core/pareto_nsga.py`, `core/stl_export.py`, `core/autodiff.py`)

Wave DD, D030-D032. 最小化 NSGA-II (bi-objective Pareto) + SBX crossover +
polynomial mutation。2D voxel → 12-triangle-per-cell ASCII STL boundary 导出
（3D 打印工程链 ready）。Pure-NumPy forward-mode AD（`Var` 类）+ central FD
gradient check 用于敏感度验证。

### 14.7 v5 永久红线（重申）

- v5 不破任何 v1-v4 红线
- 所有 multi-physics 模块仍纯 numpy；optional deps 不增
- Stochastic 模块：RNG 给定 seed + 平台 bit-exact；跨平台不强求
- Mass matrix / nonlinear / multi_material / autodiff / stl_export 均 dense-only
- 测试 agent v5 rubric **机械评分**，包含 v4 不能回归的硬性 gate

---

## 15. v5.0 已知限制

- 仍 2D（3D 永久红线，跨版本不变）
- 热传导只支持 scalar conductivity（无 anisotropic / orthotropic）
- 模态分析 dense eigh，~2000 DOFs 上限；更大需要 scipy sparse eigsh
- 频响 undamped only；Rayleigh damping 是 v5+ option
- 几何非线性 simplified TL — qualitative Gere match not bit-exact
- 多材料 Poisson 比共享（只用 material[0] 的 ν）
- Monte Carlo 只支持 Gaussian uncertainty；无 FORM / SORM / importance sampling
- NSGA-II 只支持 2 个目标；≥3 需要 reference-point variants (NSGA-III)
- STL export 是 voxelized；marching-cubes 是 v6+ option
- LLM / AI advisor not in scope（永久红线）

详 ADR D025-D032 各自的 "Reopening criteria" 节。
