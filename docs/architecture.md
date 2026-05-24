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

## 16. v6 — production-grade formulations

v6 把 v5 **有意简化**的 7 处公式升级为严格、可解析校验的 production-grade 实现（每处
都源自对应 v5 ADR 的 "Reopening criteria"），在永久红线**内**把精度推到生产级。§15 的
对应限制由此解除：

| v5 限制（§15） | v6 升级 | 模块 | ADR | 定量锚点 |
|---|---|---|---|---|
| simplified TL，仅 qualitative Gere | 完整 Total-Lagrangian Green-strain + 2nd PK + 一致切线 | `core/total_lagrangian.py` | D034 | 有限旋转 objectivity 1e-10 + 常应变 patch |
| 频响 undamped only | Rayleigh 阻尼复频响 C=αM+βK | `core/freq_response.py` | D035 | SDOF 半功率带宽解析 |
| 热传导仅 scalar k | 各向异性 / 正交各向异性张量 k | `core/thermal.py` | D036 | 正交各向异性 patch test 1e-9 + 旋转不变 |
| NSGA-II 仅 2 目标 | NSGA-III ≥3 目标（Das-Dennis + niching） | `core/pareto_nsga.py` | D037 | 参考点精确组合数 + DTLZ2 单位球收敛 |
| MC 仅 Gaussian，无尾事件方法 | FORM/SORM + importance sampling | `core/reliability.py` | D038 | 线性极限态 β 解析 + Breitung + IS 方差缩减 |
| STL 是 voxelized（O(h)） | Marching-squares 平滑边界 STL（O(h²)） | `core/stl_export.py` | D039 | 面积 O(h²) 收敛 + beats voxel |
| autodiff 实为 forward-mode | Reverse-mode（tape）AD | `core/autodiff.py` | D040 | reverse==forward==解析==中心差分 + DAG 复用 |

### 16.1 production-grade 原则

- 每个升级配**定量解析校验**（不是 v5 的 qualitative trend）——见上表锚点列。
- 向后兼容：v6 新增 API 不破坏 v5 调用（如 `solve_thermal` 的 `conductivity_tensor`
  默认 None 走原标量路径；`write_stl` voxel 路径不动；`Var` forward-mode 保留）。
- 完成度门控：`python scripts/test_agent.py --rubric v6` ≥99/100，且 v4/v5 无回归 +
  **pytest gate green**（D033）+ 全永久红线保持。
- 永久红线**全部不变**：numpy-only 运行时、2D/2.5D、本地可跑、单行 stderr、无 LLM、
  自我贬低优先于自我吹嘘。`marching-squares` 在 2D 仍是 2.5D 挤出；`reverse-mode AD`
  用纯 numpy tape（不引入 JAX）。

### 16.2 v6 已知限制（诚实范围）

- 张量热传导是 global k（非 per-element 场）；anisotropic 热 TO 灵敏度未接入。
- SORM 用 Breitung 渐近式；FORM/SORM 假设独立高斯变量（无 Nataf/Rosenblatt）。
- Marching-squares caps 是 centroid-fan（star-convex 水密）；非 star-convex / 带孔
  截面需 ear-clipping。
- Reverse-mode AD 仅 + - * / ** neg 标量算子，未端到端微分 SIMP 目标。
- 详见 D034-D040 各自 "Honest scope notes" + "Reopening criteria"。

## 17. v7 — production drivers & field-level fidelity

v7 把 v6 的**严格正向求解器接入优化驱动器**，并把残留的"全局/均匀"简化提升到**逐单元
场级保真**。每个 wave 都源自 v6（或 v5）ADR 明列的 "Reopening criteria"——§16.2 的限制
由此逐条解除：

