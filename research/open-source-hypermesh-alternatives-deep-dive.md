# 开源项目如何对标 HyperMesh / HyperWorks：OpenPISCO + SALOME + OpenMDAO 深度拆解

调研日期：2026-05-15  
对象：OpenPISCO、SALOME、OpenMDAO，并参考 Gmsh、Dakota、ParaView、Code_Aster、CalculiX  
目的：找出可被 StructureOptimizer 借鉴的开源 CAE/优化链路，避免把目标误设成“复制 HyperMesh 单体软件”。

## 1. 一句话结论

没有一个开源单体项目能完整对标 HyperMesh / HyperWorks。更现实的对标方式是一条开源工具链：

```text
SALOME / Gmsh / FreeCAD
-> mesh and selector model
-> Code_Aster / CalculiX / internal FEM
-> OpenPISCO topology optimization concepts
-> OpenMDAO / Dakota design exploration
-> ParaView / VTK post-processing
```

对 StructureOptimizer 来说，最值得立即学习的不是完整 CAD 或 GUI，而是三层架构：

```text
SALOME: 工程对象、几何/网格/分组/质量检查
OpenPISCO: 优化问题、设计域、criteria、solver adapter
OpenMDAO: study driver、DOE、参数探索、可记录的批量执行
```

这三者合起来，才接近 HyperMesh + OptiStruct + HyperStudy 的开源替代路线。

## 2. 对标 HyperMesh 时不能只看“拓扑优化算法”

HyperMesh 强在工程链路，不是只强在 SIMP 或某个优化器：

```text
CAD/几何清理
-> 网格生成与编辑
-> 材料/属性/载荷/约束/工况管理
-> design space / non-design space
-> solver deck / solver adapter
-> 目标、响应、约束
-> 制造约束
-> 后处理、报告、动画
-> 批量 study / DOE / 鲁棒设计
```

所以开源对标也必须拆成层：

| HyperWorks 层 | 开源候选 | 对 StructureOptimizer 的意义 |
| --- | --- | --- |
| HyperMesh 前处理 | SALOME, Gmsh, FreeCAD FEM, PrePoMax | 几何、网格、分组、质量检查、Python 自动化 |
| OptiStruct 优化求解 | OpenPISCO, OpenLSTO, 自研 SIMP, Code_Aster/CalculiX 适配 | 设计域、criteria、约束、solver adapter |
| HyperStudy 设计探索 | OpenMDAO, Dakota | 批量运行、DOE、参数敏感性、代理模型、鲁棒性 |
| HyperView 后处理 | ParaView, VTK, PyVista | 结果场、动画、并排比较、工程报告 |

## 3. OpenPISCO：最值得研究的开源拓扑优化平台

### 3.1 它强在哪里

OpenPISCO 是一个面向拓扑优化的研发平台，核心不是单个 SIMP 脚本，而是一套模块化优化框架：

- 支持 grids、unstructured meshes、body-fitted meshes。
- 提供 GUI、命令行 OpenPiscoCL、Python API。
- 主要用 Python 编写，并可对接外部有限元/有限体积求解器。
- 以 level set 方法为主线，包含 structured/unstructured level set、remeshing、criteria、optimization problem、solver interface。
- 允许替换 physical solver、optimization algorithm、criteria、mesh processing 等组件。

这和 StructureOptimizer 当前状态差距很明显。我们现在有：

```text
benchmark config
-> structured quad mesh
-> internal dense FEM
-> SIMP
-> verification/report/demo
```

OpenPISCO 的重要启发是：

```text
optimization problem = objective criterion + constraint criteria + design state + solver data contract
```

而不是把“优化”硬编码成 `min compliance subject to volume_fraction`。

### 3.2 最值得抄的对象模型

OpenPISCO 的优化问题围绕 objective criterion 和 constraints criteria 组织。每个 criterion 都能计算 value 和 sensitivity；physical criterion 通过标准化字段向求解器要数据，例如 stress、strain、von_mises、potential_energy、mass、volume。

StructureOptimizer 应该借鉴成：

```text
Criterion
  name
  kind: physical | geometric
  role: objective | constraint | verification_only
  required_fields
  value
  limit
  status
```

这比现在 report 里散落的 `compliance`、`max_displacement`、`approx_stress` 更接近工业软件的 response/constraint 思路。

### 3.3 Design space 的关键启发

OpenPISCO 文档明确区分设计空间和隐式区域，并使用类似 OnZone / OffZone 的概念：

- 可优化区域：拓扑可以变化。
- 不可优化区域：必须保持原状，例如载荷/约束附近的保留材料。

这对 StructureOptimizer v0.3 是最直接的下一步。我们现在所有单元基本都可设计，这会造成两个问题：

