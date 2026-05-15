# StructureOptimizer 开源对标路线图

日期：2026-05-15  
依据：`research/hypermesh-hyperworks-optimization-architecture.md`、`research/open-source-hypermesh-alternatives-deep-dive.md`  
状态：v0.3 已落地，v0.4 最小本地 study runner 已落地

## 1. 定位

StructureOptimizer 不追求复制 HyperMesh。短中期目标是做一个本地、可验证、可解释的结构优化工作台。

开源对标链路：

```text
SALOME -> 工程对象、几何/网格/分组/质量检查
OpenPISCO -> 拓扑优化问题、design space、criteria、solver adapter
OpenMDAO -> study driver、DOE、参数探索、记录与批量执行
ParaView/Gmsh -> 后处理和外部网格生态
```

## 2. v0.3 目标：工程约束内生化

v0.3 的目标是让优化问题具备工程语义，而不是只输出一个密度图。

核心对象：

- `DesignSpace`: 设计域、保留实心区、禁入/空区。
- `RegionSelector`: 基于结构化网格的命名区域选择器。
- `LoadCaseSet`: 多载荷工况和权重。
- `Criterion`: 可作为 objective、constraint、response、warning 的统一指标。
- `ConstraintStatus`: 约束的值、限值、单位、状态和来源。

必须保持：

- 仍然只做 2D structured quadrilateral FEM 和当前 2.5D simple_bracket 报告。
- 不引入 CAD、外部网格器、外部求解器、GUI、全 3D。
- 现有 `run`、`verify`、`report`、`demo` CLI 不破坏。

## 3. v0.3 最小功能清单

1. 配置支持 `design_space`：

```json
{
  "design_space": {
    "frozen_solid": [{"name": "load_pad", "selector": {"type": "box", "x": [0.85, 1.0], "y": [0.45, 0.55]}}],
    "void": [{"name": "clearance", "selector": {"type": "circle", "center": [0.5, 0.5], "radius": 0.08}}]
  }
}
```

2. SIMP 更新遵守 mask：

```text
frozen_solid -> density = 1.0
void -> density = min_density
design -> normal SIMP update
```

3. 多载荷工况：

```text
weighted_compliance = sum(loadcase_weight_i * compliance_i)
```

4. 报告输出分层：

```text
Objective
Responses
Constraints
Independent verification
Manufacturability warnings
```

5. `verification.json` 统一 schema：

```json
{
  "constraints": [
    {
      "name": "volume_fraction",
      "value": 0.402,
      "limit": 0.42,
      "unit": "ratio",
      "source": "independent_verification",
      "status": "passed"
    }
  ]
}
```

## 4. v0.4 目标：本地 study 与候选对比

v0.4 的目标是对标 HyperStudy/OpenMDAO 的最小能力：批量探索设计参数，并用工程指标比较候选。

新增 CLI：

```bash
python -m structure_optimizer study --config studies/simple_bracket_tradeoff.json
```

输入：

```json
{
  "benchmark": "simple_bracket",
  "preset": "demo",
  "parameters": {
    "volume_fraction": [0.3, 0.4, 0.5],
    "filter_radius": [1.5, 2.0]
  },
  "ranking": ["verification_status", "mass", "compliance", "max_displacement"]
}
```

输出：

```text
runs/studies/<study_id>/
  study_input.json
  candidates.csv
  study.html
  candidate_001/
  candidate_002/
```

## 5. v0.4 最小功能清单

当前已实现：

1. 参数矩阵生成。
2. 对每个候选执行 run -> verify -> report。
3. 生成 `candidates.csv`。
4. 生成 `study.html`，包含：
   - 候选排名。
   - mass / volume fraction。
   - compliance。
   - max displacement。
   - verification status。
   - manufacturability warning count。
5. 不引入 OpenMDAO 依赖，只学习其 Problem/Driver/Recorder 思路。

## 6. v0.5 以后再考虑

- Gmsh / meshio adapter。
- VTK/VTU field export。
- ParaView runbook。
- SALOME MED import/export spike。
- Code_Aster / CalculiX adapter spike。
- Dakota 或 OpenMDAO 正式集成。

这些不应进入 v0.3/v0.4 的核心路径。

## 7. 推荐下一步

下一条重大 goal 建议做 v0.5 的“评审包收敛”：把单次 `demo.html` 和批量 `study.html` 的叙事、指标解释、候选链接和限制说明统一，形成可以直接给工程评审看的本地静态包。

仍然不要在这一阶段引入 CAD、GUI、云服务、完整 3D FEM 或商业求解器适配。