| v6 限制（§16.2） | v7 driver / 升级 | 模块 | ADR | 定量锚点 |
|---|---|---|---|---|
| FORM 未接 TO 驱动器 | Reliability-based TO（FORM→SIMP 体积二分） | `core/rbto.py` | D042 | 线性极限态 β=(d_allow−d_nom)/(cov·d_nom) 解析 |
| 张量热是 global k；各向异性热 TO 未接 | 逐单元各向异性热场 + 各向异性热 TO 灵敏度 | `core/thermal.py` / `thermal_simp.py` | D043 | uniform 场==global 1e-12 + 灵敏度 vs FD 1e-4 |
| 完整 TL 仅正向 | 几何非线性 TO（完整 TL 伴随灵敏度） | `core/nonlinear_simp.py` | D044 | TL 伴随 vs 中心差分 rel 2e-4（自伴随线性极限） |
| FORM 假设独立高斯 | Nataf 变换（相关 / 非高斯） | `core/reliability.py` | D045 | 相关高斯 β=(a₀−aᵀμ)/√(aᵀΣa) 1e-6 + 对数正态闭式 |
| NSGA 仅 proxy / 后处理 | NSGA-III 直接优化密度场 | `core/multi_objective_to.py` | D046 | 2D 超体积解析 + 累积存档单调 + 不支配梯度 SIMP |
| 阻尼频响仅正向 | 阻尼频响 TO（最小化动柔度） | `core/freq_response.py` | D047 | 动柔度自伴随灵敏度 vs FD 1e-5 + 削峰 |
| caps 是 centroid-fan（仅 star-convex） | Ear-clipping 通用多边形 STL + 孔洞 | `core/stl_export.py` | D048 | 凹/双孔面积守恒 1e-12 + 挤出水密 |

### 17.1 driver 层原则

- **driver = 正向求解器 + 解析灵敏度 + 约束更新**。v7 的可验证贡献集中在**灵敏度正确性**
  （全部 vs 中心差分或解析闭式），而非"造一个更强的优化器"——多处显式标注"这是灵敏度/
  能力，不是生产级 MMA/OC 优化器"（如 D044/D047）。
- **诚实优于吹嘘**：NSGA-III 密度场（D046）显式断言"梯度自由前沿不支配梯度 SIMP"，不假装
  超越；TL/动态 driver 用紧凑投影梯度而非完整 MMA，并在 ADR 写明边界。
- **向后兼容**：v7 全部 API 附加在 v6 之上（局部 import 复用 TL 内核、`solve_thermal` 场路径
  默认 None、`write_stl_marching_squares` 不动）；v4/v5/v6 调用与 rubric 无回归。
- **完成度门控**：`python scripts/test_agent.py --rubric v7` ≥99/100，v4/v5/v6 无回归 +
  pytest gate green（D033）+ 全永久红线保持。

### 17.2 v7 已知限制（诚实范围）

- RBTO 的可靠性旋钮是**体积分数**（compliance-min 拓扑对载荷尺度不变）；非线性极限态 RBTO
  是后续。
- TL / 动态 TO driver 是**紧凑投影梯度**（无密度滤波，非 MMA/OC），验证灵敏度驱动目标下降。
- Nataf 仅 normal / lognormal（有闭式等效相关）；混合相关直接拒绝；其余 marginal 需积分。
- NSGA-III 密度场是**梯度自由**能力，前沿粗糙，不与梯度 SIMP 竞速。
- Ear-clipping 是 O(n²) + 暴力可见性桥；`write_stl_marching_squares` 仍用 fan（凸 contour）。
- 详见 D042-D048 各自 "Honest scope notes" + "Reopening criteria"。

## 18. v8 — closing the loop: gradient drivers & general distributions

v7 把 v6 的严格正向求解器**接成了 driver**，但多处刻意停在"灵敏度正确 + 紧凑投影梯度"
而非完整闭环优化器，且分布/几何仍有简化。v8 = **把这些半成品 driver 闭成完整环**，并把
不确定性 / 几何提升到一般情形。每个 wave 都源自 v7（或更早）ADR 明列的 "Reopening
criteria"——§17.2 的限制由此逐条解除：