- 载荷点和约束点附近可能被优化掉，导致物理解释变差。
- demo 看起来像数学图案，不像工程候选。

v0.3 应该把 design space 内生到 config：

```json
{
  "design_space": {
    "type": "element_regions",
    "design": [{"selector": "all"}],
    "frozen_solid": [{"selector": "left_support_band"}, {"selector": "load_pad"}],
    "void": [{"selector": "clearance_hole"}]
  }
}
```

最小实现不需要 CAD，只需要基于结构化网格的 element selector。

### 3.4 Criteria 的路线启发

OpenPISCO criteria 覆盖范围比我们当前 MVP 大很多：

- elastic compliance
- von Mises stress
- target displacement
- eigenfrequency
- buckling
- thermal
- worst-case compliance
- volume
- mass
- minimal / maximal thickness

StructureOptimizer 不应该一次性追全，但应该把响应体系先建对：

```text
v0.3:
  mass
  volume_fraction
  compliance
  max_displacement
  approximate_stress
  connected_material
  min_member_warning

v0.4:
  multi_load_weighted_compliance
  displacement_bound
  stress_warning / p-norm stress indicator
  candidate ranking
```

关键不是“指标数量”，而是每个指标都能说明：

```text
来源: baseline | optimization_iteration | independent_verification | manufacturability
角色: objective | constraint | verification | warning
状态: passed | warning | failed | not_applicable
```

## 4. SALOME：最接近 HyperMesh 前处理层的开源平台

### 4.1 它强在哪里

SALOME 是开源 CAD/CAE 集成平台，定位是数值仿真的前后处理和求解器集成。它提供：

- CAD/CAE 集成平台。
- 3D modeling：构造、导入、healing。
- mesh generation：几何驱动网格、导入导出、编辑、remeshing。
- group/filter：把节点、边、面、体、单元组织成工程区域。
- quality controls：面积、角度、扭曲、Jacobian、aspect ratio 等网格质量检查。
- visualization：3D/2D 结果可视化。
- study schema：保存和恢复研究过程。
- Python console/API：自动化入口。

它不是拓扑优化器，但它非常像 HyperMesh 的“模型准备层”。

### 4.2 对 StructureOptimizer 的直接启发

StructureOptimizer 现在最大的问题不是没有 GUI，而是没有工程对象：

```text
只有 benchmark name
没有 part / region / group / named selector
只有 mesh index
没有工程语义
只有 final density
没有可追踪的 field/result object
```

SALOME 给我们的启发是先建立轻量工程语义：

```text
Region
  name
  entity_type: node | edge | element | face
  selector
  role: load | constraint | design | frozen | void | measurement

MeshQualitySummary
  element_count
  node_count
  min_area
  max_aspect_ratio
  inverted_elements
  warnings
```

在 2D structured mesh 内部也可以先做这件事，不必立刻接 CAD。

### 4.3 为什么不要现在就做 SALOME adapter

SALOME 真正有价值的是 CAD、网格、分组、MED 文件、Python 自动化。但当前 StructureOptimizer 的核心仍是 2D structured quad + demo。过早接 SALOME 会引入：

- 大型安装依赖。
- MED/SMESH 数据模型。
- 几何拓扑命名问题。
- GUI/平台兼容问题。

所以正确路线不是 v0.3 就做 SALOME 集成，而是先把内部对象设计成未来能接 SALOME：

```text
v0.3: 内部 Region / DesignSpace / ResultField
v0.4: meshio/Gmsh export + basic VTK export
v0.5+: SALOME MED import/export spike
```

## 5. OpenMDAO：对标 HyperStudy 的轻量路线

### 5.1 它强在哪里

OpenMDAO 是 Python 开源多学科分析与优化框架。它的核心价值不是代替 FEA，而是把多个组件组合成可优化的系统：

- `Problem` 管理整个模型。
- `Component` 封装分析模块。
- `Driver` 执行优化或 DOE。
- design variables / objectives / constraints 一等公民化。
- 支持梯度优化、无梯度优化、DOE、并行/HPC、记录和调试。
- 强调 analytic derivatives 和 system-level gradients。

这对应 HyperStudy，而不是 HyperMesh。

### 5.2 对 StructureOptimizer 的直接启发

StructureOptimizer 的 `run` 当前只跑一个 benchmark/preset。下一步要让它能跑 study：

```text
study config
-> generate parameter matrix
-> run each candidate
-> verify each candidate
-> aggregate metrics
-> rank candidates
-> produce comparison report/demo
```

最小 v0.4 可以先不引入 OpenMDAO 依赖，而是学它的概念：

```json
{
  "study": {
    "benchmark": "simple_bracket",
    "parameters": {
      "volume_fraction": [0.3, 0.4, 0.5],
      "filter_radius": [1.5, 2.0]
    },
    "ranking": ["verification_status", "mass", "compliance", "max_displacement"]
  }
}
```

