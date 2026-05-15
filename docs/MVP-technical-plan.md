# StructureOptimizer MVP 技术方案

日期：2026-05-12  
状态：第一版技术方案  
对应 PRD：`docs/PRD-v0.1.md`

## 1. 技术目标

MVP 要交付一个可运行、可测试、可审计的结构优化最小闭环：

```text
benchmark config -> mesh/model -> baseline FEA -> SIMP optimization -> candidate -> independent verification -> report
```

第一版优先保证正确的工程主线，而不是追求复杂 CAD、复杂 3D 或完整工业求解器适配。

## 2. 技术原则

- 本地优先：所有 MVP 功能能在本地运行，不依赖云服务。
- 配置优先：每个基准由显式配置驱动，避免硬编码隐藏工况。
- 验证优先：优化结果必须重新验证，不能只展示迭代过程指标。
- 适配器边界清晰：优化器、FEA 求解器、文件输出分层，后续可替换。
- 小步实现：先跑通 2D 标准问题，再扩展简化 3D。

## 3. 推荐目录结构

```text
StructureOptimizer/
  docs/
    PRD-v0.1.md
    MVP-technical-plan.md
  studies/
    simple_bracket_tradeoff.json
  research/
    industrial-structural-optimization-report.md
  structure_optimizer/
    __init__.py
    cli.py
    benchmarks/
      registry.py
      configs/
        mbb_beam.json
        cantilever.json
        l_bracket.json
        loaded_hook.json
        simple_bracket.json
    core/
      config.py
      mesh.py
      material.py
      loadcase.py
      fem2d.py
      simp.py
      filtering.py
      verification.py
      reporting.py
      study.py
      run_store.py
    adapters/
      optimizer_base.py
      solver_base.py
      file_export.py
    visualization/
      density_plot.py
      convergence_plot.py
  tests/
    test_config_validation.py
    test_mbb_beam_smoke.py
    test_run_verify_report.py
  runs/
    .gitkeep
```

`runs/` 存放本地运行产物，后续可默认加入 `.gitignore`。如果项目一开始不建完整包结构，也应保留相同的概念边界。

## 4. 数据模型

### 4.1 BenchmarkConfig

必需字段：

```json
{
  "name": "mbb_beam",
  "dimension": "2d",
  "units": "mm_N_MPa",
  "mesh": {
    "type": "structured_quad",
    "nelx": 120,
    "nely": 40
  },
  "material": {
    "young_modulus": 210000.0,
    "poisson_ratio": 0.3,
    "density": 7.85e-9
  },
  "boundary_conditions": [],
  "loads": [],
  "optimization": {
    "objective": "min_compliance",
    "volume_fraction": 0.4,
    "penalty": 3.0,
    "filter_radius": 1.5,
    "max_iterations": 120,
    "change_tolerance": 0.01
  }
}
```

配置校验规则：

- `volume_fraction` 必须在 `(0, 1]`。
- `young_modulus`、`density`、`penalty`、`filter_radius` 必须为正数。
- 2D 结构网格的 `nelx`、`nely` 必须为正整数。
- 至少有一个载荷和一个位移约束。
- 载荷和约束引用的节点、边或区域必须能在网格中解析。

### 4.2 RunSummary

每次运行生成：

```json
{
  "run_id": "20260512-184500-mbb_beam",
  "benchmark": "mbb_beam",
  "input_hash": "sha256:...",
  "status": "completed",
  "iterations": 87,
  "baseline": {
    "mass": 1.0,
    "compliance": 123.4,
    "max_displacement": 0.12
  },
  "optimized": {
    "mass": 0.4,
    "compliance": 145.6,
    "max_displacement": 0.18
  },
  "verification": {
    "status": "passed",
    "volume_fraction_ok": true,
    "connectivity_ok": true
  }
}
```

### 4.3 v0.3 工程约束对象

v0.3 在不引入 CAD、外部网格器或外部求解器的前提下，增加结构化网格上的工程语义：

```json
{
  "design_space": {
    "frozen_solid": [
      {"name": "support_band", "selector": {"type": "box", "x": [0.0, 0.1], "y": [0.0, 1.0]}}
    ],
    "void": [
      {"name": "bottom_clearance", "selector": {"type": "box", "x": [0.42, 0.58], "y": [0.0, 0.18]}}
    ]
  },
  "load_cases": [
    {"name": "downward_tip", "weight": 0.8, "loads": [{"selector": "right_mid", "fx": 0.0, "fy": -300.0}]},
    {"name": "side_top", "weight": 0.2, "loads": [{"selector": "top_mid", "fx": 120.0, "fy": 0.0}]}
  ]
}
```