| v7 限制（§17.2） | v8 升级 | 模块 | ADR | 定量锚点 |
|---|---|---|---|---|
| TL TO 仅紧凑投影梯度 | 几何非线性 TO **完整 OC 环**（TL 伴随驱动 + 密度滤波） | `core/nonlinear_simp.py` | D050 | TL 端柔度单调下降 + 体积守恒 + TL-aware 比线性优化在 TL 柔度下更低 |
| 动态 TO 仅投影梯度、单 ω | 滤波**多频带** 动柔度 OC 环 | `core/freq_response.py` | D051 | 带平均 J 单调降 + 全带峰值下降 + Sigmund 滤波抑制 checkerboard |
| NSGA 随机初始、前沿粗 | **梯度种子** NSGA-III（warm-start） | `core/multi_objective_to.py` | D052 | 种子前沿超体积 > 随机（同预算）+ 梯度质量端点 |
| Nataf 仅 normal/lognormal | **一般 marginal** Nataf（Gauss-Hermite 积分） | `core/reliability.py` | D053 | GH 积分 vs 对数正态闭式 3e-11 + Weibull/Gumbel 矩与 round-trip |
| 各向异性热场固定 orientation | **纤维转向**热 TO（优化 orientation 场） | `core/thermal_simp.py` | D054 | orientation 灵敏度 vs FD 1e-9 + 各向同性基张量灵敏度恒零 + 转向降柔度 |
| FORM 仅单极限态 | **系统可靠性**（串/并联 Ditlevsen 界） | `core/reliability.py` | D055 | 二元正态 CDF 三精确特例 + 独立串联在界内且比简单界紧 + 正相关降串联失效 |
| caps 仅单环、无孔嵌套 | **MS 嵌套环 → ear-clipping 带孔封顶** | `core/stl_export.py` | D056 | 偶奇嵌套检测精确 + 面积=外环−内环 1e-9 + 洁净直角孔水密 |

### 18.1 闭环原则

- **driver 闭成环**：v8 把 v7 的"灵敏度 + 紧凑投影梯度"升级为**带密度滤波的 OC 环**
  （UU/VV），用单调下降 + 体积守恒 + 与基线对比的可量化差异作为锚点，而非只验灵敏度。
- **一般化优于特例**：分布从 normal/lognormal 闭式扩到任意 marginal 的 Gauss-Hermite Nataf
  积分（XX），可靠性从单极限态扩到系统串/并联 Ditlevsen 界（ZZ）。
- **诚实优于吹嘘**：系统可靠性显式标注 ρ=1 不精确退化（残差 ~2%）+ 并联仅 2 模式；
  带孔 STL 显式标注曲线孔零宽桥缝**非流形**、水密仅对洁净直角孔断言（D049 既有 polygon
  writer 同样限制，非 v8 引入的回归）。
- **向后兼容**：v8 全部 API 附加在 v7 之上（`nonlinear_to_oc` 复用 TL 伴随 + OC update +
  滤波；`build_nataf_general` 对 normal-normal 走闭式、其余走 GH；`write_stl_smooth_holes`
  不动既有 `write_stl_marching_squares` / `write_stl_polygon`）；v4/v5/v6/v7 调用与 rubric 无回归。
- **完成度门控**：`python scripts/test_agent.py --rubric v8` ≥99/100，v4/v5/v6/v7 无回归 +
  pytest gate green（D033）+ 全永久红线保持。

### 18.2 v8 已知限制（诚实范围）

- 几何非线性 OC 环用单一移动极限 OC update（与线性 SIMP 同款），未上 MMA；大变形与线性
  拓扑的差异在默认载荷 + 充分迭代下稳健，截断环可能反号（见 D050）。
- 多频带动态 TO 在共振附近灵敏度可变号，用投影梯度而非 OC（D051）。
- 梯度种子 NSGA-III 仍是梯度自由细化，端点由种子的梯度质量决定，不与梯度 SIMP 竞速（D052）。
- 一般 Nataf 用 24 节点 Gauss-Hermite + 二分求等效相关；极端尾部相关可能需更多节点（D053）。
- 系统可靠性：串联任意 m，**并联仅 2 模式**（m>2 需多元正态 CDF）；ρ 钳到 0.999999（D055）。
- 带孔 STL：曲线（多顶点）孔零宽桥缝非流形，水密仅断言洁净直角孔；slit-free 约束 Delaunay
  是 reopening 项（D056）。