对应 CLI：

```bash
python -m structure_optimizer study --config studies/simple_bracket_tradeoff.json
```

输出：

```text
runs/studies/<study_id>/
  study_input.json
  candidates.csv
  pareto.html
  candidate_*/...
```

这会让 demo 从“一个案例好看”升级成“能解释设计权衡”。

## 6. Dakota：比 OpenMDAO 更像 HyperStudy 的 UQ/鲁棒分析层

Dakota 来自 Sandia，定位是 design exploration、model calibration、risk analysis、margins and uncertainty quantification。

它对 StructureOptimizer 的意义偏 v0.5 以后：

- 参数不确定性。
- 载荷扰动。
- 材料属性扰动。
- 鲁棒候选排序。
- 可靠性指标。

当前不要引入 Dakota。先实现 OpenMDAO 风格的本地 study runner，等我们有稳定 candidate 数据后，再考虑 UQ/鲁棒性。

## 7. Gmsh / meshio：最务实的网格入口

Gmsh 是开源 3D 有限元网格器，带 CAD engine、post-processor、GUI、CLI、`.geo` 脚本和多语言 API。它比 SALOME 更轻，更适合作为 StructureOptimizer 未来第一个外部网格入口。

建议路线：

```text
v0.3: 不接外部网格，先建立内部 Region / DesignSpace
v0.4: 导出 VTK/VTU 或 simple mesh JSON，方便 ParaView 检查
v0.5: meshio 读写 Gmsh .msh / VTK / VTU
v0.6: Gmsh adapter spike
```

不要现在就依赖 Gmsh，因为当前 MVP 的结构化网格足够支持算法验证。

## 8. ParaView / VTK：后处理方向

ParaView 是开源后处理标杆，适合大规模科学可视化、Python batch、Web/in situ/HPC。它对我们的意义不是立刻替换 demo.html，而是定义结果数据格式：

```text
ResultField
  mesh
  nodal_displacement
  element_density
  element_stress
  scalar_metrics
```

v0.4 最小实现可以增加：

```text
density.vtk 或 density.vtu
verification_fields.json
```

这样结果既能进 demo，也能进 ParaView/PyVista/VTK 生态。

## 9. 开源对标后的架构判断

### 9.1 不应该做的事

短期不要做：

- 完整 CAD kernel。
- SALOME/FreeCAD GUI 集成。
- 全 3D FEM。
- Code_Aster/CalculiX 强适配。
- 大而全 plugin framework。
- 云端队列和账户系统。

这些会把项目拖进平台工程，偏离当前最有价值的闭环。

### 9.2 应该做的事

按收益排序：

1. 把 design space / non-design space 放进配置和优化过程。
2. 建立 objective / response / constraint / criterion 的统一对象。
3. 支持多载荷工况和 weighted compliance。
4. 把最小构件尺寸、对称、保留区从后验检查前置到优化更新。
5. 建立 study runner，能批量跑体积分数/过滤半径/工况权重。
6. 输出 candidate comparison 和 Pareto 风格静态 HTML。
7. 再考虑 Gmsh/meshio/VTK adapter。

## 10. StructureOptimizer 追赶路线

### v0.3：工程约束内生化

目标：让 StructureOptimizer 从“跑一个 SIMP 图”升级为“能定义工程优化问题”。

交付：

- `DesignSpace`：design / frozen_solid / void masks。
- `RegionSelector`：基于 structured mesh 的 named selectors。
- `LoadCaseSet`：多载荷工况，支持权重。
- `Criterion` / `Response` / `Constraint`：统一指标对象。
- `ObjectiveTable`、`ResponseTable`、`ConstraintTable` 输出到 report/demo。
- 优化过程遵守 frozen/void mask。
- verification 明确区分 objective、constraint、warning。

不做：

- CAD import。
- 外部 solver。
- 全 3D。
- GUI。

### v0.4：本地 study 与候选对比

目标：让 demo 从单案例展示升级为“工程权衡展示”。

交付：

- `study` CLI。
- 参数矩阵：volume fraction、filter radius、load weights。
- 批量 run -> verify -> report。
- `candidates.csv`。
- `study.html`，包含候选排名、质量/柔度/位移/验证状态对比。
- 简单 Pareto 散点图或表格。
- VTK/JSON field export spike。

不做：

- OpenMDAO 正式依赖。
- Dakota 正式依赖。
- HPC scheduler。
- 代理模型。

### v0.5：开源 CAE 互操作 spike

目标：让结果能进入外部 CAE/后处理生态。

候选交付：

- `export --format vtk`。
- `export --format gmsh-msh` 或 meshio adapter。
- 外部网格导入 spike，仅用于验证，不进入默认优化主线。
- ParaView 打开结果的最小 runbook。

