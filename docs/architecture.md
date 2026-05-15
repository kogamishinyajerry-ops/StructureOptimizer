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