- 详见 D050-D056 各自 "Honest scope notes" + "Reopening criteria"。

## 19. v9 — second-order drivers: constrained optimisers & coupled fields

v8 把 v7 的灵敏度闭成 OC 环并把分布/几何一般化，但多处仍停在**单移动极限 OC / 单场 / 独立优化 /
桥缝几何**。v9 = **把这些 driver 升到二阶**：真正的约束优化器（MMA）、多场交替最小化、几何鲁棒化、
可靠性从评估升成驱动 TO。每个 wave 都源自 v8（或更早）ADR 明列的 "Reopening criteria"——§18.2 的
限制由此逐条解除：

| v8 限制（§18.2） | v9 升级 | 模块 | ADR | 定量锚点 |
|---|---|---|---|---|
| TL TO 仅单移动极限 OC | **MMA** 约束优化器驱动 TL 非线性 TO | `core/nonlinear_simp.py` | D058 | MMA/OC 柔度比 0.946（同体积竞争）+ 体积可行 + 单调 |
| 频域 TO 仅受迫响应 | 特征频率**带隙** / minimax 频带（建在 modal solver） | `core/freq_response.py` | D059 | 带隙灵敏度 vs FD 1.76e-6（特征值灵敏度精确）+ 爬升加宽 2.2× |
| NSGA 仅 2 目标 | **≥3 目标多载况** NSGA-III + 种子（精确 n-D HSO 超体积） | `core/multi_objective_to.py` | D060 | HSO vs 2D + 容斥 + Das-Dennis C(d+2,2) + 载况真冲突 + 种子 HV+28% |
| Nataf 仅边缘+相关 | **Rosenblatt** 变换（已知联合分布条件 CDF） | `core/reliability.py` | D061 | Rosenblatt == Cholesky 白化 1e-10 + 去相关 Cov(U)=I + FORM β 闭式 |
| 单场 orientation 固定 | **耦合**密度 + orientation 热 TO（交替最小化） | `core/thermal_simp.py` | D062 | 耦合 ≤ 单独密度（3.1×）且 ≤ 单独 orientation（17×）+ 各向同性退化精确 |
| 可靠性仅单极限态评估 | **系统可靠性驱动 TO**（驱动到目标系统 β） | `core/rbto.py` | D063 | 达标系统 β + β_sys<min 单模 + 单模退化到 D042 + 在 D055 Ditlevsen 界内 |
| 带孔 STL 桥缝非流形 | **slit-free** 孔三角化（曲线孔鲁棒水密） | `core/stl_export.py` | D064 | 环形孔水密=True（AAA=False）+ 面积=实心格数×格面积 + 多拓扑皆水密 |

### 19.1 二阶 driver 原则

- **约束优化器 + 多场耦合**：MMA（D058）替代单移动极限 OC，交替最小化（D062）耦合密度与
  orientation 两场，系统可靠性（D063）把 D042 单模态 RBTO 升成多模态系统 β 驱动。
- **几何鲁棒化优于平滑**：slit-free cell 三角化（D064）牺牲平滑边界换取曲线孔的鲁棒水密——
  与 D056 平滑但脆弱的桥缝互补；两者都不是"平滑且鲁棒"（需 MS 轮廓 CDT，reopening）。
- **诚实优于吹嘘**：MMA 在 compliance-only 上只是与 OC 竞争（≈0.95×，非碾压），真优势是多约束；
  耦合是块坐标交替（非同时 MMA）；系统可靠性模态视为独立；slit-free 对角 pinch 如实报非水密。
- **向后兼容**：v9 全部 API 附加在 v8 之上（`mma_nonlinear_to` 复用 D044 TL 伴随；`multi_load_case_to`
  复用 pareto_nsga 助手；`RosenblattTransform` 镜像 NatafTransform 接口；`coupled_*` 局部 import；
  `write_stl_slit_free_holes` 不动 D056 路径）；v4-v8 调用与 rubric 无回归。
- **完成度门控**：`python scripts/test_agent.py --rubric v9` ≥99/100，v4/v5/v6/v7/v8 无回归 +
  pytest gate green（D033）+ 全永久红线保持。