不做：

- 承诺工业 CAD 清理。
- 承诺复杂非结构网格优化稳定收敛。
- 承诺 Code_Aster/CalculiX production adapter。

## 11. 下一条重大 /goal 建议

```text
/goal
Objective:
Implement StructureOptimizer v0.3 engineering-constraint core so the local MVP can express design/non-design regions, multi-load cases, objective/response/constraint tables, and mask-aware SIMP updates without adding CAD, GUI, external solvers, or full 3D FEM.

Scope:
/Users/Zhuanz/StructureOptimizer only.
Create or update:
- structure_optimizer/core/config.py
- structure_optimizer/core/mesh.py
- structure_optimizer/core/simp.py
- structure_optimizer/core/verification.py
- structure_optimizer/core/reporting.py
- structure_optimizer/core/workflow.py
- structure_optimizer/core/design_space.py
- structure_optimizer/core/criteria.py
- structure_optimizer/benchmarks/configs/
- tests/
- docs/MVP-technical-plan.md only for command/output/limitation consistency
- README.md only if CLI examples change

Constraints:
- Keep the solver local-first and bounded to existing 2D structured quadrilateral FEM plus current 2.5D simple_bracket mass/thickness reporting.
- Do not add SALOME, Gmsh, meshio, OpenMDAO, Dakota, Code_Aster, CalculiX, CAD kernels, GUI frameworks, cloud services, or full 3D FEM in this goal.
- Preserve existing run, verify, report, and demo CLI behavior.
- Add engineering semantics conservatively: design regions, frozen solid regions, void regions, multi-load cases, criteria/responses/constraints.
- Generated reports must keep saying optimization candidate, verification check, and 2D/2.5D benchmark model.

Done when:
1. python -m pytest exits 0 from /Users/Zhuanz/StructureOptimizer.
2. Existing commands still exit 0:
   - python -m structure_optimizer run --benchmark mbb_beam --preset smoke
   - python -m structure_optimizer demo --benchmark simple_bracket --preset demo
3. At least one benchmark config uses a frozen_solid region around a load or support, and the final density keeps that region solid.
4. At least one benchmark config uses a void region or keep-out region, and the final density keeps that region void.
5. At least one benchmark config has two load cases with weights, and metrics/report/demo identify weighted compliance separately from per-load verification metrics.
6. report.md and demo.html include separate objective, response, constraint, verification, and manufacturability sections.
7. verification.json records each constraint with name, value, limit, unit when available, source, and status.
8. Tests cover region selector validation, frozen_solid mask behavior, void mask behavior, invalid overlapping masks, multi-load weighted compliance smoke, and preservation of the existing run -> verify -> report path.

Stop if:
- Implementing any acceptance item requires CAD import, external meshing, external solvers, GUI, full 3D FEM, nonlinear analysis, buckling, fatigue, or multiphysics.
- Existing tests fail in files outside structure_optimizer/, tests/, docs/, README.md, or benchmark configs.
- The mask-aware SIMP update repeatedly creates singular systems after checking that load/support frozen regions are valid.
- The configuration format change would break existing benchmark configs without a backward-compatible loader.
- A new dependency becomes necessary to complete the goal.
```

## 12. 来源

访问日期：2026-05-15

- OpenPISCO product page: https://openpisco.irt-systemx.fr/
- OpenPISCO documentation: https://openpisco.readthedocs.io/en/latest/
- OpenPISCO Introduction: https://openpisco.readthedocs.io/en/latest/Intro.html
- OpenPISCO Optimization Problem: https://openpisco.readthedocs.io/en/latest/OptimizationProblem.html
- OpenPISCO Physical Solvers: https://openpisco.readthedocs.io/en/latest/PhysicalSolvers.html
- OpenPISCO Criteria: https://openpisco.readthedocs.io/en/latest/Criteria.html
- SALOME platform: https://www.salome-platform.org/
- SALOME functionalities: https://www.salome-platform.org/?page_id=23
- SALOME GUI introduction: https://docs.salome-platform.org/latest/gui/GUI/introduction.html
- SALOME SHAPER documentation: https://docs.salome-platform.org/latest/gui/SHAPER/index.html
- SALOME SMESH documentation: https://docs.salome-platform.org/latest/gui/SMESH/index.html
- OpenMDAO: https://openmdao.org/
- OpenMDAO latest docs: https://openmdao.org/newdocs/versions/latest/main.html
- OpenMDAO DOEDriver: https://openmdao.org/newdocs/versions/latest/features/building_blocks/drivers/doe_driver.html
- Dakota: https://dakota.sandia.gov/
- ParaView: https://www.paraview.org/
- Gmsh: https://gmsh.info/