规则：

- `frozen_solid` 单元在优化过程中保持 `density = 1.0`。
- `void` 单元在优化过程中保持 `density = min_density`，质量统计按空区处理。
- `frozen_solid` 与 `void` 不允许重叠。
- 多载荷工况使用权重归一化后的 weighted compliance 作为优化柔度。
- 旧的单一 `loads` 配置继续兼容；没有 `load_cases` 时自动视为 `primary` 工况。

## 5. 算法主线

### 5.1 2D FEM 主线

第一版实现线弹性小变形平面应力或平面应变模型：

- structured quadrilateral mesh。
- 每个单元一个密度变量。
- 全局刚度矩阵装配。
- Dirichlet 约束消元。
- 线性方程求解。
- 输出位移、柔度、近似单元应力。

第一版允许使用 NumPy/SciPy。若依赖尚未确定，先在技术 spike 中确认本地环境和许可。

### 5.2 SIMP 优化主线

目标：

```text
minimize compliance = F^T U
subject to volume_fraction <= target
```

实现步骤：

1. 初始化所有设计单元密度为目标体积分数。
2. 每轮根据密度插值单元刚度。
3. 运行 FEA 得到位移。
4. 计算柔度和灵敏度。
5. 对灵敏度执行密度过滤。
6. 用 OC update 或等价稳定更新法更新密度。
7. 记录迭代指标。
8. 达到 `change_tolerance` 或 `max_iterations` 后停止。

默认参数：

- `volume_fraction`: 0.4
- `penalty`: 3.0
- `filter_radius`: 1.5
- `max_iterations`: 120
- `change_tolerance`: 0.01
- `min_density`: 0.001

### 5.3 简化 3D 范围

MVP 不要求完整 3D 工业能力。简化 3D 只做以下二选一：

- 方案 A：提供 `simple_bracket` 的 2.5D 厚度模型，把 2D 结果映射为带厚度的质量估算。
- 方案 B：提供 3D 数据模型和 adapter 接口，但不承诺 3D 优化主线完整收敛。

推荐先选方案 A，避免 3D FEM 和可视化拖慢 MVP。

## 6. 验证闭环

验证必须独立于优化主循环输出。

验证步骤：

1. 读取最终密度场。
2. 以阈值或连续密度方式重建验证模型。
3. 使用相同载荷和约束重新运行 FEA。
4. 计算质量、体积分数、柔度、最大位移和近似最大应力。
5. 检查连通性、frozen/void mask、孤立材料和粗制造性风险。
6. 输出 `verification.json`。

第一版通过条件：

- 体积分数不超过目标值 + 2% 绝对容差。
- 最终模型存在从载荷区到支撑区的材料连通路径。
- frozen solid 区保持实心，void 区保持空区。
- FEA 求解成功，矩阵没有奇异失败。
- 最大位移、柔度、质量都成功写入报告。

失败状态必须可解释：

- `invalid_config`
- `solver_failed`
- `singular_matrix`
- `volume_constraint_failed`
- `connectivity_failed`
- `design_space_constraint_failed`
- `report_failed`

`verification.json` 还必须输出：

- `objective`：当前优化目标，例如 `compliance` 或 `weighted_compliance`。
- `responses`：质量、柔度、最大位移、近似最大应力。
- `constraints`：每条约束的 `name`、`value`、`limit`、`unit`、`source`、`status`。
- `load_cases`：多载荷工况的 baseline/candidate 独立验证指标。

## 7. 报告输出

每次运行的 `report.md` 必须包含：

- 运行 ID、时间、输入 hash。
- 基准名称、网格规模、材料、载荷、约束。
- 优化参数和停止原因。
- 迭代表格摘要。
- Objective、Responses、Constraints 分层表格。
- 基线 vs 优化后 vs 验证后指标。
- 多载荷工况验证指标，如果配置了 `load_cases`。
- 图片引用：`density.png`、`convergence.png`。
- 限制说明：2D/简化模型不等于工业认证。

## 8. 测试策略

### 8.1 单元测试

必须覆盖：

- 配置校验拒绝非法 `volume_fraction`。
- 配置校验拒绝缺失载荷或约束。
- structured 2D mesh 的节点/单元数量正确。
- 简单 FEM 模型能求解非零位移。
- SIMP 更新后密度仍在 `[min_density, 1]`。

### 8.2 集成测试

必须覆盖：

- `mbb_beam` smoke run 在小网格上退出 0。
- run 产物包含 `input.json`、`metrics.csv`、`density.png`、`verification.json`、`report.md`。
- verify 阶段能重新读取运行目录并生成验证结果。
- report 阶段不会把优化迭代指标误标为独立验证指标。
- study 阶段能批量执行候选、生成 `candidates.csv` 和 `study.html`，且不破坏现有 run -> verify -> report 路径。