### 19.2 v9 已知限制（诚实范围）

- MMA-TL 只接了体积约束（`mma_step` 多约束能力未用）；compliance-only 上 MMA≈OC（D058）。
- 带隙假设**非重根**（重根处灵敏度是次梯度集）；投影梯度爬升非 MMA；未做目标频带放置（D059）。
- 多目标仍**梯度自由**（种子注入梯度端点）；HSO 是 O(k^{n−1})，不适合多目标大前沿（D060）。
- Rosenblatt 仅 **MVN 联合**；高斯 copula 退化到 Nataf；非高斯联合是 reopening（D061）。
- 耦合是**块坐标交替**（非同时 (ρ,θ) MMA）；无角度场制造约束（D062）。
- 系统可靠性模态视为**独立**；可靠性旋钮仍是体积分数；线性位移极限态（D063）。
- slit-free 仅**边连通**区域水密（对角 pinch 非流形）；阶梯边界非平滑（D064）。
- 详见 D058-D064 各自 "Honest scope notes" + "Reopening criteria"。

## 20. v10 — constraint-rich & manufacturable: 多约束优化器 + 一般 copula + 平滑水密几何

v9 把 driver 升到二阶，但多处仍是**单约束 / 高斯 copula / 块坐标 / 阶梯几何**。v10 = **约束丰富 +
可制造**：把这些推进到多约束优化器（stress constraint alongside volume）、一般 Archimedean copula、
同时多场 MMA、平滑且水密的几何。每个 wave 都源自 v9（或更早）ADR 明列的 "Reopening criteria"——§19.2 的
限制由此逐条解除：

| v9 限制（§19.2） | v10 升级 | 模块 | ADR | 定量锚点 |
|---|---|---|---|---|
| MMA 仅体积约束 | **多约束 MMA**：应力 p-norm constraint + 体积 | `core/nonlinear_simp.py` + `core/stress.py` | D066 | 应力 p-norm 伴随灵敏度 vs FD ~1e-7 + 两约束同时满足 + 应力绑定 6.56e3→4.59e3 |
| 频域仅带隙（推开特征值） | **目标频带放置**（minimax around target） | `core/freq_response.py` | D067 | 带内峰值灵敏度 vs FD ~1e-7 + 最坏响应 −84% + 体积守恒 |
| 两个并行 NSGA 循环 | **泛化 nsga3_density_to** + IGD⁺ 指标 | `core/multi_objective_to.py` | D068 | 2/3-obj 委托**逐位一致** + IGD⁺ 解析前沿 δ→IGD⁺=δ |
| Rosenblatt 仅 MVN | **Archimedean copula**（Clayton/Frank）Rosenblatt | `core/reliability.py` | D069 | 条件 CDF round-trip ≤1e-9 + θ→0 退化独立 + Kendall τ 闭式 |
| 耦合是块坐标交替 | **同时 (ρ,θ) MMA** | `core/thermal_simp.py` | D070 | 合并灵敏度 vs FD ~1e-8 + 同时 ≤ 交替（−19%）+ 体积可行 |
| 系统模态视为独立 | **相关系统模态**驱动 TO | `core/rbto.py` | D071 | ρ=0 退化独立 <1e-9 + 正相关升 β_sys + bivariate CDF Φ₂ |
| slit-free 阶梯非平滑 | **平滑且水密**带孔三角化（annulus ribbon） | `core/stl_export.py` | D072 | 平滑环形孔水密=True + 面积≈外−内 ≤5e-3 + 每边恰 2 三角 |

### 20.1 约束丰富 + 可制造原则

- **多约束优化器**：D066 把 MMA 从单体积约束升到 stress-constrained（应力 p-norm 伴随 + 体积），
  这是 MMA 相对 OC 的真正价值兑现；D070 把块坐标交替升成同时 (ρ,θ) MMA（联合步逃离坐标式驻点）。
- **一般不确定性**：D069 用 Archimedean copula（Clayton/Frank）表达尾部相关（高斯 copula 不能），
  D071 用 bivariate normal CDF 把系统可靠性从独立升到相关模态。
- **可制造几何**：D072 用 annulus ribbon 把"平滑（MS 轮廓）"与"水密（边流形）"同时拿下（环形孔），
  补上 D056（平滑非水密）与 D064（水密非平滑）的缺口。
- **DRY 与保行为**：D068 把两个并行 NSGA 循环收成单个泛化 `nsga3_density_to`，并以**逐位一致** golden
  baseline 证明重构不改行为。
- **诚实优于吹嘘**：D066 是 raw 应力（非 SIMP-松弛，不处理应力奇异性）；D067 是平滑 minimax（非精确 max）；
  D070 "≤交替"是经验非定理；D071 单标量等相关 + Ditlevsen 界中点；D072 仅 annulus（多孔需 CDT）。
- **向后兼容**：v10 全部 API 附加在 v9 之上（`stress_pnorm_sensitivity` 复用 FEM 后端；`multi_objective_to`/
  `multi_load_case_to` 委托 `nsga3_density_to`；`CopulaRosenblattTransform` 镜像 RosenblattTransform 接口；
  `correlated_system_rbto_simp` 并行 `system_rbto_simp` 不改 HHH）；v4-v9 调用与 rubric 无回归。
- **完成度门控**：`python scripts/test_agent.py --rubric v10` ≥99/100，v4-v9 无回归 + pytest gate
  green（D033）+ 全永久红线保持。

### 20.2 v10 已知限制（诚实范围）

- 多约束 MMA 用 **raw von Mises p-norm**（非 SIMP-松弛），不解应力奇异性；目标是线性柔度非全 TL（D066）。
- 目标频带是**平滑 minimax**（p-norm 非精确 max）+ 固定频带采样（不自适应跟踪移动共振）（D067）。
- NSGA 重构是**保行为 DRY**（NSGA-III 本身不变，仍梯度自由）；IGD⁺ 需调用方提供参考前沿（D068）。
- copula 仅**双变量** + 仅 Clayton/Frank（Gumbel 无闭式逆）；假设联合已知不拟合（D069）。
- 同时 MMA 仅**热**柔度；θ 未滤波；"≤交替"经验非定理（D070）。
- 相关系统仅**单标量等相关** + Ditlevsen 界中点（≥3 模态带界差）；ρ∈[0,1)（D071）。
- 平滑水密仅 **annulus（单孔/区域）**；轮廓重采样（面积"≈"）；水密是拓扑（强偏心孔 rung 可能几何自交）（D072）。
- 详见 D066-D072 各自 "Honest scope notes" + "Reopening criteria"。

## 21. v11 — exact & robust: 应力奇异性松弛 + 一般 copula 维度 + 精确系统积分 + 约束 Delaunay

v10 把 driver 升到约束丰富 + 可制造，但多处仍是**未处理应力奇异性 / 仅双变量 copula / 界中点近似 / 单孔
几何 / 一阶投影梯度**。v11 = **精确化 + 鲁棒化（exact & robust）**：每个 wave 追溯到一条 v10（或更早）
ADR 明列的 "Reopening criteria"——§20.2 的限制由此逐条解除：