### 8.3 性能约束

建议 smoke 配置：

- `mbb_beam`: `nelx=30`, `nely=10`, `max_iterations=10`
- 本地普通开发机 30 秒内完成。

完整 demo 配置可更大，但不能作为 CI 的唯一验证。

## 9. 实现切片

### Slice 1：项目骨架与配置校验

交付：

- Python 包结构。
- 基准配置 registry。
- `BenchmarkConfig` loader 和 validator。
- `mbb_beam`、`cantilever` 小网格配置。
- 配置校验测试。

验收命令：

```bash
python -m pytest tests/test_config_validation.py
```

### Slice 2：2D FEM 基线求解

交付：

- structured quad mesh。
- 线弹性 FEM 装配和求解。
- 基线质量、柔度、最大位移指标。
- 小网格 smoke test。

验收命令：

```bash
python -m pytest tests/test_mbb_beam_smoke.py
```

### Slice 3：SIMP 优化循环

交付：

- 密度初始化。
- SIMP 刚度插值。
- 灵敏度计算。
- 密度过滤。
- OC update。
- `metrics.csv`。

验收标准：

- 小网格 `mbb_beam` 至少完成 10 次迭代。
- 体积分数接近配置目标。
- 柔度和密度变化写入指标文件。

### Slice 4：结果输出与可视化

交付：

- run directory。
- `input.json`。
- `density.npy`。
- `density.png`。
- `convergence.png`。

验收标准：

- 运行目录文件齐全。
- 图片非空。
- 重复运行不会覆盖旧结果。

### Slice 5：验证闭环

交付：

- `verify` 命令或函数。
- `verification.json`。
- 连通性检查。
- 基线/候选/验证指标对比。

验收标准：

- 验证失败有明确状态码。
- 报告区分优化指标和验证指标。

### Slice 6：报告生成

交付：

- `report.md`。
- 运行摘要。
- 输出文件索引。
- 限制说明。

验收命令：

```bash
python -m pytest tests/test_run_verify_report.py
```

### Slice 7：本地参数 study 与候选对比

交付：

- `studies/simple_bracket_tradeoff.json`。
- `python -m structure_optimizer study --config studies/simple_bracket_tradeoff.json`。
- `runs/studies/<study_id>/study_input.json`。
- `runs/studies/<study_id>/candidates.csv`。
- `runs/studies/<study_id>/study.html`。
- 每个 `candidate_###/` 目录复用标准 run 产物：`input.json`、`metrics.csv`、`density.png`、`verification.json`、`report.md`。

当前支持的 study 参数：

- `volume_fraction`
- `filter_radius`
- `load_weights.<load_case_name>`

验收命令：

```bash
python -m pytest tests/test_study.py
python -m structure_optimizer study --config studies/simple_bracket_tradeoff.json
```

## 10. 依赖建议

第一版可考虑：

- Python 3.11+。
- NumPy。
- SciPy。
- Matplotlib。
- Pydantic 或 dataclasses + 手写校验。
- pytest。

依赖选择规则：

- 新依赖必须解决真实问题。
- 不引入 CAD 内核依赖。
- 不引入云服务 SDK。
- 不引入 GPL 组件到核心路径，除非明确接受许可影响。

## 11. 验收总线

MVP 完成的最低验收：

```bash
python -m pytest
python -m structure_optimizer run --benchmark mbb_beam --preset smoke
python -m structure_optimizer verify --run runs/mbb_beam/<latest>
python -m structure_optimizer report --run runs/mbb_beam/<latest>
python -m structure_optimizer study --config studies/simple_bracket_tradeoff.json
```

全部通过后，检查：

- `runs/mbb_beam/<latest>/input.json` 存在。
- `runs/mbb_beam/<latest>/metrics.csv` 存在。
- `runs/mbb_beam/<latest>/density.png` 存在且非空。
- `runs/mbb_beam/<latest>/convergence.png` 存在且非空。
- `runs/mbb_beam/<latest>/verification.json` 存在且 `status` 为 `passed` 或明确失败原因。
- `runs/mbb_beam/<latest>/report.md` 存在。
- `runs/studies/<latest>/candidates.csv` 和 `runs/studies/<latest>/study.html` 存在且非空。

## 12. 下一步建议

当前最小主线已经覆盖 Slice 1-7。下一步建议把 study 页面和单次 demo 页面统一成更强的“候选评审包”，但仍保持本地静态 HTML、结构化输出和 2D/2.5D 限制说明。