| v10 限制（§20.2） | v11 升级 | 模块 | ADR | 定量锚点 |
|---|---|---|---|---|
| raw 应力不解奇异性 | **qp-relaxed 应力**（σ̃=ρ^q·σ_vm）约束 MMA | `core/stress.py` + `core/nonlinear_simp.py` | D074 | qp 灵敏度 vs central-FD ≤1e-4（显式+隐式）+ 松弛按 ρ^q 抑制奇异性 + 双约束绑定。屈曲驱动 **deferred**（分析级灵敏度探针 λ 20.1→8.1）|
| 固定频带采样 + peak 作目标 | **自适应采样 + peak-as-constraint** | `core/freq_response.py` | D075 | 自适应 25 evals 还原 dense-400 峰 0.015% vs uniform-7 漏 41% + peak 约束绑定 3.99e5→2.23e4 |
| IGD⁺ 需参考前沿 | **reference-free 指标**（R2 + 自动参考点 HV）| `core/multi_objective_to.py` | D076 | R2 闭式 5/6 + 弱 Pareto 兼容 + R2/refHV/IGD⁺ 排序一致 [3,2,1,0] |
| 仅双变量 Clayton/Frank | **Gumbel + d 维交换 Clayton** | `core/reliability.py` | D077 | Gumbel 条件 vs ∂C/∂u₁ ≤1e-6 + d 维条件 = 混合偏导比值 ≤1e-5 + round-trip ≤1e-9 |
| Ditlevsen 界（双变量拼） | **Genz 精确多元系统 P_f**（全相关矩阵）| `core/reliability.py` | D078 | Genz→m=2 对精确 Φ₂ ≤1e-3 + R=I 精确 ΠΦ ≤1e-12 + 精确 P_f 落 Ditlevsen 界内 |
| 同时 MMA 仅热 | **弹性正交各向异性同时 (ρ,θ) + fibre 连续性** | `core/orthotropic_simp.py` | D079 | iso ke 复现闭式 ≤1e-9 + dC/dρ·dC/dθ vs FD ≤1e-4 + 连续性约束绑定 0.46→0.14 |
| 平滑水密仅 annulus | **约束 Delaunay 多孔**平滑+水密 | `core/stl_export.py` | D080 | 2/3 孔水密（每边恰 2 facet）+ 面积≈外−Σ孔 ≤1% + 边界边==环边 |

### 21.1 exact & robust 原则

- **精确化**：D078 用 Genz 分离变量 MC 把系统 P_f 从 Ditlevsen **界**升到**精确**多元 Φ_m（全相关矩阵）；
  D076 把质量指标从需参考前沿的 IGD⁺ 升到 reference-free 的 R2 + 自动参考点 HV。
- **鲁棒化**：D074 用 qp 松弛解经典应力奇异性（低密度单元 σ̃→0）；D075 自适应采样捕获固定网格漏掉的尖锐
  共振，并把 peak 从目标升为约束；D080 用约束 Delaunay 解 D072 的单孔限制（任意多孔水密）。
- **一般化**：D077 把 copula 从双变量 Clayton/Frank 升到 Gumbel（上尾相依）+ d 维交换 Clayton（闭式生成元
  导数）；D079 把同时 (ρ,θ) MMA 从热升到弹性正交各向异性 + fibre 连续性约束。
- **诚实优于吹嘘**：D074 屈曲驱动**deferred**（分析级 buckling_sensitivity 探针显示 ascent 反把 λ 拉低，绝不
  谎称可用）；D075 单频约束会被失谐白嫖故用频带 + 必须阻尼；D076 排序一致是经验非定理；D077 Gumbel 逆是
  二分非闭式、d 维仅交换 Clayton；D078 是 MC 估计非闭式、朴素非点阵；D079 连续性非周期感知、MMA 非凸；
  D080 无 flip 约束恢复（失败显式报错）。

### 21.2 v11 已知限制（诚实范围）

- qp 松弛 q=2.5/p=8 非自调；**屈曲约束驱动 deferred**（D074 reopening，附 λ-drop 探针证据）。
- 自适应采样是**贪心二分非全局** band-max 证明；MMA 内每步用固定 band_omegas（D075）。
- R2 比较多前沿须共享 ideal+weights；排序一致是良构嵌套前沿经验等价（D076）。
- Gumbel 逆是**二分非闭式**；d 维仅**交换 Clayton**（非嵌套/非 d 维 Gumbel/Frank）（D077）。
- Genz 是 **MC 估计**（n_samples→∞ 收敛）+ 朴素 MC（非 Korobov 点阵）+ R 须 SPD（D078）。
- 弹性 (ρ,θ) 连续性度量**非周期感知**（±89° 误罚）+ 单层平面 + MMA 非凸（D079）。
- 约束 Delaunay **无 flip 恢复**（稀疏/强非凸边界显式报错非默默非水密）+ O(n²) + 拓扑水密（D080）。
- 详见 D074-D080 各自 "Honest scope notes" + "Reopening criteria"。
