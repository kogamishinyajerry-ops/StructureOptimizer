# StructureOptimizer Tutorial

> 一个新工程师在 15 分钟内从安装到看懂第一个候选评审结果。

## 你将完成

1. 安装并验证环境
2. 跑一个标准 benchmark（`mbb_beam`）并查看产物
3. 用 `demo` 命令生成静态评审页
4. 跑 `study` 批量参数对比，理解 Pareto 前沿
5. 知道如何加入工程约束（对称 / 挤出 / min 构件尺寸）

---

## 0. 前置条件

- Python 3.11 或更新（推荐 3.12）
- 仅 NumPy 一个运行时依赖

```bash
python --version  # 应输出 3.11+ 的版本号
```

---

## 1. 安装

```bash
git clone <repo>
cd StructureOptimizer

# 推荐：在虚拟环境里
python -m venv .venv
source .venv/bin/activate
pip install -e .

# 验证
structure-optimizer --version
# 输出: structure-optimizer 1.x.y
```

---

## 2. 跑第一个 benchmark

```bash
structure-optimizer run --benchmark mbb_beam --preset smoke
```

预期输出（最后一行）：

```
runs/mbb_beam/20260516-180000-123456
```

这条路径是本次运行的产物目录，我们用 `RUN_DIR` 代表它：

```bash
RUN_DIR=$(ls -td runs/mbb_beam/*/ | head -1)
ls "$RUN_DIR"
```

你会看到：

```
input.json            metrics.csv            density.npy       density.png
baseline.png          loadcase.png           convergence.png   optimization.gif
optimization_frames/  verification.json      manufacturability.json
summary.json          report.md
```

### 怎么读这些文件

| 文件 | 看什么 |
|---|---|
| `summary.json` | 顶层一眼：迭代次数、停止原因、baseline vs optimized 关键指标 |
| `metrics.csv` | 每一轮的柔度、体积分数、变化量；用 Excel/pandas 画曲线 |
| `convergence.png` | 柔度收敛图 |
| `density.png` | 最终密度场（深色 = 留材料） |
| `optimization.gif` | 密度演化动画（评审时最直观） |
| `verification.json` | **最重要** — 独立验证的目标 / 响应 / 约束 / 制造性 |
| `report.md` | Markdown 报告，工程评审用 |

---

## 3. 独立验证 + 报告

`run` 命令已经自动调用了 verify 和 report。**但如果你想重跑**：

```bash
structure-optimizer verify --run "$RUN_DIR"
# 输出: passed   （或某个失败状态码）

structure-optimizer report --run "$RUN_DIR"
# 输出: runs/mbb_beam/<...>/report.md
```

验证状态可能是以下之一：

- `passed` — 所有约束通过
- `volume_constraint_failed` — 候选体积超出目标 +2% 容差
- `connectivity_failed` — 从载荷区到支撑区没有材料连通路径
- `design_space_constraint_failed` — frozen/void 区域被破坏
- `solver_failed` / `singular_matrix` — FEM 求解失败
- `invalid_config` — 配置非法或文件损坏

每个失败状态都对应一个具体诊断方向。

---

## 4. 静态评审页

`demo` 命令在 `run` 基础上**额外生成** `demo.html` — 给非算法背景的评审者看的页面：

```bash
structure-optimizer demo --benchmark simple_bracket --preset demo
```

输出最后一行是 `demo.html` 路径。**用浏览器打开**（无需 web server）：

```bash
open "$(ls -td runs/simple_bracket/*/demo.html | head -1)"   # macOS
xdg-open "$(ls -td runs/simple_bracket/*/demo.html | head -1)"   # Linux
```

页面结构：

- 顶部 hero：原始结构 vs 优化候选 并排
- 4 个关键指标卡（减重 / 材料保留 / 柔度 / 最大位移）+ 点击说明
- 怎么看这页 + 2 分钟视觉走查
- 原始 vs 优化对比表 + 制造性粗检表
- 目标 / 响应 / 约束分层
- **结果适用范围声明**（evaluator 调）
- 输出文件索引

---

## 5. 批量参数 study + Pareto 前沿

单次跑只是一组参数。要找"哪组参数最好"，跑 study：

```bash
structure-optimizer study --config studies/simple_bracket_tradeoff.json
```

输出最后一行：

```
runs/studies/simple_bracket_<timestamp>/study.html
```

打开浏览器看 `study.html`：

- 顶部摘要：benchmark / preset / 候选数 / 第一名验证状态
- **Pareto 前沿**节：橙色块圈出当前参数空间内的非支配集
- Pareto 风格散点图：横向越靠左 = 越轻，纵向越靠上 = 越硬
- 排名表：每个候选一行，前沿候选用淡橙底高亮，每行都有"查看详情"链到该候选的 `demo.html`

### Pareto 前沿是什么意思

候选 A "支配" 候选 B 当且仅当：
- A 在所有目标上 ≤ B（minimize 方向）
- A 在至少一个目标上 < B

**没有任何其他候选能支配它**的候选就在 Pareto 前沿上。评审时你需要在前沿集合内做权衡，前沿外的候选可以直接淘汰。

### study 配置长这样

```json
{
  "benchmark": "simple_bracket",
  "preset": "smoke",
  "parameters": {
    "volume_fraction": [0.42, 0.5],
    "filter_radius": [1.4, 1.9]
  },
  "ranking": ["verification_status", "mass", "compliance", "max_displacement"],
  "objectives": [
    {"name": "mass", "direction": "minimize"},
    {"name": "compliance", "direction": "minimize"}
  ]
}
```

参数会做笛卡尔积（这里是 2×2=4 候选）。可以加 `"load_weights.<load_case_name>"` 来扫多工况权重。

---

## 6. 加工程约束（v0.6）

如果你要求结构必须对称、必须沿某轴均匀（挤出件）、或必须满足最小构件尺寸：

在 benchmark JSON 的根部加：

```json
"manufacturing_constraints": {
  "symmetry": {"axis": "y", "position": 0.5},
  "extrusion": {"axis": "x"},
  "min_member_size": 2.0
}
```

含义：
- `symmetry.axis="y"` → 上下对称（关于水平中线）
- `symmetry.axis="x"` → 左右对称（关于竖直中线）
- `position` ∈ [0, 1]，归一化坐标，默认 0.5
- `extrusion.axis="x"` → 每一行密度都相等（沿 x 方向"拉伸"）
- `min_member_size` → 检查 `filter_radius` 是否足够大（不强制只 warn）

SIMP 循环每轮都会把这些投影应用到密度场上。验证产物 `verification.json` 会含 `symmetry_compliance` / `extrusion_compliance` / `min_member_size_compliance` 约束记录。

---

## 7. 切换求解器后端（v0.8）

对超过 ~1000 DOF 的网格，dense 求解器内存会偏大。可以切到 Jacobi-PCG：

```json
"solver": {"backend": "cg"}
```

两个后端在小 benchmark 上数值等价（相对误差 < 1e-5）。CG 是纯 NumPy，零额外依赖。

---

## 8. v2.x 新能力（v1.5 → v2.0）

> 以下章节对应 `docs/blueprint-v2.md` 中 E → J 波交付的功能。任何 v1.x 配置都向后兼容；新功能默认关闭，按需启用。

### 8.1 多工况 robust formulation（Wave E）

把单工况配置改成 multi-case，每个 case 一组载荷 + 权重 + 一个 aggregator：

```json
"load_cases": [
  {"name": "down", "weight": 1.0, "loads": [{"selector": "right_mid", "fx": 0, "fy": -800}]},
  {"name": "up",   "weight": 1.0, "loads": [{"selector": "right_mid", "fx": 0, "fy": 800}]},
  {"name": "shear","weight": 1.0, "loads": [{"selector": "right_mid", "fx": 400, "fy": 0}]}
],
"optimization": {
  ...,
  "case_aggregator": "worst_case"
}
```

可选 aggregator：`weighted_sum`（默认，按 weight 加权）/ `average`（忽略 weight，等权）/ `worst_case`（rubust min-max）。

完整例：`structure-optimizer run --benchmark multi_load_cantilever --preset smoke`

### 8.2 应力约束（Wave F）

在 BenchmarkConfig 顶层加 `stress_constraint`：

```json
"stress_constraint": {
  "enabled": true,
  "aggregation": "p_norm",
  "p": 8.0,
  "limit": 250.0,
  "density_threshold": 0.5
}
```

verification 阶段计算 p-norm 或 KS von Mises 应力，超过 `limit` 时 `status = stress_constraint_failed`。

**重要**：v1.6 仅做 verification-time 检查（D003-stress-verification-only.md）；SIMP 主循环不感知应力。

例：`structure-optimizer run --benchmark stress_limited_bracket --preset smoke`

### 8.3 BESO 算法（Wave G）

切换到 BESO（Bidirectional Evolutionary Structural Optimization）：

```bash
structure-optimizer run --benchmark mbb_beam --preset smoke --algorithm beso

# 或在配置文件里:
"optimization": {
  ...,
  "algorithm": "beso",
  "beso_er": 0.02
}
```

BESO 是 hard-kill：每个 element 要么 solid 要么 void，没有 gray。设计上更接近 manufacturable，compliance 通常略劣于 SIMP。

### 8.4 scipy sparse 求解器（Wave H）

大网格启用 sparse 后端（**24× 加速** vs `dense` on 6262 DOF）：

```bash
pip install structure-optimizer[sparse]
```

```json
"solver": {"backend": "sparse"}
```

可选 backend：`dense`（默认）/ `cg`（NumPy CG）/ `sparse`（scipy spsolve）/ `sparse_cg`（scipy CG，最低内存）。性能见 `docs/performance.md`。

### 8.5 非结构三角网格（Wave I）

```bash
pip install structure-optimizer[mesh]
```

```python
from structure_optimizer.adapters.mesh_source import MeshioReader
from structure_optimizer.core.triangle import solve_tri_linear_elastic

mesh = MeshioReader().load("my_mesh.msh")
result = solve_tri_linear_elastic(
    mesh, young_modulus=70000, poisson_ratio=0.33,
    fixed_dofs=..., force=...,
)
```

**重要**：v1.9 仅支持 triangle linear elastic **solve**，不支持 SIMP-on-triangle。详情见 D005-triangle-mesh-no-simp.md。

### 8.6 几何导出（Wave J）

从 run 目录输出 SVG / DXF / STL：

```bash
structure-optimizer export --run runs/mbb_beam/<run_id> --format svg
structure-optimizer export --run runs/mbb_beam/<run_id> --format dxf
structure-optimizer export --run runs/mbb_beam/<run_id> --format stl --extrusion-depth 5
```

- **SVG**: 2D 矢量边界，浏览器/CAD/SVG editor 直接打开
- **DXF**: R12 ASCII，AutoCAD / FreeCAD / LibreCAD 直接 import
- **STL**: ASCII，2.5D 棱柱挤出，3D 打印或 CAE 输入

阈值用 `--threshold`（默认 0.5）。SIMP gray 元素按阈值二值化。

---

## 9. v3.x 新能力（v2.1 → v3.0）

### 9.1 应力约束 SIMP 集成到梯度 — adjoint method（Wave L）

v1.6 加了应力 verification，v2.1 把它真正接进 SIMP 的梯度：

```bash
structure-optimizer run --benchmark stress_limited_bracket --preset smoke
```

打开 `stress_limited_bracket.json` 把 `optimization.stress_penalty` 调到 `1.0` 即可启用 adjoint。`docs/decisions/D007-adjoint-stress-constrained-simp.md` 写明了数学推导、Le et al. 2010 normalization、以及"经典 penalty method 不保证严格约束满足"的诚实 caveat。

### 9.2 SIMP-on-triangle（Wave M）

```python
from structure_optimizer.core.triangle_simp import run_simp_triangle, split_quad_to_triangles
import numpy as np

mesh = split_quad_to_triangles(20, 10, width=20.0, height=10.0)
# ... 设置 fixed_dofs / force（见 tests/test_triangle_simp.py 的 _cantilever_setup）
result = run_simp_triangle(mesh, young_modulus=210000, poisson_ratio=0.3,
                           fixed_dofs=fixed_dofs, force=force,
                           volume_fraction=0.45, max_iterations=30)
result._repr_html_()  # Jupyter 会显示一个 HTML 表
```

填补 v1.9 的 D005 留白；centroid-distance 过滤器代替 grid-distance，面积加权体积约束。

### 9.3 大网格 + 增量 sparse 装配 + 并行 study（Wave N）

500×500 mesh（~50 万 DOF）通过 sparse direct 在 ~100 秒内跑完：

```bash
structure-optimizer run --benchmark large_cantilever
# 启用 --run-slow 才会跑 500×500 capability test
pytest tests/test_performance.py --run-slow
```

```python
from structure_optimizer.core.study import run_study
run_study("studies/my_study.json", workers=4)  # 4 进程并行，实测 3.0× 加速
```

### 9.4 DOE 采样（LHS + Sobol）+ 设计 lineage（Wave O）

study JSON 加 `"sampling": "lhs", "n_samples": 16, "seed": 42` 即可改用拉丁超立方而非 Cartesian grid：

```json
{
  "benchmark": "cantilever",
  "preset": "smoke",
  "parameters": {"volume_fraction": [0.3, 0.4, 0.5, 0.6, 0.7]},
  "sampling": "lhs",
  "n_samples": 16,
  "seed": 42
}
```

每个 run 自动写 `lineage.json`，study 末尾汇总成 `lineage_tree.json`。

### 9.5 跨平台可复现 + fingerprint 数据库（Wave P）

`tests/fingerprints/<benchmark>__smoke.json` 是金标准 SHA-256，CI 在 Linux+Python3.12 canonical cell 走严比对，其他 11 cell 走 ≤1e-9 容忍。

```bash
# 重新生成 fingerprints（仅在故意改变 benchmark 行为时）
python scripts/generate_fingerprints.py
```

### 9.6 Jupyter rich display + 交互式 demo HTML（Wave Q）

在 JupyterLab / VS Code Notebook 直接 `result` 就会显示 HTML 表 + 密度 PNG 预览；`demo.html` 加了 toggle / pan / zoom 交互（vanilla JS，无依赖）。

---

## 10. v4.x 新能力（v3.1 → v4.0）

> v4 阶段完整蓝图见 `docs/blueprint-v4.md` 与 `docs/quality-rubric-v4.md`（100 分制，目标 ≥ 99）。
> 实施记录见 ADR `D017-D024`。

### 10.1 MMA 优化器 + Augmented Lagrangian（Wave S，D017）

OC update（之前 v0.x..v3.x 默认）在多约束、应力约束、非凸问题上收敛差。
**Method of Moving Asymptotes (Svanberg 1987)** 用渐进可移动的凸近似在每个迭代构造子问题，
通过对偶分解高效解 m 个对偶变量；**Augmented Lagrangian (Powell-Hestenes)** 把应力约束作为乘子项
加入目标函数，避免内罚法的病态条件数。

最小用法（API）：

```python
from structure_optimizer.core.simp_mma import run_simp_with_mma
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh

config = load_benchmark("stress_multi_load_bracket", preset="smoke")
mesh = create_structured_mesh(config)
result = run_simp_with_mma(config, mesh)  # MMA + AL stress
print(result.metrics[-1].compliance, result.metrics[-1].stress_max)
```

对照：`run_simp(...)` 是 OC + KS/p-norm。MMA 路径在 5-50 倍约束规模下更稳。

### 10.2 三角网格 BESO + 制造投影（Wave T，D018）

BESO（Bidirectional Evolutionary Structural Optimization）原本只支持结构 quad；
Wave T 把 element-removal 改成基于三角形面积加权的排序，并在三角网格上
落地 symmetry / extrusion 投影（centroid-based 比较，nearest-neighbour 配对）。

```python
from structure_optimizer.core.triangle_beso import run_beso_on_triangle_mesh
from structure_optimizer.adapters.mesh_source import MeshioReader

mesh = MeshioReader().load("my_part.msh")  # 需 pip install structure-optimizer[mesh]
result = run_beso_on_triangle_mesh(config, mesh)
```

3 个 triangle benchmark 已 fingerprint 化（`tests/fingerprints/triangle_*.json`）。

### 10.3 屈曲特征值 + Heaviside 三场鲁棒（Wave U，D019）

**屈曲（linear buckling）**: 解 KKₓ φ = λ KG φ 的最小 λ；λ < 1 表示在
当前载荷下结构会失稳。集成到 SIMP 后可做"屈曲约束 SIMP"。

**Heaviside 三场公式 (Wang/Lazarov/Sigmund 2011)**: ρ → ρ̃ (filter) → η-eroded /
nominal / dilated 三个投影场；优化目标是 max(C_e, C_n, C_d)，得到的
拓扑对几何摄动、3D 打印线宽误差鲁棒。

```python
from structure_optimizer.core.robust import project_robust_fields, HeavisideParams
from structure_optimizer.core.buckling import linearized_buckling

fields = project_robust_fields(rho, eta_eroded=0.75, eta_dilated=0.25, beta=10.0)
lam_min = linearized_buckling(config, mesh, rho).min_eigenvalue
```

### 10.4 Bayesian 优化 + 自动加密 + 对比报告 + CLI 增强（Wave V，D020）

- `core.bayesian_opt.bayes_optimize`: EI 采集函数 + GP（NumPy 实现，零依赖）
  用于搜索 `volume_fraction` / `filter_radius` 等超参数
- `core.refinement.refine_loop`: 在感兴趣区域自动局部加密网格，闭合 D010
- `core.compare.render_side_by_side`: 两个 OptimizationResult 并排 HTML 对比
- `cli.cli_red/green/yellow` + `diagnose_error`: ANSI 彩色错误诊断（仍保
  单行 stderr，符合永久红线；`NO_COLOR=1` 关闭）

### 10.5 AMG 预条件 + 矩阵自由 CG + 1000×1000 网格（Wave W，D021）

**AMG（Algebraic MultiGrid）**: `pip install structure-optimizer[amg]` 启用
pyamg-preconditioned CG，对刚度矩阵的迭代次数从 1000+ 降到 ~50。

**矩阵自由 CG**: `core.matrix_free_cg.matrix_free_cg(...)` 不组装 K，
按 element-by-element 计算 K·v；内存 O(n_elem) 而非 O(n_elem²)。
配合 `xlarge_cantilever` benchmark 可在本地跑 1000×1000 ≈ 2M DOFs 网格。

```python
from structure_optimizer.core.matrix_free_cg import matrix_free_cg
u_free = matrix_free_cg(config, mesh, densities, rhs_free, tolerance=1e-8)
```

### 10.6 突变测试 + 漂移检测 + 指纹库扩充（Wave W 续，D021）

- `scripts/run_mutation_test.py`: 4 个标准变异算子 × 3 个核心模块；
  当前杀伤率 ≥ 70%（rubric §3.3）
- `scripts/drift_check.py`: 把当前代码的 benchmark 输出哈希 vs `tests/fingerprints/`
  里的历史指纹比对；CI 早期预警意外的算法漂移
- `tests/fingerprints/` 已扩充到 ≥ 20 quad + ≥ 3 triangle 指纹

### 10.7 测试 agent + v4 评分体系（D022-D024）

`scripts/test_agent.py` 是 v4 阶段引入的**独立机械验证器**：扫 100 分制
rubric 的 23 个条目（算法 30 + 性能 15 + 复现 15 + 工程质量 20 + 用户面 10 + 文档 10），
逐项输出 PASS/PARTIAL/FAIL + 证据，并把分数写入 `tests/v4_scorecard.json`。
评分故意"客观高于乐观"：若 `core` 覆盖率 < 95% 就 fail，不放水。

```bash
python scripts/test_agent.py        # 跑完整 rubric
cat tests/v4_scorecard.json | jq .   # 机器可读评分
```

测试 agent 同时检查 v1/v2/v3 旧 rubric **不能回归**，保证向前没有
性能/算法/复现退化。

---

## 11. 下一步

- `docs/architecture.md` — 模块边界、永久红线、扩展点（含 v3.x/v4.x 抽象）
- `docs/quality-rubric.md` / `quality-rubric-v2.md` / `quality-rubric-v3.md` / `quality-rubric-v4.md` — 质量评分体系四代
- `CHANGELOG.md` — v0.1 → v4.0 完整版本历史
- `README.md` — CLI 完整表 + 已知限制
- `scripts/test_agent.py` — 自动跑 100 分制 rubric

### 11.1 v4 阶段的永久红线（不变）

v4 没有放松任何 v1-v3 已建立的红线：
- 无 CAD / GUI / cloud / full-3D / commercial 求解器
- 运行时 mandatory deps 仍仅 `numpy`（scipy / pyamg / meshio / matplotlib 全部 optional）
- 本地可跑 — `pytest -q` 不依赖网络
- 失败仍单行 stderr + 状态码字符串（不抛 traceback）
- 自我贬低优先于自我吹嘘（rubric 评分诚实优先）

---

## 12. v5.x 多物理场扩展（v4.0 → v5.0）

> v5 阶段完整蓝图见 `docs/blueprint-v5.md` 与 `docs/quality-rubric-v5.md`（100 分制，目标 ≥ 99）。
> 实施记录见 ADR `D025-D032`。
> **主题**：把 v1-v4 的工程纪律（红线 + 测试 agent + 诚实评分）推广到 multi-physics 2D：
> 热传导、模态、几何非线性、多材料、随机/可靠性、Pareto。

### 12.1 热传导 SIMP + 散热器拓扑（Wave Y，D025）

2D Poisson 热传导 + min-thermal-compliance SIMP。Element matrix 是
经典 4-node bilinear quad conductivity matrix（Cook 1989 §10.2）：

```python
from structure_optimizer.core.thermal_simp import (
    load_thermal_benchmark, run_thermal_simp,
)
from structure_optimizer.core.mesh import create_structured_mesh

cfg, k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
mesh = create_structured_mesh(cfg)
result = run_thermal_simp(cfg, mesh, k, sources, bcs)
print(result.final_result.max_temperature, result.metrics[-1].volume_fraction)
```

`heat_sink` benchmark：中心点热源 + top/bottom Dirichlet=0 + SIMP min-thermal-compliance。
1D-rod analytical 校验（`test_thermal.py`）确保 FEM 与解析解一致。

### 12.2 模态 + 频响 TO（Wave Z，D026）

广义本征值问题 `K φ = ω² M φ` + 谐波激励响应 `(K - ω²M) u = f`。
纯 numpy Cholesky 变换 + `np.linalg.eigh`（无 scipy 依赖）。
Consistent 和 lumped mass 两种选择，Euler-Bernoulli 一阶频率校验。

```python
from structure_optimizer.core.modal import solve_modal
from structure_optimizer.core.freq_response import solve_frequency_response

result = solve_modal(cfg, mesh, densities, n_modes=3, mass_type="consistent")
print(result.frequencies_hz)  # smallest 3 natural frequencies in Hz

# Frequency-response at a single excitation freq:
fr = solve_frequency_response(cfg, mesh, densities, omega=10.0)
print(fr.max_displacement)
```

### 12.3 几何非线性 + 大变形 TO（Wave AA，D027）

简化的 Total-Lagrangian Newton-Raphson + 增量加载。复用 v4 的 `K_g` 几何刚度矩阵
（来自 buckling 模块）。Gere elastica 趋势校验：在大载荷下 `|u_nl| < |u_linear|`。

```python
from structure_optimizer.core.nonlinear_fem import solve_geometric_nonlinear
from structure_optimizer.core.nonlinear_simp import run_nonlinear_simp

# Direct FEM solve at fixed densities:
fem = solve_geometric_nonlinear(cfg, mesh, densities, n_load_steps=5)
print(fem.max_displacements)  # per-step max displacement trace

# Full SIMP driver:
opt = run_nonlinear_simp(cfg, mesh, n_load_steps=3)
print(opt.final_result.max_displacements)
```

### 12.4 多材料 SIMP（Sigmund-Tortorelli, Wave BB, D028）

M 种材料各自一个独立 density field；effective E = E_min + Σᵢ ρ_{i,e}^p · (E_i - E_min)。
Per-material 体积约束，per-material OC update。

```python
from structure_optimizer.core.multi_material import (
    MaterialProperty, run_multi_material_simp,
)

materials = [
    MaterialProperty(name="aluminium", young_modulus=70_000, poisson_ratio=0.3, density=2.7),
    MaterialProperty(name="steel",     young_modulus=210_000, poisson_ratio=0.3, density=7.85),
]
result = run_multi_material_simp(cfg, mesh, materials, volume_fractions=[0.2, 0.2])
print(result.material_names, result.final_result.compliance)
```

### 12.5 随机 / 可靠性 TO（Wave CC，D029）

Monte Carlo UQ + worst-case (minimax) SIMP。RNG-seed 化保证可复现。
2 个 stochastic fingerprint 锁定 seed=20251201 输出。

```python
from structure_optimizer.core.stochastic import monte_carlo_uq, UncertaintySpec
from structure_optimizer.core.reliability import worst_case_simp

# UQ over uncertain loads on a fixed topology:
spec = UncertaintySpec(load_magnitude_std=0.1, load_angle_std=0.05)
uq = monte_carlo_uq(cfg, mesh, densities, rng_seed=42, n_samples=50, uncertainty=spec)
print(uq.mean, uq.std, uq.p95, uq.max)

# Robust SIMP (worst-case over K pre-sampled scenarios):
robust = worst_case_simp(cfg, mesh, rng_seed=42, n_scenarios=5)
print(robust.final_worst_compliance, robust.final_mean_compliance)
```

### 12.6 NSGA-II Pareto + 2D→STL + Autodiff（Wave DD，D030-D032）

最小化 NSGA-II 实现（bi-objective Pareto），2D→STL boundary 导出（3D 打印），
pure-NumPy 反向 AD（用于敏感度验证）。

```python
from structure_optimizer.core.pareto_nsga import nsga_ii, render_pareto
from structure_optimizer.core.stl_export import write_stl
from structure_optimizer.core.autodiff import gradient_check, Var

# Pareto front for any bi-objective function:
def my_objective(x):
    return (float(x[0]), float(np.sum(x[1:])))
front = nsga_ii(my_objective, n_vars=5, bounds_lower=np.zeros(5),
                bounds_upper=np.ones(5), population_size=30, n_generations=20)
render_pareto(front, "pareto.html")

# Voxelized STL of a topology:
info = write_stl(mesh, densities, "topology.stl", rho_threshold=0.5, z_thickness=2.0)
print(info["n_triangles"], info["n_solid_cells"])

# Sensitivity verification via central finite differences:
def f(x):
    return float(x @ x)
g = gradient_check(f, np.array([1.0, 2.0]), h=1e-7)  # ≈ [2, 4]
```

### 12.7 v5 阶段的永久红线（不变）

- v5 仍**在** v1-v4 红线**内**扩展，没有放宽任何
- 所有 multi-physics 模块仍纯 numpy；optional deps 不增加
- Stochastic 模块的 RNG 决定性给定 seed + 平台，跨平台 bit-exact 不强求
- 测试 agent 的 v5 rubric 同样 mechanical 评分，不放水

如果 `verification.json` 出现 `volume_constraint_failed` / `connectivity_failed` 之类的失败状态，先看 `report.md` 的诊断段落。

---

## 16. v6.x 生产级公式升级（v5.0 → v6.0）

v6 把 v5 的有意简化升级为严格、可解析校验的生产级实现（见 `docs/blueprint-v6.md`）。
每个升级都配定量解析校验，不再是 v5 的 qualitative trend。

### 16.1 完整 Total-Lagrangian Green-strain Newton（Wave EE，D034）

v5 的 `core/nonlinear_fem.py` 用矩阵级 `K + ½K_g` 近似 SVK 响应；v6 的
`core/total_lagrangian.py` 实现真正的 Total-Lagrangian Q4 单元（Bonet & Wood Ch.9）：
等参 Q4 + 2×2 Gauss，由参考节点坐标算变形梯度 `F = I + ∂u/∂X`，Green-Lagrange 应变
`E = ½(FᵀF − I)`，2nd PK 应力 `S = D:E`（SVK，SIMP 密度缩放 `D_e = ρ缩放·D₀`），
内力 `∫B_LᵀS dV` + 一致切线 `∫(B_LᵀD B_L + GᵀΣG)dV`，Newton + 增量加载。

```python
from structure_optimizer.core.total_lagrangian import solve_total_lagrangian, green_strain_field
r = solve_total_lagrangian(config, mesh, densities, n_load_steps=5)
# r.displacements / r.max_displacements / r.converged / r.strain_energy
```

**关键升级**：完整 TL 满足 frame indifference——有限刚体旋转产生**零** Green 应变
（`E = ½(RᵀR−I) = 0`，机器精度），这是 v5 `K+½K_g` 近似**不满足**的性质，也是
Wave EE 的旗舰回归测试。小载荷下退化为线性 FEM；工作载荷下 tip 挠度不超过线性估计
（elastica 次线性趋势）。

### 16.2 Rayleigh 阻尼复频响（Wave FF，D035）

v5 的 `solve_frequency_response` 解无阻尼实系统 `(K−ω²M)û=f̂`，在每个固有频率处奇异。
v6 加 `solve_damped_frequency_response`，解复系统 `(K−ω²M+iωC)û=f̂`，C = αM+βK（Rayleigh）：

```python
from structure_optimizer.core.freq_response import (
    solve_damped_frequency_response, half_power_bandwidth, rayleigh_modal_damping_ratio,
)
r = solve_damped_frequency_response(config, mesh, densities, omega, alpha=0.1*w1, beta=0.0)
# r.magnitude / r.phase / r.max_magnitude（复数 û）
```

**关键升级**：阻尼系统在共振处**有限**（无阻尼是奇异的）。模态阻尼比
`ζ = ½(α/ω + βω)`，通过半功率（−3 dB）带宽 `Δω ≈ 2ζω_n` 解析校验
（`half_power_bandwidth` 从幅值扫频提取带宽 → 反推 ζ，与设定值吻合）。

### 16.3 各向异性张量热传导（Wave GG，D036）

v5 的 `solve_thermal` 只支持标量 conductivity；v6 加张量 k = [[kxx,kxy],[kxy,kyy]]
（纤维复合、增材分层、轧制金属），通过 2×2 Gauss 积分 `∫BᵀkB`：

```python
from structure_optimizer.core.thermal import conductivity_tensor, solve_thermal
k = conductivity_tensor(kxx=5.0, kyy=1.0, kxy=0.3)  # 正交各向异性 + 耦合
r = solve_thermal(config, mesh, densities, k_scalar, sources, bcs, conductivity_tensor=k)
```

**关键升级**：各向同性 k·I 退化为 v5 解析标量矩阵（机器精度）；通过 **FEM patch test**
定量验证——线性温度场 `T = a·x+b·y` 对任意常张量产生零内部残差（机器精度）。向后兼容：
不传 `conductivity_tensor` 时走原标量路径。

### 16.4 NSGA-III ≥3 目标多目标优化（Wave HH，D037）

v5 的 `nsga_ii` 是双目标 NSGA-II（拥挤距离选择）；目标数 ≥3 时拥挤距离会丢失多样性。
v6 加 `nsga3`：用 **Das-Dennis 结构化参考方向** + **niching** 维持高维目标空间的均匀覆盖：

```python
import numpy as np
from structure_optimizer.core.pareto_nsga import nsga3, das_dennis_reference_points

ref = das_dennis_reference_points(n_obj=3, n_divisions=12)  # C(14,2)=91 个参考点
front = nsga3(eval_fn, n_vars=6, bounds_lower=np.zeros(6), bounds_upper=np.ones(6),
              n_obj=3, n_divisions=12, n_generations=80)
# front.objectives: (n_front, 3) 非支配点；front.decisions: 对应决策向量
```

**关键升级**：参考点数严格等于组合数 `C(n_divisions+n_obj−1, n_obj−1)`（解析校验）；
分裂前沿用参考线垂距关联 + 最小 niche 计数选择（空 niche 取最近点，否则随机）。
**定量校验**：在 DTLZ2 基准上（真前沿 = 单位球卦限 Σf²=1）演化前沿收敛到该球面，
且按目标维均匀展开（非塌缩）。SBX 交叉 / 多项式变异 / 非支配排序与 NSGA-II 共享。

### 16.5 FORM/SORM + 重要性采样可靠度（Wave II，D038）

v5 的 `monte_carlo_uq` 是粗 Monte Carlo：估计失效概率 P_f 需要 O(1/P_f) 样本才能
看到一个尾部事件——P_f≈1e-4 时几乎不可行。v6 加结构可靠度方法（标准正态 U 空间，
失效 = `{g(u) ≤ 0}`，原点假定安全）：

```python
import numpy as np
from structure_optimizer.core.reliability import (
    form_hlrf, sorm_breitung, importance_sampling, standardize_gaussian)

# 物理高斯变量 → 标准正态：u = (x − μ)/σ
a = np.array([3.0, 4.0])                       # 线性极限态 g(u) = 10 − aᵀu
g = lambda u: float(10.0 - a @ u)
form = form_hlrf(g, n_vars=2)                  # β = 10/‖a‖ = 2.0，P_f = Φ(−2)
sorm = sorm_breitung(g, form)                  # 线性 → 退化为 FORM
imp  = importance_sampling(g, 2, form.mpp, n_samples=4000)  # 低方差 P_f + cov
```

**关键升级**：FORM 对线性极限态**解析精确**（β=β₀/‖a‖，一步收敛，机器精度）；
SORM 用 Breitung 曲率修正 `P_f ≈ Φ(−β)∏(1+βκᵢ)^(−1/2)`，零曲率时退化为 FORM；
重要性采样把采样密度移到设计点（MPP），尾事件（β=3，P_f≈1.35e-3）下变异系数
比同样本量的粗 MC 小一个量级以上。Φ 用 `math.erf`，不引入 scipy。

### 16.6 Marching-squares 平滑边界 STL（Wave JJ，D039）

v5 的 `write_stl` 把每个实体格变成轴对齐方盒——边界是阶梯状，面积误差 O(h)。
v6 加 `write_stl_marching_squares`：用 marching squares 提取密度场的等值线（边上线性
插值），把拐角削平，光滑场下面积误差降到 O(h²)；闭合轮廓再挤出成棱柱：

```python
import numpy as np
from structure_optimizer.core.stl_export import (
    marching_squares_contours, polygon_area, write_stl_marching_squares)

# 直接对标量场提取等值线（inside = field > level）
loops = marching_squares_contours(field, x_coords, y_coords, level=0.0)
area = sum(polygon_area(lp) for lp in loops)          # 各闭合环面积之和
# 或对优化后的密度场直接写平滑 STL
info = write_stl_marching_squares(mesh, densities, "out.stl", rho_threshold=0.5)
```

**关键升级**：对光滑圆盘场，面积误差随 h 减半而**四分之一化**（实测 n=33→257
误差 1.08e-3→1.6e-5，比率≈0.25 = O(h²)），且各分辨率下都比 voxel 阶梯面积误差小
约 5 倍；轮廓保证闭合（首点≈末点）。鞍点（case 5/10）用格心值消歧。仍是 2.5D 挤出，
不引入 3D 求解。

### 16.7 Reverse-mode（tape）自动微分（Wave KK，D040）

v5 的 `Var` 名为 reverse 实为 **forward-mode**（每次只带一个种子的导数，n 个输入要
跑 n 遍）。v6 加真正的 reverse-mode（tape）`RVar`：记录计算图，一次反向传播就拿到
对**所有**输入的梯度——这正是标量目标对大量设计变量求灵敏度时该用的模式：

```python
import numpy as np
from structure_optimizer.core.autodiff import RVar, reverse_grad

# 方式一：直接用 RVar 建表达式
a, b = RVar(2.0), RVar(3.0)
y = a * b + a            # y = a·b + a
y.backward()             # 一次反向传播
print(a.grad, b.grad)    # ∂y/∂a = b+1 = 4.0，∂y/∂b = a = 2.0

# 方式二：对向量函数求全梯度（f 接收 list[RVar]，返回 RVar）
g = reverse_grad(lambda v: 100*(v[1]-v[0]**2)**2 + (1-v[0])**2, np.array([0.7, -0.3]))
```

**关键升级**：reverse 梯度与 forward `Var`、解析解、中心差分**四者一致**（机器精度 /
1e-6）；共享子表达式的伴随**正确累加**（per-seed 方法会漏）；反向传播用**迭代**后序
遍历，2 万深的链也不会撞 Python 递归上限。仅支持 + - * / ** neg（灵敏度验证工具，
非 JAX/PyTorch 替代）。

## 17. v7 — production drivers & field-level fidelity

v7 把 v6 的严格**正向求解器**接入**优化驱动器**，并把残留的全局/均匀简化提升到
**逐单元场级保真**。每个升级源自一条 v5/v6 ADR 的 reopening criterion。

### 17.1 Reliability-based TO（Wave MM，D042）

v6 的 FORM（D038）只能**评估**给定结构的失效概率；v7 把它接进 SIMP **驱动器**：在
载荷幅值不确定（乘性因子 `s ~ N(1, cov)`）下，对**可靠度约束** β ≥ β_target 求最轻设计。
线性弹性位移随载荷线性变化，故位移极限态 `g(s)=d_allow − s·d_nom` 在标准正态空间线性，
FORM 精确：`β = (d_allow − d_nom)/(cov·d_nom)`。

```python
import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.rbto import displacement_reliability, rbto_simp

config = load_benchmark("cantilever", preset="smoke")
mesh = create_structured_mesh(config)
# 评估某设计在 cov=0.15 下的可靠度指标 β（FORM，对线性极限态精确）
res = displacement_reliability(d_nominal=0.8, d_allow=1.0, load_cov=0.15)
print(res.beta, res.p_failure)          # β = (1−0.8)/(0.15·0.8) = 1.667
# 求满足 β ≥ 2.0 的最轻 min-compliance 设计（对体积分数二分）
out = rbto_simp(config, mesh, d_allow=1.2, beta_target=2.0, load_cov=0.15)
print(out.feasible, out.volume_fraction, out.beta)
```

**关键升级**：FORM β 与解析闭式**机器精度一致**（1e-7）；因 min-compliance 拓扑对载荷
均匀缩放不变，可靠度旋钮是**体积分数**——更多材料 → d_nom 下降 → β 上升。更苛刻的
β_target 需要 ≥ 同等的材料量（RBTO vs 确定性设计的差异，可量化）。仍 numpy-only / 2D。

### 17.2 逐单元各向异性热场 + 各向异性热 TO（Wave NN，D043）

v6（D036）的张量热传导是**全局**一个 k；v7 升级到**逐单元**各向异性场（每个单元一个
方向/张量，如纤维复合的局部纤维角），并给出**各向异性热 TO 灵敏度**：

```python
import numpy as np
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.thermal import orientation_field_to_tensors, solve_thermal
from structure_optimizer.core.thermal_simp import (
    anisotropic_thermal_sensitivity, load_thermal_benchmark)

config, k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
mesh = create_structured_mesh(config); rho = np.full(mesh.elements.shape[0], 1.0)
# 逐单元方向场（基张量 kxx=5,kyy=1 旋转 per-element 角度）
field = orientation_field_to_tensors(5.0, 1.0, np.linspace(0, np.pi/2, mesh.elements.shape[0]))
r = solve_thermal(config, mesh, rho, 1.0, sources, bcs, conductivity_tensor_field=field)
# 各向异性热 TO 灵敏度 dC/dρ（自伴随，与标量同式，但能量带张量）
sens = anisotropic_thermal_sensitivity(config, mesh, rho, conductivity_tensor=field[0],
                                       heat_sources=sources, thermal_bcs=bcs)
```

**关键升级**：均匀方向场**精确退化**到 v6 全局张量解（1e-12，故继承 D036 patch test）；
变化的方向场产生不同的温度场（物理有效）；各向异性 SIMP 灵敏度与中心差分**一致**
（rel 1e-4）。注：变化 k 下线性场不再是无源精确解，故不重复声称 patch test——退化锚点
经均匀情形传递该保证。

### 17.3 几何非线性 TO 的 TL 伴随灵敏度（Wave OO，D044）

v6（D034）的完整 Total-Lagrangian 求解器是**正向**的；v7 把它接成**优化驱动器**所需的
伴随灵敏度。对端柔度 `C = fᵀu`，收敛态下内力等于外载 `f_int = f_total`，故伴随 `λ` 解
`K_T λ = f_total`（K_T 为一致切线刚度），灵敏度为

```text
dC/dρ_e = -(dk_scale_e/dρ_e / k_scale_e) · (λ_eᵀ f_int,e)
```

因为每个单元的 TL 内力对其 SIMP 模量因子**线性**（f_int,e = k_scale_e · g_e(u)）。线性极限
下 K_T→K、f_int=Ku、λ→u，退化为经典自伴随 `−u_eᵀ(dK_e/dρ)u_e`。

```python
import numpy as np
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.nonlinear_simp import tl_adjoint_compliance_sensitivity

config = load_benchmark("cantilever", preset="smoke")
mesh = create_structured_mesh(config); rho = np.full(mesh.elements.shape[0], 0.6)
out = tl_adjoint_compliance_sensitivity(config, mesh, rho, n_load_steps=4)
# out.compliance = 完整 TL 端柔度；out.sensitivity[e] = dC/dρ_e（伴随，已验对中心差分）
```

**关键升级 / 诚实边界**：伴随灵敏度对**中心差分**一致（rel 2e-4，受两次独立 Newton 收敛
容差 + float64 抵消限制，非 1e-5）；TL 端柔度可测地**异于**同设计的线性柔度（非线性真实）；
本 wave 交付的是**灵敏度**（可验证的难点），把它喂进 `_optimality_criteria_update` 即得
完整 TL-in-the-loop 优化器——后者更慢且不增新解析锚点，故推迟（见 D044 reopening）。

### 17.4 相关 / 非高斯不确定性的 Nataf 变换（Wave PP，D045）

v6（D038）的 FORM/SORM 假设物理变量是**独立高斯**。v7 用 **Nataf 变换**把"相关 +
非高斯"映射到独立标准正态 U，从而沿用同一套 HL-RF。对线性极限态 g(x)=a₀−aᵀx、
X~N(μ,Σ)，精确闭式 β=(a₀−aᵀμ)/√(aᵀΣa)：

```python
import numpy as np
from structure_optimizer.core.reliability import correlated_gaussian_reliability

mean = np.array([10.0, 8.0, 5.0]); std = np.array([2.0, 1.5, 1.0])
corr = np.array([[1, 0.5, -0.3], [0.5, 1, 0.2], [-0.3, 0.2, 1]], float)
a0, a = 40.0, np.array([1.0, 1.0, 1.0])
res = correlated_gaussian_reliability(mean, std, corr, lambda x: a0 - a @ x)
# res.beta == (a0 - a@mean)/sqrt(a @ (diag(std)@corr@diag(std)) @ a)
```

非高斯走 `Marginal` + `build_nataf`：支持 **normal / lognormal**（两者等效正态相关有
**闭式**修正 ρ_z = ln(1+ρ_x·c)/(ζ_iζ_j)，故每个相关情形都有解析锚点）。

```python
from structure_optimizer.core.reliability import Marginal, build_nataf
m = [Marginal("lognormal", 1.0, 0.3), Marginal("lognormal", 0.5, 0.4)]
nataf = build_nataf(m, np.array([[1.0, 0.6], [0.6, 1.0]]))
g_u = nataf.wrap_limit_state(lambda x: 5.0 - x.sum())   # 喂给 form_hlrf
```

**诚实边界**：仅 normal/lognormal（有闭式等效相关，可解析验证）；**混合** normal/lognormal
且相关≠0 直接**拒绝**（无闭式，不静默近似）；其余 marginal（Weibull/Gumbel）需 Nataf
积分，推迟（见 D045 reopening）。独立情形精确退化为 `standardize_gaussian`。

### 17.5 NSGA-III 直接优化密度场（Wave QQ，D046）

v5（Wave DD）的 NSGA 只跑 **proxy**（材料分配 / 截面）或对预算解后处理，因为"每个基因
= 整个密度场"太贵。v7 兑现 D037/D023 reopening：基因**就是**密度场，目标 =（柔度, 体积）：

```python
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.multi_objective_to import multi_objective_to

config = load_benchmark("cantilever", preset="smoke")
mesh = create_structured_mesh(config)
res = multi_objective_to(config, mesh, n_generations=10, population_size=12)
# res.front_objectives (n,2) 已按柔度升序；res.hv_history 累积存档超体积（单调）
```

**关键 / 诚实边界**：2D 超体积有**精确解析**校验；累积非支配存档 + 固定参考点保证超体积
**单调不减**（算法不变量，与优化质量无关）；前沿是真柔度/体积权衡（体积随柔度升而降）。
**这是梯度自由搜索，打不过梯度 SIMP**——测试显式断言"前沿不支配梯度 SIMP 点"而非吹嘘
超越。价值在于"真密度场的可验证 Pareto 前沿 + 收敛信号"，单目标 SIMP 给不了。

### 17.6 阻尼频响 TO：动柔度（Wave RR，D047）

v6（D035）的 Rayleigh 阻尼复频响是**正向**的；v7 把它接成驱动器。目标 = 平方动柔度
J=|fᵀû|²（D=K−ω²M+iωC，C=αM+βK）。因 K/M/C 对称且输出载荷=输入载荷，伴随**自伴随**：
dc/dρ_e=−û_eᵀ(dD_e/dρ_e)û_e，dJ/dρ_e=2·Re(c̄·dc/dρ_e)。

```python
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.freq_response import (
    dynamic_compliance_sensitivity, minimize_dynamic_compliance)

config = load_benchmark("cantilever", preset="smoke")
mesh = create_structured_mesh(config)
out = dynamic_compliance_sensitivity(config, mesh, rho, omega=50.0, alpha=0.5, beta=1e-4)
# out.objective = |fᵀû|²；out.sensitivity = dJ/dρ（自伴随，已验对中心差分 rel 1e-5）
res = minimize_dynamic_compliance(config, mesh, omega=50.0, alpha=0.5, beta=1e-4, n_steps=20)
# res.objective_history 单调下降；扫频显示共振峰 2.60→0.97（避共振）
```

**关键 / 诚实边界**：灵敏度对中心差分 rel 1e-5（实测 ~1e-7）；无阻尼退化为实数、J=(fᵀu)²
与 v5 实数解一致；体积守恒投影梯度下降使 J 单调降 ~86% 且扫频峰值显著下降。但这是**单频**
目标 + **紧凑投影梯度**（无滤波，非 MMA/OC 生产优化器）——验证的是"解析灵敏度能把 J 推下去
并削峰"，不是生产级动态 TO（见 D047 reopening）。

### 17.7 Ear-clipping 通用多边形 STL + 孔洞（Wave SS，D048）

v6（D039）的 marching-squares 用**形心扇区**封顶，只对 star-convex 环有效、不能表示孔洞。
v7 用 **ear clipping** 三角化任意简单多边形（凹/非 star-convex），并用可见性桥把孔洞
（even-odd 嵌套）并入外环后再切：

```python
from structure_optimizer.core.stl_export import (
    ear_clipping_triangulate, triangulate_with_holes, write_stl_polygon)

L = [(0,0),(4,0),(4,1),(1,1),(1,4),(0,4)]              # 凹 L 形
pts, tris = ear_clipping_triangulate(L)                # 面积守恒到 1e-12
outer = [(0,0),(10,0),(10,10),(0,10)]; hole = [(3,3),(7,3),(7,7),(3,7)]
pts, tris = triangulate_with_holes(outer, [hole])      # 面积 = 100−16 = 84
info = write_stl_polygon(outer, "part.stl", holes=[hole], z_thickness=2.0)
# info["is_watertight"] == True；info["cross_section_area"] == 84.0
```

**关键 / 诚实边界**：凹多边形 + 星形 + 双孔面积守恒均到 **1e-12**；挤出棱柱**水密**（每条边
恰被 2 个面共享）。对比：形心扇区在 L 形给 **11**（真值 7）——这正是需要 ear-clipping 的原因。
边界：O(n²)（截面环规模够用，非百万顶点）；孔桥用**暴力可见性**（慢但易验证正确）；
`write_stl_marching_squares` **未改**（凸 iso-contour 仍用扇区），把 MS 嵌套环接入 ear-clipping
是后续（见 D048 reopening）。

---

## 18. v8 — closing the loop: gradient drivers & general distributions

v8 把 v7 的半成品 driver **闭成完整环**，并把不确定性/几何提升到一般情形。每个 wave 源自
v7（或更早）ADR 的 reopening criterion。

### 18.1 几何非线性 TO 完整 OC 环（Wave UU，D050）

v7（D044）给了完整 TL 伴随灵敏度但没接驱动器；v8 用它驱动一个**完整 OC 环**（每次迭代
= 正向 TL + 伴随 → 滤波 → OC 更新），目标是大变形端柔度：

```python
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.nonlinear_simp import nonlinear_to_oc

config = load_benchmark("cantilever", preset="smoke")
mesh = create_structured_mesh(config)
res = nonlinear_to_oc(config, mesh, n_load_steps=4, max_iter=15)
# res.compliance_history 单调下降（2066→584）；res.volume_history 守恒在 0.45
```

**关键 / 诚实边界**：TL 端柔度大幅下降 + 体积守恒；**大变形真的有影响**——TL-aware 最优解
在 TL 柔度下比"线性 SIMP 最优解"低 ~8%（拓扑也可区分 L2/√n≈0.066）。但差异**幅度随载荷**：
轻载差异小、重载（~5×）差异 ~15% 且布局明显不同。是 **OC 非 MMA**、单目标；"beats linear"
不等式需环**收敛够**（截断的环在重载下可能反而高于已收敛的线性解），故测试用 15 迭代留足
余量（见 D050）。每迭代一次 TL 正向+伴随，比线性 SIMP 慢（~17s/15 迭代）。

### 18.2 滤波动态柔度 TO 完整环（多频带，Wave VV，D051）

v7（D047）只做单频 + 无滤波；v8 升级到**多频带平均** J=mean_ω|fᵀû(ω)|² + **Sigmund 滤波**：

```python
import numpy as np
from structure_optimizer.core.freq_response import dynamic_compliance_to
omegas = np.linspace(30, 70, 5)
res = dynamic_compliance_to(config, mesh, omegas, alpha=0.5, beta=1e-4, n_steps=18)
# res.objective_history 单调降；res.peak_before/after = 全带峰值（2.60→1.06）
```

**关键 / 诚实边界**：带平均 J 单调降 ~83% + **全带**峰值下降（多频比单频的增量价值）+ 体积守恒；
Sigmund 滤波**抑制 checkerboard**（直接平滑性质：0.36→5e-4）。用**投影梯度非 OC**——动柔度
灵敏度在共振附近变号，OC 正乘子二分不适用（见 D051）。checkerboard 锚点验的是"滤波器平滑性质"，
不是最终设计前后对比（这个温和的环本身不产生 checkerboard，无可减）。

### 18.3 梯度种子 NSGA-III（Wave WW，D052）

v7（D046）的 NSGA-III 随机初始化、打不过梯度 SIMP；v8 用 `run_simp` 在多个体积分数的最优解
**热启动**初始种群：

```python
from structure_optimizer.core.multi_objective_to import gradient_seeded_multi_objective_to
res = gradient_seeded_multi_objective_to(config, mesh, n_generations=10, population_size=12,
                                         seed_volume_fractions=(0.2, 0.35, 0.5, 0.65, 0.8))
# res.hv_history[-1] 比随机初始化高 ~45%；res.front_objectives 最低柔度端 = 梯度质量
```

**关键 / 诚实边界**：同预算下种子前沿超体积 **+45%** > 随机，最低柔度端 223 vs 2094（梯度质量，
~9× 更优）。诚实读法是"**用梯度播种、用 NSGA 多样化**"，不是"NSGA 找到了这些"——巨大的柔度差
正反映梯度 SIMP 在单目标柔度上远胜梯度自由搜索。仍是双目标 smoke 网；≥3 目标 + 超体积-预算扫描
是后续（见 D052）。

### 18.4 一般 marginal Nataf（Gauss-Hermite，Wave XX，D053）

v7（D045）的等效相关只有 normal/lognormal 闭式；v8 用 **Gauss-Hermite 积分**支持任意 marginal
（新增 Weibull / Gumbel）：

```python
import numpy as np
from structure_optimizer.core.reliability import (
    Marginal, nataf_correlation_gauss_hermite, build_nataf_general)
w, g = Marginal("weibull", 2.0, 3.0), Marginal("gumbel", 1.0, 0.5)
rho_z = nataf_correlation_gauss_hermite(w, g, rho_x=0.6)   # 解 Nataf 积分
nataf = build_nataf_general([w, g], np.array([[1, 0.6], [0.6, 1]]))   # 任意 marginal
```

**关键 / 诚实边界**：GH 积分对 lognormal-lognormal **复现闭式**到 3e-11（证明积分正确，
Weibull/Gumbel 用同一积分，验证可迁移）；Weibull/Gumbel 矩与 round-trip 精确；ρ_x=0→0、单调。
新增 normal/lognormal/Weibull/Gumbel 四种；更多 marginal（GEV 等）只是 `Marginal` 扩展。
n_nodes=24 对这些光滑被积函数足够（闭式 cross-check 3e-11）。D045 闭式路径不变（见 D053）。

### 18.5 纤维转向热 TO（Wave YY，D054）

v7（D043）的各向异性热场方向固定；v8 把**方向角本身作为设计变量**优化（纤维转向）。
自伴随：dC/dθ_e = −scale_e·Tₑᵀ(∂ke_e/∂θ_e)Tₑ，∂ke/∂θ 由 dk/dθ=R'(θ)k₀R(θ)ᵀ+R(θ)k₀R'(θ)ᵀ：

```python
from structure_optimizer.core.thermal_simp import (
    orientation_sensitivity, fibre_steering_thermal_to, load_thermal_benchmark)
config, k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
g = orientation_sensitivity(config, mesh, rho, angles, kxx=5.0, kyy=1.0,
                            heat_sources=sources, thermal_bcs=bcs)   # dC/dθ
res = fibre_steering_thermal_to(config, mesh, rho, 5.0, 1.0, n_steps=20,
                                heat_sources=sources, thermal_bcs=bcs)
# res.compliance_history 单调降 ~33%；res.angles = 优化后的方向场
```

**关键 / 诚实边界**：orientation 灵敏度对中心差分 rel 1e-5（实测 ~1e-9）；**各向同性基张量
（kxx==kyy）灵敏度恒零**（旋转各向同性导体无效，精确解析检验）；最速下降使热柔度降 ~33% 单调。
仅优化**方向场**（密度固定）；耦合密度+方向、角度场滤波/连续化是后续（见 D054）。

### 18.6 系统可靠性（串/并联，Ditlevsen 界，Wave ZZ，D055）

v6/v7 的 FORM 只算**单**极限态；v8 处理**多失效模式系统**。串联系统（任一模式失效即失效）的
失效概率用 **Ditlevsen 二阶界**，需要二元正态 CDF Φ₂(−β_i,−β_j;ρ_ij)：

```python
import numpy as np
from structure_optimizer.core.reliability import (
    bivariate_normal_cdf, system_reliability_series, system_reliability_parallel)
r = system_reliability_series([2.0, 2.5, 3.0])               # 独立串联
rho = np.full((3,3), 0.8); np.fill_diagonal(rho, 1.0)
rc = system_reliability_series([2.0, 2.5, 3.0], rho)         # 相关串联
# r['p_failure_lower'/'upper'] = Ditlevsen 界；'simple_lower'/'upper' = 单模界
```

**关键 / 诚实边界**：二元正态 CDF 三个特例精确（ρ=0 乘积、Φ₂(0,0;ρ)=¼+asin(ρ)/2π 闭式、ρ→1→min）；
单模式串联=Φ(−β)；独立串联落在 Ditlevsen 界内且比简单界紧；**正相关降低串联失效**（模式重叠）。
ρ 钳到 0.999999，故 ρ=1 不精确退化（残差 ~2%，因 φ₂ 在 ρ=1 近奇异）；串联任意 m，并联仅 2 模式
（m>2 并联需多元正态 CDF，见 D055）。

### 18.7 marching-squares 嵌套环 → 带孔 ear-clipping 封顶（Wave AAA，D056）

v6 的 marching-squares 平滑边界用**质心扇形**封顶——只对星凸环正确且**不支持内孔**。带内孔的密度场
（如环形）会同时产生外环和内环，封顶必须把内环**挖掉**：

```python
import numpy as np
from structure_optimizer.core.stl_export import (
    classify_loops_even_odd, write_stl_smooth_holes)
# 偶奇嵌套：方块套方块 → 1 组 1 孔；不相交 → 2 组 0 孔
groups = classify_loops_even_odd(loops)        # [(outer, [holes]), ...]
info = write_stl_smooth_holes(mesh, densities, "holed.stl")
# info['cross_section_area'] = 外环 − 内环；info['is_watertight'] / 'n_groups'
```

**关键 / 诚实边界**：偶奇嵌套检测精确（射线投射定深度，偶=实心外环、奇=孔；三层嵌套→外环带孔+实心岛）；
面积守恒 = 外环−内环，1e-9（矩形孔与环形孔均成立）。**水密仅对洁净直角孔断言**：曲线（多顶点）孔用
零宽桥缝挖洞会留一条非流形边——这**不是** AAA 引入的回归，D049 既有 `write_stl_polygon` 在同一环形上
同样非水密（其方块孔测试恰好落在良态几何上）。无桥缝孔三角化（约束 Delaunay）是 reopening 项（见 D056）。

---

## 19. v9 — second-order drivers: constrained optimisers & coupled fields

### 19.1 MMA 驱动 TL 非线性 TO（Wave CCC，D058）

v8 的几何非线性 TO（`nonlinear_to_oc`）用**单移动极限 OC** 更新——只能处理一个约束（体积）。
v9 用 **MMA（移动渐近线法）** 驱动同一个 D044 TL 伴随灵敏度，把体积约束写成显式不等式
`g(x)=mean(x)−vf≤0`：

```python
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.nonlinear_simp import mma_nonlinear_to, nonlinear_to_oc
config = load_benchmark("cantilever", preset="smoke"); mesh = create_structured_mesh(config)
mma = mma_nonlinear_to(config, mesh, n_load_steps=3, max_iter=30)
# mma.compliance_history / volume_history / densities / converged
```

**关键 / 诚实边界**：全 TL 端柔度大幅下降（2066→553，3.7×）+ 体积可行（≤vf+0.02）+ **MMA 与
OC 竞争**（同体积下柔度在 OC 的 5% 以内，实测比值 0.946 即 MMA 比 OC 低 5.4%）。诚实声明：
在 **compliance-only** 问题上 MMA ≈ OC（不是碾压）；MMA 的真正价值是**额外约束**（应力/屈曲），
这是 reopening 项。体积约束是唯一接入的约束，`mma_step` 的多约束能力尚未使用（见 D058）。

### 19.2 特征频率带隙目标（Wave DDD，D059）

v8 的频域 TO 都建在受迫响应上；v9 直接在 **modal solver** 上做**带隙**（band-stop）目标：
把相邻两阶固有频率推开，`g = ω²_{m+1} − ω²_m`。质量归一化模态的特征值灵敏度是教科书闭式：

```python
from structure_optimizer.core.freq_response import band_gap_sensitivity, maximize_band_gap
gap, dgap = band_gap_sensitivity(config, mesh, densities, lower_mode=0)  # g 与 dg/dρ
res = maximize_band_gap(config, mesh, lower_mode=0, n_steps=20, move=0.1)
# res.gap_history / omega2_initial / omega2_final
```

**关键 / 诚实边界**：带隙灵敏度 `dg/dρ` vs 中心差分 rel 1.76e-6（`dλ_i/dρ_e =
φ_eᵀ(dk·ke − λ_i·dm·me)φ_e`，`φᵀMφ=1` 精确）+ 体积守恒爬升使带隙加宽 ~2.2× + 模态被推开。
诚实声明：假设**非重根**（重根处灵敏度是次梯度集，对称设计模态合并会失效）；驱动是**投影梯度
爬升**非 MMA；只做相邻模态带隙，未做**目标频带放置**或 minimax 频带（reopening 项，见 D059）。

### 19.3 ≥3 目标多载况 NSGA-III（Wave EEE，D060）

v7/v8 的密度场 NSGA-III 是 2 目标（柔度+体积）。v9 扩到 **≥3 目标多载况**：在多个**载荷工况**
下分别最小化柔度，再加体积。需要精确的 n 维超体积（HSO 切片算法）：

```python
from structure_optimizer.core.multi_objective_to import multi_load_case_to, hypervolume_nd
# 默认 2 工况（原载荷 + fx/fy 互换的水平载荷）+ 体积 = 3 目标
res = multi_load_case_to(config, mesh, n_generations=12, population_size=16)
# res.front_objectives (n_front, 3) / hv_history（累积存档单调）
# 可传 seed_genomes 做梯度 SIMP 暖启动
```

**关键 / 诚实边界**：精确 n-D 超体积 HSO（与 2D 公式一致 + 已知 3D 盒 + 容斥 0.375）+ Das-Dennis
3 目标精确组合数 `C(d+2,2)` + 三目标前沿单调 HV + **载况真冲突**（LC1 最优设计在 LC2 下更差）+
梯度种子暖启动提升 HV（1.51e9→1.93e9）且单目标端点锐化 8.4×。诚实声明：仍是**梯度自由**搜索
（种子是**注入**梯度端点，非 GA 自己发现）；HSO 是 `O(k^{n−1})`，不适合多目标大前沿（见 D060）。

### 19.4 Rosenblatt 变换（已知联合分布，Wave FFF，D061）

Nataf（D045/D053）用**边缘 + 相关矩阵**（假设高斯 copula）映射到独立标准正态。当**完整联合
分布**已知时，精确变换是 **Rosenblatt**——条件 CDF 链 `u_k = Φ⁻¹(F_{k|1..k-1}(x_k|…))`。
对多元正态联合，条件是高斯，故 `Φ⁻¹∘F_{k|..}` 退化为标准化条件：

```python
from structure_optimizer.core.reliability import build_rosenblatt_normal, form_hlrf
rt = build_rosenblatt_normal(mean, cov)      # X ~ N(mean, cov)
u = rt.x_to_u(x); x = rt.u_to_x(u)           # 条件 CDF 链 / 逆
beta = form_hlrf(rt.wrap_limit_state(lambda x: a0 - a @ x), n_vars=len(mean)).beta
```

**关键 / 诚实边界**：条件 CDF Rosenblatt == Cholesky 白化 `L⁻¹(x−μ)`，1e-10（Schur 条件 vs 前代
两独立推导一致）+ round-trip + 精确去相关 `Cov(U)=I` + 单位方差高斯下与 Nataf 一致 + FORM β ==
闭式 `(a₀−aᵀμ)/√(aᵀΣa)`。诚实声明：仅实现 **MVN 联合**；高斯 copula + 非高斯边缘会退化回 Nataf
（不增益）；真正非高斯联合（Clayton/Frank copula）是 reopening 项。Rosenblatt **依赖变量顺序**（见 D061）。

### 19.5 耦合密度 + orientation 热 TO（Wave GGG，D062）

D043 优化密度（固定方向）、D054 优化纤维方向（固定密度）。v9 **交替最小化**同时优化两者：
每个外循环 = 密度 OC 步（固定 θ）+ orientation 最速下降步（固定 ρ），循环到收敛：

```python
from structure_optimizer.core.thermal_simp import coupled_density_orientation_to
res = coupled_density_orientation_to(config, mesh, kxx=5.0, kyy=1.0,
                                     n_outer=8, n_orient_steps=8,
                                     heat_sources=sources, thermal_bcs=bcs)
# res.densities / angles / compliance_history（逐 cycle 单调）/ converged
```

**关键 / 诚实边界**：交替最小化热柔度 ≤ 单独优化密度（实测 3.1×）且 ≤ 单独优化 orientation（17×）+
逐 cycle 单调下降（2.88e6→2.59e5）+ **各向同性退化**（kxx==kyy → dC/dθ≡0 → 精确等于纯密度 TO，
角度恒 0）。诚实声明：**块坐标交替**非同时 (ρ,θ) MMA（收敛到块坐标驻点，未必全局联合最优）；密度步
OC + 方向步最速下降，均非 MMA；无角度场制造约束（reopening 项，见 D062）。

### 19.6 系统可靠性驱动 TO（Wave HHH，D063）

D042 把体积分数驱动到**单**极限态的目标 β；D055 给了系统可靠性（Ditlevsen 界）。v9 把拓扑驱动到
目标**系统** β：多个失效模态（各自 d_allow_i + 独立载荷因子 s_i），系统失效 `P_f,sys=1−∏(1−P_i)`：

```python
from structure_optimizer.core.rbto import system_rbto_simp
res = system_rbto_simp(config, mesh, d_allows=[da, da*1.1], beta_target=2.0,
                       load_covs=[0.15, 0.15], vf_low=0.2, vf_high=0.85)
# res.volume_fraction / beta_system / per_mode_betas / p_failure_system
```

**关键 / 诚实边界**：体积二分达到目标系统 β（vf 0.413, β_sys 2.06≥2.0）+ **β_sys < min 单模态 β**
（独立 2 模态系统比任一模态更难）+ 单模态**精确退化**到 D042 `rbto_simp` + 体积随目标 β 单调 +
独立 Pf 落在 D055 Ditlevsen 界内。诚实声明：模态视为**独立**（相关模态用 `system_reliability_series(ρ)`
是 reopening）；可靠性旋钮仍是**体积分数**（非逐模态拓扑塑形）；线性位移极限态（见 D063）。

### 19.7 slit-free 孔三角化（鲁棒水密，Wave III，D064）

AAA（D056）的平滑封顶用**零宽桥缝**挖孔，曲线孔（环形）会留非流形边 → **不水密**。v9 给出最简
**slit-free** 分解：每个实心格是平凡 y-monotone 四边形，逐格三角化（2 三角顶/底盖 + 实心↔空边墙），
无桥无缝 → 任意**边连通**孔拓扑都边流形水密：

```python
from structure_optimizer.core.stl_export import write_stl_slit_free_holes
info = write_stl_slit_free_holes(mesh, densities, "ring.stl")
# info['is_watertight'] / cross_section_area (=实心格数×格面积) / n_solid_cells
```

**关键 / 诚实边界**：环形孔 slit-free **水密=True** 而 AAA 同场=False（解决 D056 曲线孔限制）+ 面积=
实心格数×格面积精确 + 多曲线孔拓扑（4 环 + 双孔板）皆水密。诚实声明：**仅边连通区域**水密——
**对角 pinch**（棋盘：两实心格仅角接触）是真非流形，如实报 `False`（密度滤波后的拓扑优化设计无此问题，
原始随机场可能有）；**阶梯边界**（cell 分辨率），非平滑——平滑 + 鲁棒水密需 MS 轮廓的 CDT（reopening，见 D064）。

---

## 20. v10 — constraint-rich & manufacturable: 多约束优化器 + 一般 copula + 平滑水密几何

### 20.1 多约束 MMA：应力 p-norm + 体积（Wave KKK，D066）

v9 的 MMA（`mma_nonlinear_to`，D058）只接了**单约束**（体积），所以在 compliance-only 问题上只能
**追平 OC**——D058 诚实声明 MMA 的真正价值是**额外约束**。v10 把它兑现到应力情形。卡点是代码库
只有 **forward** p-norm von Mises 应力，**没有密度灵敏度**（v1.6 显式把"应力伴随"推迟到后续 ADR）。
D066 补上这条伴随：

```python
from structure_optimizer.benchmarks.registry import load_benchmark
from structure_optimizer.core.mesh import create_structured_mesh
from structure_optimizer.core.nonlinear_simp import multi_constraint_mma
from structure_optimizer.core.stress import stress_pnorm_sensitivity
config = load_benchmark("cantilever", preset="smoke"); mesh = create_structured_mesh(config)
sigma_pn, dsdrho = stress_pnorm_sensitivity(config, mesh, densities, p=8.0)  # 伴随灵敏度
r = multi_constraint_mma(config, mesh, sigma_limit=4.6e3, p=8.0, max_iter=60)
# r.stress_history / volume_history / compliance_history / densities / sigma_limit
```

应力 `σ_PN=(Σσ_e^p)^(1/p)`，每个 von Mises 应力是**线性于单元位移**的量的范数
（`σ_e²=(S uₑ)ᵀ V (S uₑ)`，`S=D·B` 逐单元常量），原始材料应力**无显式 ρ 依赖** → 纯伴随项
`dσ_PN/dρ_e = −dscale_e·(λₑᵀ kₑ uₑ)`，`K λ = ∂σ_PN/∂u`。两个不等式
`g₁=σ_PN/σ_lim−1≤0`、`g₂=mean(ρ)−vf≤0` 交给 `mma_step`。

**关键 / 诚实边界**：伴随灵敏度 vs 中心差分 rel-err ≤1e-4（实测 ~1e-7）+ 收敛时**两约束同时满足**
（σ_PN≤lim ∧ 体积≤vf）+ 应力约束**绑定**（σ_lim=0.7×纯体积设计应力时，σ_PN 6.56e3→4.59e3 压到限值，
体积守 0.450）。诚实声明：用的是**原始材料应力 p-norm，非 SIMP-松弛应力**（不处理应力奇异性，
是 reopening 项）；von Mises 用 `_approx_element_stress` 单点有限差分应变（非高斯点 B 矩阵积分）；
目标是**线性**柔度（非全 TL）；`converged` 标志在绑定点 `|Δx|` 抖动时可能读 False，测试断言可行性/绑定
而非该标志。

### 20.2 目标频带放置：minimax around target（Wave LLL，D067）

v9 的带隙波（DDD，`maximize_band_gap`）只把两阶**特征值**推开。D059 的 reopening 项是**目标频带放置**——
最小化目标频带内的**最坏受迫响应**（band-suppression / 隔振）。代码库已有单频灵敏度
`dynamic_compliance_sensitivity`（J(ω)=|fᵀû|² + dJ/dρ），缺的是**带内 minimax 聚合**：

```python
from structure_optimizer.core.freq_response import target_band_placement, target_band_peak_sensitivity
from structure_optimizer.core.modal import solve_modal
import numpy as np
w1 = float(np.sqrt(solve_modal(config, mesh, densities, n_modes=1).omega_squared[0]))
band = np.linspace(0.85*w1, 1.15*w1, 7)                       # 跨第一阶共振的频带
peak, dpeak, J = target_band_peak_sensitivity(config, mesh, densities, band, beta=1e-4, p=12.0)
r = target_band_placement(config, mesh, band, beta=1e-4, n_steps=20, p=12.0)
# r.peak_initial / peak_final / peak_history / densities
```

带内峰值用 p-norm 平滑：`J_PN=(Σ_k J(ω_k)^p)^(1/p) → max_k J(ω_k)`（p→∞），灵敏度链式
`dJ_PN/dρ = Σ_k (J_k/J_PN)^(p−1)·dJ_k/dρ`。体积守恒的 move-limited 投影梯度**下降**（与带隙波同款，方向取负）。

**关键 / 诚实边界**：带内峰值灵敏度 vs 中心差分 rel-err ≤1e-4（实测 ~1e-7）+ 优化后**真实最坏带内响应**
`max_k J(ω_k)` 大降（实测跨一阶共振 4.33e5→6.75e4，−84%）+ 体积守恒（≤1e-6）。诚实声明：用的是**平滑 minimax**
（p-norm，非精确 max，p=12 高估真峰几个百分点）；频带是**用户固定采样**（不自适应跟踪移动的共振）；优化器是**一阶
投影梯度**（非 MMA，把峰值做成 D066 多约束 MMA 的约束是 reopening 项）；`beta=1e-4` 默认阻尼保证带内解不奇异。

### 20.3 泛化 NSGA driver + IGD⁺ 指标（Wave MMM，D068）

D060 后代码库有**两个几乎一样的 NSGA-III 循环**：`multi_objective_to`（柔度+体积，2 目标）和
`multi_load_case_to`（各载况柔度+体积，≥3 目标），只差目标数 / 参考点 / 用哪个 hypervolume。D060 的
reopening 项就是**单个泛化 `nsga3_density_to`** + **多目标 IGD⁺** 指标：

```python
from structure_optimizer.core.multi_objective_to import nsga3_density_to, igd_plus
# 单一驱动统辖 2/3/N 目标：n_obj = len(load_cases)+1
r = nsga3_density_to(config, mesh, load_cases=[list(config.loads), swapped_lc], n_generations=12)
val = igd_plus(obtained_front, reference_pareto_front)   # 越小越好，0 ⇔ 弱支配参考前沿
```

`nsga3_density_to` 在 `n_obj==2` 用 `hypervolume_2d`、否则 `hypervolume_nd`，所以两个旧驱动**逐位复现**
（golden baseline 验证）。`multi_objective_to` / `multi_load_case_to` 现在只是薄壳委托。IGD⁺:
`d⁺(z,a)=sqrt(Σ_i max(a_i−z_i,0)²)`、`IGD⁺=mean_z min_a d⁺`，弱 Pareto 相容（支配参考前沿则记 0，胜过朴素 IGD）。

**关键 / 诚实边界**：2-obj / 3-obj 委托**逐位一致**（front objectives / densities / hv history 全 `array_equal`，
对照重构前 golden baseline hv[-1] 118455.6190 / 1.5067600610e9）+ IGD⁺ 闭式（手算 3 点例=1/3；四分之一圆解析前沿
径向外推 δ → IGD⁺=δ）+ 4 目标可跑。诚实声明：这是**保行为 DRY 重构**（不是算法改进，NSGA-III 仍无梯度）；IGD⁺ 需
调用方提供**参考前沿**（真实 TO 问题无解析前沿，只能用代理参考，是相对收敛非绝对）；`n_obj==2→hypervolume_2d`
派发纯为逐位兼容。

### 20.4 Archimedean copula Rosenblatt：Clayton / Frank（Wave NNN，D069）

D061 的 `RosenblattTransform` 只支持**多元正态**（依赖完全由协方差描述），无法表达**尾部相关**
（两个载荷一起飙高的概率远超高斯 copula 预测）。D061 的 reopening 项就是**非高斯 Rosenblatt（Clayton/Frank
copula）**：

```python
from structure_optimizer.core.reliability import clayton_copula, frank_copula, build_copula_rosenblatt, Marginal
cop = clayton_copula(4.0)                              # 下尾相关；frank_copula(θ) 对称无尾相关
cop.conditional_cdf(u1, u2)                            # Rosenblatt 条件 CDF C_{2|1}=∂C/∂u₁
cop.conditional_ppf(u1, w)                             # 闭式逆
cop.kendall_tau()                                      # Clayton θ/(θ+2) / Frank 1−4/θ(1−D₁(θ))
rb = build_copula_rosenblatt([Marginal("normal",10,2), Marginal("lognormal",0.5,0.3)], cop)
z = rb.x_to_u(x)   # 物理 → 独立标准正态；rb.wrap_limit_state(g) 直接喂 form_hlrf
```

双变量 Archimedean copula `C(u,v)` 用单生成元耦合两个均匀边缘，Rosenblatt 条件 CDF
`C_{2|1}(u₂|u₁)=∂C/∂u₁` 复合 `Φ⁻¹` 把相关对映射到独立标准正态供 FORM 用。

**关键 / 诚实边界**：条件 CDF round-trip ≤1e-9（Clayton ~1.4e-10 / Frank ~2.8e-15）+ θ→0 退化到独立
（`C_{2|1}→u₂`、`C→u₁u₂`，误差 ≤2θ）+ Kendall τ 闭式（Clayton θ/(θ+2) 精确；Frank Debye D₁ 经 numpy Simpson，
与 1500 样本经验 τ 差 <0.03）。诚实声明：**仅双变量**（d 维需生成元的 d−1 重条件）；**仅 Clayton/Frank**
（Gumbel 无闭式条件逆，省略）；Frank τ 的 Debye 是 2000 点 Simpson 近似（非解析）；假设**联合已知**（不从数据拟合 copula）。

### 20.5 同时 (ρ,θ) MMA 耦合（Wave OOO，D070）

D062（`coupled_density_orientation_to`）用**块坐标交替最小化**（密度 OC 步 → 取向最速下降步，循环），交替会卡在
坐标式驻点。D062 的 reopening 项就是**同时 (ρ,θ) MMA**：把 `[ρ_design; θ_design]` 堆成一个设计向量，一次 MMA
同时动 ρ 和 θ：

```python
from structure_optimizer.core.thermal_simp import simultaneous_density_orientation_mma, load_thermal_benchmark
config, _k, sources, bcs = load_thermal_benchmark("heat_sink", preset="smoke")
r = simultaneous_density_orientation_mma(config, mesh, kxx=5.0, kyy=1.0, max_iter=40,
                                         heat_sources=sources, thermal_bcs=bcs)
# r.densities / angles / compliance_history / volume_history
```

目标梯度堆叠两个自伴随灵敏度 `dC/dρ`（D043，密度滤波）+ `dC/dθ`（D054）；唯一约束体积 `g=mean(ρ)−vf≤0`
只作用在 ρ 块（`∂g/∂θ≡0`）。角度盒约束 `[−π/2, π/2]`（张量周期 π，π/2 覆盖所有方向）。

**关键 / 诚实边界**：合并灵敏度 `[dC/dρ; dC/dθ]` vs 中心差分两块都 ≤1e-4（实测 ~1e-8）+ 同时 MMA 柔度
**≤ 交替最小化**（heat_sink smoke kxx=5/kyy=1：同时 2.0949e5 vs 交替 2.5905e5，优 19%）+ 体积可行（≤vf+0.02）。
诚实声明：**热**柔度（非弹性耦合）；"≤交替"是**本基准经验非定理**（MMA 是局部优化器，病态起点可能更差，测试留 1.001 容差）；
θ **未滤波**（无 fibre-continuity 约束，角度场可局部粗糙）；单体积约束（与 D066 应力约束合并是 reopening 项）。

### 20.6 相关系统模态驱动 TO（Wave PPP，D071）

D063（`system_rbto_simp`）的系统 RBTO 把失效模态当**统计独立**（`P_f=1−∏(1−P_i)`）。真实模态共享载荷不确定性
→ 相关。D063 的 reopening 项就是**相关系统模态 via `system_reliability_series(ρ)`**：

```python
from structure_optimizer.core.rbto import correlated_system_rbto_simp
r = correlated_system_rbto_simp(config, mesh, d_allows=[1.3,1.5], beta_target=2.5,
                                rho_modes=0.8, load_covs=[0.12,0.12])
# r.beta_system / volume_fraction / per_mode_betas / feasible
```

按标量模态间相关 `ρ` 建等相关矩阵 `R=(1−ρ)I+ρ·11ᵀ`，喂 `system_reliability_series` 经**bivariate normal CDF Φ₂**
算 Ditlevsen 二阶界，取界中点。**正相关降低并联失效概率**（模态一起失效而非独立）→ β_sys 升 → 所需体积降。
`rho_modes=0` 时**精确退化**到 `system_rbto_simp`。

**关键 / 诚实边界**：ρ=0 退化到独立（β/P_f/体积/densities 全 <1e-9）+ 方向正确（ρ:0→0.9 → β_sys 2.4764→2.4985 单调升）
+ 用 Φ₂（同 β_target 下 ρ=0.8 体积 ≤ ρ=0）。诚实声明：**单标量等相关**（非逐对矩阵）；P_f 取 **Ditlevsen 界中点**
（2 模态精确，≥3 模态带界差）；ρ 是**建模输入**非 FORM MPP 方向余弦导出（标量限状态无 MPP 向量）；限 `ρ∈[0,1)`
（排除负相关与 ρ→1 奇异）；并联 `system_rbto_simp` bisection（不改 HHH）。

### 20.7 平滑且水密的带孔三角化（Wave QQQ，D072）

两个早期几何波各得一项失一项：AAA（D056）**平滑**轮廓但桥缝 cap **非水密**（曲线孔）；III（D064）**水密**棱柱但
**阶梯**边界。D064 的 reopening 项是 **constrained-Delaunay 平滑+水密孔**。QQQ 为 rubric 针对的**环形孔（annulus）**
用 **ribbon 法**解决（不用全 CDT）：

```python
from structure_optimizer.core.stl_export import write_stl_smooth_watertight_holes
info = write_stl_smooth_watertight_holes(field, x_coords, y_coords, "ring.stl", n_samples=128)
# info['is_watertight'] / cross_section_area (≈外−内) / n_annuli / n_triangles (=8·n_samples/环)
```

对每个单孔区域：外/孔平滑轮廓各重采样到 `n_samples` 点 → 角度对齐 → `i↔i` 连成 **quad 条带**做顶/底 cap + 两侧墙。
quad 条带拓扑**构造即边流形**（每根 rung 被 2 个 cap 三角共享，每条轮廓边被 1 cap + 1 墙共享）→ 与几何无关地水密，
同时轮廓保持平滑。

**关键 / 诚实边界**：环形孔平滑轮廓**水密=True**（同场 AAA=False）+ 面积≈平滑外−内（≤5e-3：圆环 0.00%/椭圆环 0.06%）
+ 每边恰 2 三角（解析 STL 边直方图全 2）+ 椭圆环也水密。诚实声明：**仅 annulus（单孔/区域）**，0 孔或 ≥2 孔 raise
（多孔平滑水密仍需 CDT，是 reopening 项）；轮廓**重采样**（面积"≈"非精确）；水密是**拓扑**（强偏心孔 rung 可能几何自交但仍边流形）；
顶/底是 **2.5D 挤出**（非真 3D 曲面）。

---

## 21. v11 — exact & robust：应力奇异性松弛 + 一般 copula + 精确系统积分 + 约束 Delaunay

### 21.1 qp-relaxed 应力：消除应力奇异性（Wave SSS，D074）

D066 的多约束 MMA 用**原始** von Mises p-norm 应力——它不处理经典的**应力奇异性**：当 ρ_e→0 时材料应力
σ_vm,e(u) 仍**有限**（只依赖状态 u，不依赖 ρ），于是可行域在孔洞角落长出梯度法逃不出的细尖刺。D066 的第一条
reopening 就是 **qp-relaxed / ε-relaxed 应力**。SSS 落地标准的 **qp 松弛**（Bruggi）：约束应力换成
`σ̃_e = ρ_e^q · σ_vm,e(u)`，松弛指数 `q < p_simp`，使低密度单元贡献**趋零**应力，尖刺消失。

```python
from structure_optimizer.core.stress import qp_relaxed_stress_pnorm_sensitivity
from structure_optimizer.core.nonlinear_simp import qp_stress_constrained_mma

# 灵敏度：显式 ρ^q 项 + 隐式 adjoint（合起来 vs central-FD ≤1e-4）
sigma_pn, dsdrho = qp_relaxed_stress_pnorm_sensitivity(config, mesh, densities, p=8.0, q=2.5)

# 最小柔度 s.t. 松弛应力 ≤ 限值 且 体积 ≤ vf（双约束 MMA）
r = qp_stress_constrained_mma(config, mesh, sigma_limit=lim, p=8.0, q=2.5, vf=vf, max_iter=120)
# r.stress_history 记录松弛 σ̃_PN；r.densities / volume_history / converged
```

聚合量 `σ̃_PN = (Σ_e (ρ_e^q·σ_e)^p)^(1/p)`。因为 `σ̃_e` 同时含**显式** ρ^q 因子和**隐式**状态依赖，总导数干净拆成
显式项 `w_e·q·ρ_e^(q−1)·σ_e` + 隐式 adjoint 项 `−dscale_e·(λₑᵀkₑuₑ)`（`w_e=(σ̃_e/σ̃_PN)^(p−1)`，`Kλ=∂σ̃_PN/∂u`）。
显式项正是 D066 纯隐式 adjoint 所没有的部分——所以测试锚点 1 专门用 central-FD 验证它（≈1e-7）。

**关键 / 诚实边界**：qp 灵敏度 vs central-FD ≤1e-4（验证显式项）+ 松弛按 ρ^q 抑制奇异性（ρ≈0.2 → ρ^2.5≈0.018，>50×
抑制）+ qp 约束 MMA 双约束同时生效（探针 120 迭代：基线 σ̃_PN 2321 → 约束 1625.2 ≤ 限 1625.0，体积守 0.450）。
**屈曲约束驱动 deferred**：仓内 `buckling_sensitivity`（v4）是**分析级非设计级**——忽略 ∂u/∂ρ + 无 void-mode 松弛；
探针显示定容 λ_crit ascent **反而**把 λ_crit 从 20.1 拉到 8.1（灵敏度指错方向），所以 SSS 重新限定为**仅 qp 应力**，
屈曲驱动连同探针证据移入 D074 reopening（绝不谎称屈曲可用）。松弛指数 q=2.5/p=8 非自调；底层仍是 `_approx_` 单元中心应力。

### 21.2 自适应频带采样 + peak-as-constraint（Wave TTT，D075）

D067 在**固定** ω 网格上采样、把 peak 当**目标**做投影梯度下降。两个毛病：共振很**尖**，固定粗网格可能整段落在采样点
之间——优化器"压低"了一个它从没量到的峰；且 peak 只能当目标，无法表达"在保证带内响应不超标的前提下最小化别的量"。
TTT 两个都解决。

```python
from structure_optimizer.core.freq_response import adaptive_band_sample, peak_constrained_mma

# 自适应采样：从 n_init 均匀点出发，n_refine 次"向峰二分"加点
ab = adaptive_band_sample(config, mesh, rho, omega_lo, omega_hi, n_init=7, n_refine=18, beta=2e-6)
# ab.peak_value / peak_omega / omegas / values / n_evals

# peak-as-constraint：最小化静柔度 s.t. 带内 peak ≤ 限值 且 体积 ≤ vf（复用 D066 双约束 MMA）
r = peak_constrained_mma(config, mesh, peak_limit=lim, band_omegas=band, beta=1e-4, vf=vf, max_iter=100)
# r.peak_history / compliance_history / volume_history / densities
```

自适应方案每步**二分当前峰相邻、端点响应和更大的子区间**，把算力堆到共振附近。peak-as-constraint 复用 D066 的双
约束 MMA 结构，把应力换成带内 p-norm peak 灵敏度（`target_band_peak_sensitivity`），目标改静柔度、体积单独做约束
——这样优化不会塌到 min density。

**关键 / 诚实边界**：自适应 25 evals 还原 dense-400 参考峰**误差 0.015%**，而同等规模 uniform-7 **低估 ≥20%**（探针 41%）
+ 最近样本距峰 < 初始间距/8 + peak 约束 MMA 把峰从 3.99e5 压到 2.23e4 ≤ 限 2.14e4（binding）体积守 0.450。
**两条硬诚实边界**：(1) **必须有阻尼**——无阻尼时 ω=ω_n 处 `D=K−ω²M` 奇异、J→∞（探针见 4e30 共振奇点），所以用小
Rayleigh β；(2) **约束必须是频带不是单频**——单频约束会被"失谐"白嫖（优化器把共振挪开单一采样点，真峰反而涨；探针
min-volume+单频 → 体积塌到 0.01、真峰炸到 2.6e9），故聚合多频 p-norm + 目标取柔度而非最小化材料。贪心二分非全局
band-max 证明（双共振时次峰可能欠解析）；MMA 内每步用**固定** band_omegas（不在循环里重采样）——这些都进 D075 reopening。

### 21.3 reference-free 多目标质量指标：R2 + 自动参考点 hypervolume（Wave UUU，D076）

D068 的 IGD⁺ 需要一条**真 Pareto 前沿**做参考——但实际优化中你恰恰没有它（有了就不用优化了）。两个标准指标绕开参考
前沿：**R2 指标**（Tchebycheff）只要权重集 + utopia 点；**hypervolume** 只要参考点。UUU 落地两者的 reference-front-free 版本。

```python
from structure_optimizer.core.multi_objective_to import r2_indicator, reference_free_hypervolume

# R2（越小越好）：权重默认 Das-Dennis，ideal 默认前沿逐维 min（比较多前沿须传共享 ideal+weights）
r2 = r2_indicator(front, weights=None, ideal=shared_ideal)   # (1/|W|)Σ_λ min_a max_j λ_j(a_j−z*_j)

# 自动参考点 hypervolume（越大越好）：ref = max + margin·(max−min)，委托精确 hypervolume_2d/_nd
hv = reference_free_hypervolume(front, margin=0.1)
```

**关键 / 定量锚点**：R2 闭式（单点前沿 {(1,1)}，权重 {(1,0),(0,1),(0.5,0.5)}，utopia (0,0) → 5/6，机器精度匹配）+ 弱
Pareto 兼容（支配前沿 R2 严格更低；加入被支配解 R2 不变）+ **三指标排序一致**：4 条嵌套更优前沿上，R2/refHV/IGD⁺
给出完全相同序 [3,2,1,0]——没有真前沿（用不了 IGD⁺）的人靠 R2/refHV 得到同样裁决 + 自动参考点 HV 加非支配点严格增。

**诚实边界**：R2 **比较多前沿必须共享 ideal+weights**（默认用各自 min 比较无意义）；R2 收敛性只透过所选标量化方向感知，
粗权重集会漏前沿间隙（非多样性指标替代品）；排序一致是**良构嵌套前沿上的经验等价非定理**——交叉权衡的不可比前沿会
（正当地）分歧；refHV 的 margin 是**约定**（同 margin 下不影响排序，跨前沿比较仍首选共享显式参考点）。HV 算法本身仍是
D068 的精确版，UUU 只加参考点推导便利。

### 21.4 Gumbel copula + d 维交换 Clayton（Wave VVV，D077）

D069 给了双变量 Clayton/Frank（下尾/无尾相依），但缺**上尾相依的 Gumbel**，且 Rosenblatt 变换写死 2 变量。VVV 两个都补。

```python
from structure_optimizer.core.reliability import gumbel_copula, build_clayton_rosenblatt, Marginal

g = gumbel_copula(2.3)                 # θ≥1，上尾相依
w = g.conditional_cdf(u1, u2)          # C_{2|1}=∂C/∂u1（闭式）；逆用二分（无闭式）
tau = g.kendall_tau()                  # 1 − 1/θ

# d 维交换 Clayton 的 Rosenblatt 变换（闭式生成元导数 → 全闭式 sequential）
T = build_clayton_rosenblatt([Marginal('normal',0,1)]*4, theta=1.7)
z = T.x_to_u(x); x_back = T.u_to_x(z)  # form_hlrf 直接复用 T.wrap_limit_state
```

d 维交换 Clayton 用生成元 `φ(u)=u^{-θ}−1`、逆 `ψ(s)=(1+s)^{-1/θ}`。因为 `ψ^{(j)}` 的常数因子和符号在条件比值里**抵消**，
条件 CDF 是闭式 `C_{k|1..k-1}=(T_k/T_{k-1})^{-(1/θ+k−1)}`（`T_j=Σ_{i≤j}u_i^{-θ}−(j−1)`），逆也闭式——所以任意维全解析。

**关键 / 定量锚点**：Gumbel 条件 CDF vs 数值 ∂C/∂u1 ≤1e-6 + 二分逆 round-trip ≤1e-9 + τ=1−1/θ；d 维 Clayton 条件 CDF
**对上混合偏导比值**（真 Rosenblatt 定义）≤1e-5（实测 4e-7）+ z→x→z round-trip ≤1e-9（d=3,4）+ 3000 样本经验 τ 还原
θ/(θ+2)（±0.04）。**诚实边界**：Gumbel 逆是**二分非闭式**；d 维仅**交换 Clayton**（单 θ 全对称）——非嵌套/分层、非 d 维
Gumbel/Frank（后者生成元导数需 Bell 多项式/数值微分，deferred）；marginal 仍走正态映射不在此改进；未暴露尾相依系数。

### 21.5 Genz 精确多元系统失效概率（Wave WWW，D078）

D055/D071 的串联系统 P_f 是 **Ditlevsen 二阶界**（一个区间，由两两 Φ₂ 拼出），不是精确值。WWW 用 **Genz (1992)**
分离变量 Monte Carlo 算**精确**的 m 维正态 CDF `Φ_m(b;R)`，支持**全相关矩阵**。

```python
from structure_optimizer.core.reliability import genz_mvn_cdf, system_reliability_series_exact

phi_m = genz_mvn_cdf([b1,b2,b3], R, n_samples=20000, seed=0)   # P(Z≤b), Z~N(0,R)
pf = system_reliability_series_exact(betas, R)                  # 1 − Φ_m(β;R)，单一精确值
```

Cholesky `R=LLᵀ`，下界 −∞ 时截断积分分离成乘积，对均匀样本 `w∈[0,1]^{m−1}` 求平均：`e₁=Φ(b₁/L₁₁)`，
`y_{i-1}=Φ⁻¹(w_{i-1}·e_{i-1})`，`e_i=Φ((b_i−Σ_{j<i}L_ij y_j)/L_ii)`，`Φ_m≈mean(Π_i e_i)`。

**关键 / 定量锚点**：Genz 退化到 m=2 对上精确 Gauss-Legendre Φ₂ ≤1e-3；独立 R=I 时 `Φ_m=ΠΦ(b_i)` 精确 ≤1e-12；
精确串联 P_f（4.13e-2）落在 Ditlevsen 界 [4.09e-2,4.15e-2] **之内**（独立交叉验证）；确定性 + 非 SPD/形状报错。
**诚实边界**：Genz 是 **MC 估计非闭式**——n_samples→∞ 才收敛到精确，默认 2 万样本标准误 ~1e-3~1e-4（"精确"=无偏收敛非
逐位）；用**朴素 MC 非随机化点阵**（Korobov 点阵收敛快一个量级，是 reopening）；维数高/强相关时精度退化（测到 m≤4）；
**R 必须 SPD**（秩亏 ααᵀ 需 nudge 0.98R+0.02I，不内置 ridge 以免掩盖病态）；仍设 FORM 线性化极限状态。

### 21.6 弹性正交各向异性同时 (ρ,θ) MMA + fibre 连续性（Wave XXX，D079）

D070 把密度+纤维方向**一起**用 MMA 优化，但针对**热传导**张量。XXX 做**弹性**版：正交各向异性层合刚度 `D₀` 按
逐单元纤维角 θ 旋转，建 Q4 单元刚度——这些原来都没有（弹性 FEM 只有各向同性闭式 ke）。再加 **fibre 连续性**约束。

```python
from structure_optimizer.core.orthotropic_simp import (
    orthotropic_plane_stress_matrix, simultaneous_elastic_orientation_mma)

D0 = orthotropic_plane_stress_matrix(E1=2*E, E2=0.5*E, nu12=0.3, G12=0.4*E)
r = simultaneous_elastic_orientation_mma(config, mesh, D0, vf=vf,
        fibre_continuity_limit=0.14)   # None=仅体积约束
# r.densities / angles / compliance_history / continuity_history
```

旋转用**四阶张量** `C'=QQQQ:C`（工程剪切记账精确，避开易错的 Q̄ Reuter 矩阵），`dD/dθ` 经 `dQ/dθ` 解析。单元刚度
`∫BᵀDB` 2×2 Gauss，节点序对齐 mesh。连续性约束 = 相邻设计单元角差平方均值 ≤ 限值（梯度 = 设计图 Laplacian）。

**关键 / 定量锚点**：各向同性 D 时 ke **复现闭式** `element_stiffness` ≤1e-9（验 B/节点序/积分）+ 旋转：各向同性不变、
D(90°) 交换 E₁↔E₂、`dD/dθ` vs FD ≤1e-6 + dC/dρ 与**新增 dC/dθ** vs central-FD ≤1e-4（实测 9e-7/1e-5）+ 同时 MMA
柔度 1200→262 体积守 0.450 确定性 + 连续性约束 **binding**（自由 0.461 超限 → 约束后 0.138≤限，柔度可比）。
**诚实边界**：连续性度量是**原始角差平方非周期感知**（+89°/−89° 物理差 2° 却被罚大，周期感知 `sin²Δθ` 是 reopening）+
**单层平面非层合** + dense 装配每迭代重建 ke + MMA 非凸（约束版柔度更低是局部最优假象，只声明"可比"）。

### 21.7 约束 Delaunay 多孔平滑 + 水密（Wave YYY，D080）

D056 平滑多孔但桥缝 cap **非水密**（曲线孔）；D072 ribbon 水密但**仅 annulus（单孔）**。YYY 用**约束 Delaunay**
三角化多连通区域——无桥缝，支持**任意个孔**，构造即水密。

```python
from structure_optimizer.core.stl_export import write_stl_cdt_multi_hole, constrained_delaunay_triangulate

pts, tris = constrained_delaunay_triangulate(outer_loop, holes)   # 多孔 CDT
info = write_stl_cdt_multi_hole(outer_loop, holes, 'part.stl', n_samples=64)
# info['is_watertight'] / n_holes / cross_section_area
```

实现 = 全环顶点 Bowyer-Watson Delaunay → 按质心是否在区域内（外环内、所有孔外）过滤三角 → **验证不变量**：保留三角
的边界边（恰属 1 个三角的边）== 全部环边。满足则顶 CDT cap + 底 + 沿每条环边的墙 = 每边恰 2 facet → 水密。

**关键 / 定量锚点**：圆外环 **2 孔与 3 孔**均水密（独立边直方图证每边恰 2 facet）+ 截面积 ≈ 外−Σ孔 ≤1%（圆 r=1 减两 r=0.18）
+ CDT 边界边数 == 外+孔环边总数 + 0 孔（实心 π）/椭圆外环 2 孔均水密 + 退化输入报错。
**诚实边界**：**无 flip 约束恢复**——靠环边本就是 Delaunay 边（密采样平滑边界成立，已验证）；稀疏/强非凸边界缺约束边时
**显式报错**（`cdt_constraint_recovery_failed`）而非默默吐非水密网格（flip 恢复是 reopening）；O(n²) Bowyer-Watson；
水密是**拓扑边流形**（同 D072/D056 标准，不保证病态自交输入的几何非自交）；cap 是 **2.5D 挤出**；无 Steiner 点质量细化
（边界采样不均处可能瘦三角）；面积是**采样多边形面积**（"≈"随密采样收敛）。

---

## 22. v12 — design-grade & adaptive：设计级屈曲 + 循环内自适应 + 增广指标 + 分层 copula + 点阵积分 + 周期感知几何

### 22.1 设计级屈曲灵敏度：∂u/∂ρ 伴随（Wave AAAA，D082）

D074（v11）**defer 了屈曲驱动 TO**：既有 analysis-grade `buckling_sensitivity` 忽略几何刚度 `K_g=K_g(σ(u(ρ)))`
经状态 u 的**间接 ∂u/∂ρ 项**，探针显示定容 λ_crit ascent 反把 λ 从 20.1 拉到 8.1（梯度指错方向）。v12 AAAA 补上
伴随项，满足 D074 设的 entry condition（ascent 必须升 λ_crit）。

```python
from structure_optimizer.core.buckling import design_grade_buckling_sensitivity, maximize_buckling_load

dl = design_grade_buckling_sensitivity(config, mesh, rho, u, lam, phi)   # 含 ∂u/∂ρ 伴随，vs FD ≤1e-3
r = maximize_buckling_load(config, mesh, vf=vf, n_steps=30)              # 定容 λ_crit 上升 driver
# r.lambda_history（20.1→34.8）/ densities / volume_history
```

完整公式（φ 归一化使 φᵀ(−K_g)φ=1）：`dλ/dρ_e = dscale_e·φₑᵀkₑφₑ + λ·g_dscale_e·φₑᵀkgeₑφₑ − λ·μₑᵀ(dscale_e·kₑ)uₑ`，
伴随 `K μ = w`，`w=∂(φᵀK_gφ)/∂u`（K_g 对 u 线性，逐单元 `φₑᵀK_g^e(unit_k)φₑ` 组装）。第三项就是 analysis-grade 丢掉的
∂u/∂ρ 项。**void-mode relaxation** 旋钮：`assemble_geometric_stiffness(..., g_penalty=)` 越陡，低密度单元 K_g 越快趋零，
抑制伪局部屈曲模态（默认 = opt.penalty，行为不变）。

**关键 / 定量锚点**：design-grade dλ/dρ vs central-FD ≤1e-3（实测 4e-8，验证 ∂u/∂ρ 项）+ **entry condition**：
design-grade ascent 升 λ_crit（20.1→34.8）而 analysis-grade 降（20.1→8.1）+ maximize_buckling_load 终 λ>初 λ 体积可行确定性
+ g_penalty 旋钮 default 复现原 K_g、越陡 ‖K_g‖ 越小。**诚实边界**：是 **∂u/∂ρ 伴随**（非 void-mode）解了 smoke mesh
的 deferral；**单最低模无 mode-tracking**（屈曲 TO 有模态切换/重根，ascent 有 it₅≈8.4 瞬态下凹后爬升）；是 **ascent（最大化 λ）非约束**
（屈曲约束进 compliance 问题是下一步）；单 Gauss 点 K_g + dense 每步多一次 adjoint solve。

### 22.2 循环内自适应频带重采样：跟踪移动的共振（Wave BBBB，D083）

D075（v11）的 `peak_constrained_mma` 把峰约束的频带 **一次性固定** 在优化前。但结构刚度随材料重分布而变，
固有频率会漂移——smoke 悬臂上基频在一次 compliance-min 中漂 **+99%**（36867→73545 rad/s）。固定在初始共振处的频带
完全滑离共振：在终设计上它只读到真峰（dense sweep）的 **6.3%**（少报 94%）——p-norm 约束于是在管错频率。D075 的
reopening criterion 就是要 **循环内自适应重采样** 来补这个洞。

```python
from structure_optimizer.core.freq_response import adaptive_peak_constrained_mma

r = adaptive_peak_constrained_mma(config, mesh, peak_limit, omega_lo, omega_hi,
                                  beta=2e-6, vf=vf, max_iter=40)
# r.peak_omega_history（每步重定位的共振，如 36867→73545）/ densities / peak_history / converged
```

每步重跑 `adaptive_band_sample` 在全 `[omega_lo, omega_hi]` 重定位移动的共振 `ω_peak`，再把约束频带重建成
`ω_peak·linspace(1−w, 1+w, n_band)`（clip 到搜索范围）。约束因而全程跟踪共振。两条不等式沿用 D066/D075：
`g₁=J_peak/J_lim−1≤0`（带内峰）+ `g₂=mean(x)−vf≤0`（体积），目标是 SIMP 静柔度（`dc/dρ_e=−dscale_e·uₑᵀkₑuₑ`）。
轻阻尼默认 `beta=2e-6` 是刻意的：共振要够尖才**值得**跟踪（重阻尼单调响应无峰可追，固定/自适应频带重合），又够阻尼保证
有限稳定解（对照 TTT 无阻尼 J→∞ 奇异）。

**关键 / 定量锚点**（全锚定到独立 800 点 dense sweep）：共振漂移 ≥20%（实测 +99%）+ **in-loop 跑赢 stale 固定频带**：
终设计上 tracked band 读真峰误差 **4.0%** 而固定在初始共振的 band 误差 **93.7%**（且 stale 误差 > 3× tracked）+ 终设计对
dense sweep 可行（真峰 ≤1.05×limit、体积 ≤vf+0.02）+ 确定性 + 重阻尼退化（无峰可追时重采样 pin 到带下沿）+ 输入守卫。
**诚实边界**：在这个 **刚度对齐** 的 smoke 问题上 in-loop 与固定频带的 **设计几乎重合**——compliance-min 本就降峰（终 8.2e6 vs 初 7.0e8），
约束与目标同向、并不强 binding；这里 re-gridding 的价值是 **共振漂 +99% 时保持约束测量保真（4% vs 94%）**，不是产出不同设计。
真正 **峰约束与目标冲突** 的表述（如 min dynamic compliance @ ω_op s.t. tracked-peak）留作 reopening，**不在此声称**。
min-volume-s.t.-peak **不可用**（单目标 min-volume 由 detuning 坍到近空、真峰爆 40–120×，TTT 已记的失败，已复验）。
每步一次完整 `adaptive_band_sample`（≈21 次频响解）是跟踪的诚实成本；单最低共振无 mode-tracking。

### 22.3 增广 Tchebycheff R2 + Schott spacing 多样性指标（Wave CCCC，D084）

D076 的 `r2_indicator` 用纯 Tchebycheff `max_j λ_j(a_j−z*_j)`，但这个 max **看不见非约束目标**：两个点在 binding
坐标相等就同分，哪怕一个在其余目标上严格更优（dominates）——纯 R2 因此分不清 **weakly** efficient 点和 dominate 它的
**properly** efficient 点。另外 R2/IGD⁺/HV 全测收敛、没人测 **分布**。v12 CCCC 补上两者。

```python
from structure_optimizer.core.multi_objective_to import augmented_tchebycheff_r2, spacing_indicator

r2a = augmented_tchebycheff_r2(front, ideal=z, rho=0.05)  # max 项 + ρ·Σ ℓ₁ 项，破 tie 向 dominate 点
s   = spacing_indicator(front)                            # Schott 最近邻 ℓ₁ 间距标准差；越小越均匀，均匀→0
```

增广标量化 `g_aug = max_j λ_j(a_j−z*_j) + ρ·Σ_j λ_j(a_j−z*_j)`，`R2_aug=(1/|W|)Σ_λ min_a g_aug`。闭式性质：
`ρ=0` **精确退化**为 `r2_indicator`；`ρ>0` 且 front 在 utopia 之上时 `g_aug≥g_plain` 逐点成立 ⟹ `R2_aug≥R2` 恒成立。
Spacing `S=sqrt((1/(m−1))Σ(d̄−d_i)²)`，`d_i` 为点 i 的 ℓ₁ 最近邻距离——纯分布度量（不管离真前沿多近），**补充**而非替代收敛指标。

**关键 / 定量锚点**（全闭式）：`ρ=0` 退化 == 纯 R2（≤1e-12）+ `ρ>0` 时 augmented ≥ plain + **weak-vs-proper 区分**：
λ=(.5,.5)、z*=0 下 weakly (0.5,0.5) 与 dominate 它的 (0.5,0.3) 纯 R2 **同分** 0.25，augmented 严格偏好 dominate 点
（闭式 0.30 vs 0.29）+ spacing 均匀前沿 **S=0**、聚集前沿 S>0 且 permutation-invariant。**诚实边界**：`rho=0.05` 固定默认
不随目标尺度自适应（poorly-normalised front 上可能太弱/太强，建议归一化目标）；spacing **只测分布、可被钻空子**（两个极端点
S=0 却覆盖极差，必须配 extent 指标 + 收敛指标一起读，本波未发 extent）；ℓ₁ dense 两两距离 O(m²·n)；两指标都是**诊断**，
**未接进 driver**（augmented-R2 当 NSGA-III 选择键 / spacing 当 niching 项是 reopening）。

### 22.4 分层（nested）Clayton copula — per-cluster θ（Wave DDDD，D085）

D077 的 exchangeable Clayton 只有**一个 θ**，每对变量依赖相同。真实可靠性系统会分簇：子系统内强耦合、子系统间弱耦合。
两层 fully-nested Archimedean copula 表达这个：簇内 inner Clayton 用各自 `θ_g`，簇间 outer Clayton 用 `θ₀`。

```python
from structure_optimizer.core.reliability import nested_clayton_copula

c = nested_clayton_copula(dim=4, clusters=[[0,1],[2,3]], theta_outer=2.0, thetas_inner=[6.0,4.0])
c.cdf(u)                      # C(u)=ψ_θ₀(Σ_g φ_θ₀(C_g(u_g)))，C_g=ψ_θg(Σ φ_θg(u_i))
c.bivariate_margin_cdf(0,1,0.4,0.6)   # 同簇 → Clayton(θ_g=6) ; 跨簇 → Clayton(θ₀=2)
c.kendall_tau_within(0), c.kendall_tau_between()   # 6/8 vs 2/4
```

**嵌套条件**（Joe/McNeil，valid copula 的**充分**条件）：`θ_g ≥ θ₀ > 0`——簇内依赖至少和簇间一样强，`__post_init__` 强制。
bivariate margin 精确（其余维设 1，用 `ψ_θ₀(φ_θ₀(x))=x`）：同簇对 = Clayton(θ_g)、跨簇对 = Clayton(θ₀)，故簇内 Kendall
τ=θ_g/(θ_g+2)、簇间 τ=θ₀/(θ₀+2)。所有 θ 相等时**精确退化**为 exchangeable Clayton。

**关键 / 定量锚点**（全闭式）：θ 全相等退化 == exchangeable（≤1e-12）+ bivariate margins 精确匹配 Clayton(6)/Clayton(4)/Clayton(2)
+ per-cluster τ（6/8>4/6>2/4，簇内>簇间）+ valid copula（C(1..1)=1、零参 grounding→0、uniform margin）+ 4 阶混合偏导（密度）
grid 上 ≥0 + 嵌套条件/partition/计数守卫。**诚实边界**：**本波不发 nested Rosenblatt transform / sampler**——nested 的序贯条件
CDF 要穿两层 generator（Faà di Bruno）、精确采样要 Marshall-Olkin tilted-stable frailty（**非 numpy-trivial**，拉特殊函数库会蹭
numpy-only 红线），D077 的 exchangeable transform 仍是 FORM 主力，nested transform **reopened**；嵌套条件只是**充分**条件，
**不声称**用负密度检测其违反（probe 里 θ_inner<θ_outer 在测试 grid 上没出负密度）；**只两层、单 family（Clayton）**，深层级 /
混合 family / d-dim nested Gumbel 都 reopened（"non-Clayton d-dim" 只部分解决）。

### 22.5 Korobov 点阵 Genz + 报告标准误（Wave EEEE，D086）

D078 的 `genz_mvn_cdf` 用伪随机点采样（plain MC，误差 `O(N^{-1/2})`、**无可用误差估计**）。Genz 被积函数是光滑正态 CDF
乘积——正适合点阵规则。本波用 **随机移位 Korobov rank-1 lattice**：更快收敛 + shift 间散布给出**真实可报告的标准误**。

```python
from structure_optimizer.core.reliability import genz_mvn_cdf_lattice, system_reliability_series_lattice

res = genz_mvn_cdf_lattice(upper, R, n_points=1021, n_shifts=12, a=76)   # 生成向量 z=(1,a,..,a^{m-2}) mod N
res.value, res.std_error          # 估计 + 移位间散布标准误 std(ddof=1)/√n_shifts
pf, se = system_reliability_series_lattice(betas, R)   # P_f=1−Φ_m(β;R) + SE
```

每个随机移位 `Δ` 给点 `w_k=frac(k·z/N+Δ)`，跑一次 Genz 估计；`n_shifts` 个独立移位 → 均值是 value、散布是 SE。
`_genz_product_estimate` 内核与 D078 共享逻辑（但 **D078 原函数不动**，无回归）。

**关键 / 定量锚点**（参考 = equicorrelation 1-D Gauss-Hermite 约化，精确到求积；numpy-only）：独立情形精确（R=I → 被积常数 → ∏Φ(b_i)
≤1e-9）+ equicorrelation 4-D ρ=0.5 `|value−exact|≤4·SE` 且 SE<1e-3 + **等预算下跑赢 plain MC**（20 seed RMS < MC/3，probe 实测 ~25×）
+ **SE 是真误差估计**（|err|≤3·SE 在 ≥27/30 seed，且 SE 随 n_points 增大而缩小）+ system wrapper 报 SE + 确定性/守卫。
**诚实边界**：默认 `(a=76,N=1021)` 只是**一个不错的小 Korobov 规则、非认证最优**（a=306 时增益从 ~25× 掉到 ~11×，暴露 z 选择敏感），
无 CBC 构造；"标准误"是**随机移位的 MC 标准误、非确定性最坏界**（真 QMC 界需 variation×discrepancy，未算）——criterion 的"error bounds"
按**报告标准误**交付并如实命名；不做 Genz 变量重排序（两法都未排）；高维/近奇异 R 下点阵优势收窄（SE 仍有效、只是不再声称提速）。

### 22.6 周期感知 fibre 连续性（sin²Δθ）+ laminate [A,B,D]（Wave FFFF，D087）

D079 的 fibre 连续性用 `(θ_e−θ_f)²`，但 fibre 角是 **π 周期**（θ 和 θ+π 是同一纤维朝向）。平方度量错把 +89°/−89°
缝当 178° 跳变罚，而那俩 ply 朝向只差 2°。`sin²(Δθ)` 周期 π、在 Δθ=0 **和** π 都为零，正确测真实朝向失配。

```python
from structure_optimizer.core.orthotropic_simp import period_aware_continuity, laminate_abd, simultaneous_elastic_orientation_mma

m, grad = period_aware_continuity(angles, pairs)   # mean sin²(θ_e−θ_f)，梯度 mean sin(2Δ)
A, B, D = laminate_abd(d0, angles, thicknesses)    # 经典层合理论：A=ΣQ̄Δz, B=½ΣQ̄Δz², D=⅓ΣQ̄Δz³
r = simultaneous_elastic_orientation_mma(config, mesh, d0, periodic_continuity=True)  # opt-in，默认 False 复现 D079
```

`sin²` 加 π 不变（`sin²(θ_e+π−θ_f)=sin²(θ_e−θ_f)`）、小角时 `sin²(Δ)≈Δ²` 退化为 D079。laminate `z` 从 `−h/2` 到 `+h/2`
居中：单层居中 ply → `A=Q̄·t, B=0, D=Q̄·t³/12`；中面对称 stack → `B=0`；非对称 [0/90] → `B≠0`（拉弯耦合）。

**关键 / 定量锚点**（闭式 + FD）：±89° 缝 sin²<2e-3（≈sin²2°）而平方 >9.0 + 加 π 不变（≤1e-12）+ 小角 sin²/平方→1（≤1e-3）
+ 连续性梯度 vs 中心 FD ≤1e-6 + 单层 ABD 闭式精确 + 对称 stack B=0 / 非对称 [0/90] B≠0、A&D 对称 + driver opt-in 在 ±89° 棋盘
初值上 period-aware 报 <2e-3 而平方报 >1.0 + 守卫。**诚实边界**：`laminate_abd` 是**独立 CLT 计算器、未接进 driver**（不优化铺层
顺序，正交 SIMP 仍是单层面内问题，laminate 只报告不设计——铺层优化 reopened）；`sin²Δθ` 周期 π **但非圆上度量**，在 Δθ=π/2
垂直缝有伪驻点（罚函数无碍、真测地距是 refinement）；**默认 opt-in False 保 D079 不变**（不偷改默认）；B≠0/B=0 阈值是 scale-aware
松散 sanity（精确锚点是单层闭式 + 对称 B=0）。

### 22.7 flip 约束恢复 CDT + 最小角细化（Wave GGGG，D088）

D080 的 `constrained_delaunay_triangulate` 在无约束 Delaunay 穿过边界边时直接**报错** `cdt_constraint_recovery_failed`
（非凸/稀疏边界常见）。本波用 **edge flip 恢复**（Sloan 1993）把缺失边界边翻回来，使这些边界水密三角化、**不报错**，再可选细化。

```python
from structure_optimizer.core.stl_export import constrained_delaunay_flip_recover, recover_constraints_by_flips, refine_min_angle_flips

pts, tris = constrained_delaunay_flip_recover(outer_loop, holes=None, refine=False)  # 不报错地恢复
pts, tris = constrained_delaunay_flip_recover(outer_loop, refine=True)               # + Lawson 最小角细化
```

恢复：对每条缺失约束边 `(a,b)`，列出与 `a–b` 真相交的边，反复翻转**凸**四边形的对角线（非凸延后、翻后仍相交则重入列），
每次凸翻转严格减少相交数 → 有限步恢复。细化：仅对**非约束**边做 Lawson Delaunay 翻转（对面顶点在外接圆内即翻），局部**增大最小角**，
约束边永不翻 → 边界/水密保持。`constrained_delaunay_flip_recover` 仍**验证** boundary edges == 约束（真失败才 raise）。**D080 原函数不动**。

**关键 / 定量锚点**（闭式 + manifold）：11 顶点星形 D080 报错、本波恢复出 n−2 三角且**2-manifold 帽**（每边属 1 或 2 三角 → 水密）
+ **精确铺砌**（三角面积和 == 多边形面积 ≤1e-6、所有约束边在）+ 最小角细化在已知例**严格升** 18.75°→19.38° 且保面积/manifold
+ 星形上细化**永不降** min angle（Lawson 单调）+ 凸多边形**退化**为 D080 同三角集 + 带洞恢复仍水密、铺砌环形面积。
**诚实边界**：恢复在三角 list 上 **O(n²)**、无 half-edge（小网格够用，max_flips 守卫）；细化**只 Lawson 翻转、不插点（非 Ruppert）**——
最大化定点集内最小角、**不能**消除边界采样强加的 sliver，故只声称"改善/不降最小角"、**不保证最小角下界**；只翻凸四边形，退化共线无可翻时
恢复不进展、最终 boundary≠constraints **仍 raise**（best-effort，水密保证从不削弱、宁可响亮失败）；opt-in 新函数、D080 行为不变。

### 22.8 v12 收口（Wave HHHH，D089）

v12 = **设计级 & 自适应**：把 v11 honestly-deferred 的 7 条限制逐条追溯到 ADR reopening criterion 升级（AAAA-GGGG = D082-D088），
HHHH 收口。

```bash
python scripts/test_agent.py --rubric v12 --strict   # 100/100，v4-v11 各 100 无回归，D033 pytest-green
python scripts/v12_demos.py build/v12_demos          # 9 个真实确定性 demo（覆盖 7 个 wave）
python scripts/generate_v12_fingerprints.py          # 5 个 v12 fingerprint（55→60）
```

收口交付：`scripts/v12_demos.py`（9 demo）+ 5 新 fingerprint（design-grade buckling / nested Clayton / Korobov Genz / laminate /
flip-CDT，各带 `test_multiphysics_fingerprints.py` rerun recipe + guard-set）+ `tests/test_property_v12.py`（3 property，51→54）
+ architecture §22 + CI `--rubric v12 --strict` 步 + 本节 + `quality-rubric-v12.md` + `CHECKS_V12`。

**关键 / 定量锚点**：rubric 100/100（`tests/v12_scorecard.json`）+ v4-v11 各 100 无回归 + pytest gate green（D033）+ ≥1095 测试
（54 property / 60 fingerprint）+ core coverage ≥95%。**诚实边界**：v12 关的是 v11 deferral、**非 production-complete**——D082-D088 各自
"Honest scope notes/Reopening criteria" 仍在（屈曲 ascent 非约束无 mode-tracking、in-loop 赚约束保真非不同设计、spacing 可钻空子、
copula 无 Rosenblatt/sampler、Korobov 随机化 SE 非确定性界、laminate 独立计算器、CDT 只 Lawson 无最小角下界）；rubric 是**自著门控非外部 benchmark**
（100 = 实现匹配我写的契约、是回归 + 诚实账本）；5 fingerprint 覆盖 7 wave 中 5 个（快速非 MMA-loop driver），in-loop / 增广 R2 由单测覆盖。

---

## 23. v13 — robust drivers & validated geometry：屈曲约束 + 峰约束驱动 + 多样性指标 + d 维 Gumbel + 重排序点阵 + 铺层优化 + Ruppert 细化

v13 把 v12 honestly-deferred 的限制逐条追溯到 ADR reopening criterion 升级（AAAAA-HHHHH = D090-D097）。

### 23.1 屈曲约束 MMA：λ_crit ≥ λ_safety（Wave AAAAA，D090）

D082 给了设计级屈曲灵敏度但只当 **ascent 目标**（maximize_buckling_load）。生产用例不是"最大化 λ"，而是"**又刚又不屈曲**"——
min compliance s.t. λ_crit ≥ λ_safety。本波交付这个屈曲**约束**驱动。

```python
from structure_optimizer.core.buckling import buckling_constrained_mma

r = buckling_constrained_mma(config, mesh, lambda_safety=21.5, vf=vf, max_iter=40)
# r.lambda_history / compliance_history / volume_history / lambda_safety / converged
```

两条不等式（D066 结构）：`g₁=1−λ_crit/λ_safety≤0`（屈曲）+ `g₂=mean−vf≤0`（体积），目标 SIMP 静柔度，屈曲约束梯度用
**设计级** `−dλ/dρ/λ_safety`（analysis-grade 指错方向，见 D082）。λ_safety 低于 buckling-free 最优的 λ_crit 时约束失活退化为纯
compliance-min；高于时绑定、用柔度换抗屈曲。

**关键 / 定量锚点**（buckling-free baseline = 同 driver 约束失活，一致参考）：λ_safety=1.5×λ_free 时 λ_crit≥0.95×λ_safety 且
>1.3×λ_free、**柔度严格更高**（probe：λ 14.3→21.2，柔度 +6.7%）+ 体积可行 + slack λ_safety(0.5×) 退化为 compliance-min（柔度/λ 内 2%/5%）
+ 确定性 + 守卫。**诚实边界**：单最低模无 mode-tracking（继承 D082，模态切换/重根未处理）；40 iter 近绑定非精确绑定（~99% λ_safety）；
baseline 是同 driver 约束失活的**相对**比较非绝对最优；g_penalty void-mode 用默认（细网格需 D082 续延）。

### 23.2 半功率带宽自适应窗口（Wave BBBBB，D091）

D083 的 in-loop 频带用固定 `band_rel_width`。但共振的尖锐度随阻尼变——固定 5% 窗口只在某一 ζ 附近准。本波按
**半功率带宽** `Δω/ω_n=2ζ=α/ω_n+β·ω_n` 自适应窗口宽度。

```python
from structure_optimizer.core.freq_response import half_power_relative_bandwidth, adaptive_peak_constrained_mma

half_power_relative_bandwidth(omega, alpha=0.0, beta=2e-6)   # = α/ω+β·ω = 2ζ
r = adaptive_peak_constrained_mma(config, mesh, limit, lo, hi, beta=2e-6, bandwidth_adaptive=True)  # 窗口宽随共振尖锐度
```

`bandwidth_adaptive=True` 时每步用 tracked 共振处的半功率带宽设窗口半宽（默认 False 保 D083）。

**关键 / 定量锚点**（闭式 + dense sweep）：half-power 闭式 = α/ω+β·ω = 2ζ（≤1e-15）+ **跨 sharpness 鲁棒**：β∈{5e-7,2e-6,8e-6}
（ζ≈0.009→0.148）自适应 worst-case 误差 < ½ fixed-5% worst-case，最尖共振处自适应 ~11% vs fixed ~62% + driver 可行 + 确定性/守卫。
**诚实边界 + defer**：D083 的另一条 reopening「peak-binding 产生不同设计」在 smoke mesh **不成立、诚实 defer**——probe 证据：min J(ω_op)
（ω_op∈{0.85..1.4}ω₁）下 in-loop 和 fixed 设计**都可行**（true-peak 仅 limit 的 0.01-0.05），且无约束 min J(ω_op) 反而**降低**带内峰
（7e8→6.1e6）非升高——小网格上"降一频响应"靠整体变刚把整条传递函数压下去，目标与峰约束**同向非冲突**；设计虽差 46% 但都可行不构成
"in-loop 赢 fixed 输"。真冲突需细网格反共振 flanking-mode 机制，**不伪造**，reopened。bandwidth_adaptive opt-in 保 D083；半功率宽设
Rayleigh 模型；最尖处 ~11% 残差来自 5 点 p-norm + bisection（denser 可收紧，非本波重点）。

### 23.3 extent 多样性指标 + range-adaptive ρ（Wave CCCCC，D092）

D084 的 `spacing_indicator` 只量**均匀度**：它把"紧簇前沿"和"只有两端点的极端前沿"都报成 S=0（两者 NN 间距都相等）。
均匀≠铺得开。本波补 **extent 指标 Δ = ‖max−min‖₂**（前沿包围盒对角线长，越大铺得越开），并给 augmented R2 加
`normalize_ranges` 让 ρ 不被最大尺度目标吞掉。

```python
from structure_optimizer.core.multi_objective_to import extent_indicator, spacing_indicator, augmented_tchebycheff_r2

extent_indicator(front)                                            # Δ = 包围盒对角线（越大越散）
spacing_indicator(front)                                           # S = NN 间距 std（越小越匀）
augmented_tchebycheff_r2(front, rho=0.05, normalize_ranges=True)   # 按每目标 range 归一 → 尺度不变
```

extent 与 spacing **互补**：判断前沿多样性需要 (spread=extent, uniformity=spacing) 这对指标，单看任一都不够。

**关键 / 定量锚点**（闭式 + 尺度不变）：extent 闭式 [0,4]² 前沿 = √32（≤1e-12）；**互补 headline**：两端点极端前沿 Δ 与密集
铺开前沿**相同**（都 √32），但 spacing 把两者都报 S=0——证明 extent 抓的是 spacing 看不见的"铺开度"；Δ 平移不变 + 单目标
×10 → √(40²+4²)；range-adaptive：某目标 ×1000 时归一 R2 不变（≤1e-9）而固定 R2 涨 >1.5×；range=1 时归一 == 固定（≤1e-12）；
1D/空前沿守卫 + 某目标常数（range 0 → 守卫为 1）不除零。**诚实边界**：extent 是 spread 非 convergence（要配 R2/IGD⁺/HV 看收敛）；
归一用前沿**自身观测 range**（早期采样有偏，非真 ideal/nadir box）；`normalize_ranges` opt-in 保 D084；非 Deb 的 Δ-metric（不声称是）。

### 23.4 d 维交换 Gumbel copula（Wave DDDDD，D093）

D085 的 nested Clayton 抓**下尾**相关；串联系统可靠性更关心**上尾**（同时极端/共同失效），靠 Gumbel。双变量 Gumbel 已有（D069），
但 d 维缺闭式条件 CDF——因为 Gumbel 逆生成元 `ψ(s)=exp(−s^{1/θ})` 的 k 阶导没有一行闭式。本波用**精确递推** `ψ^{(k)}=ψ·g_k`
（`g_{k+1}=g_k′−α s^{α−1} g_k`，α=1/θ）给出，非数值微分。

```python
from structure_optimizer.core.reliability import gumbel_d_copula

cop = gumbel_d_copula(dim=3, theta=2.2)          # θ≥1；Kendall τ = 1−1/θ
cop.cdf([0.3, 0.5, 0.7])                          # C(u) = exp(−(Σ(−ln u_i)^θ)^{1/θ})
cop.conditional_cdf([0.3, 0.5, 0.7])              # 闭式 C_{k|1..k-1} = ψ^{(k-1)}(S_k)/ψ^{(k-1)}(S_{k-1})
uk = cop.conditional_ppf([0.3, 0.5], w=0.73, k=3) # 单调条件的 bisection 逆（Gumbel 无闭式逆）
```

**关键 / 定量锚点**（闭式 + 数值混合偏导）：d=2 CDF/条件 = 双变量 Gumbel（≤1e-12）；**headline** 闭式条件 CDF 对数值混合偏导
比值 d=3 ≤1e-7、d=4 ≤1e-4（解析精确，FD 才是近似）；Kendall τ=1−1/θ 精确（≤1e-14）；conditional_ppf round-trip ≤1e-9 + 单调；
维度/θ 守卫。**诚实边界**：逆是 bisection 非闭式；仅交换（单 θ，非 nested 分簇）；g_k 12dp 合并同幂（小 d 精确，超大 d 项数增长——出 2.5D 范畴不追）；
无 Marshall–Olkin frailty 采样器（采样走 Rosenblatt ppf）；**尚未接入 `system_reliability_series`**（本波只交付 copula 原语，集成是 reopening）。

### 23.5 Genz 变量重排序（Wave EEEEE，D094）

Genz 分离变量估计器的方差严重依赖积分轴的**顺序**：先积"宽松/大质量"轴会把高方差的"紧约束"轴留到最后，放大每样本乘积的离散度。
Genz–Bretz **priority ordering** 把最受约束（期望概率最小）的轴排在最前。

```python
from structure_optimizer.core.reliability import genz_mvn_cdf_reordered, genz_mvn_cdf

# 与 genz_mvn_cdf 同 estimand，但先做有序 Cholesky 重排
p_safe = genz_mvn_cdf_reordered(upper=betas, correlation=R, n_samples=20000, seed=0)
```

**关键 / 定量锚点**（精确 1-D 参考 + 固定 N 误差比）：6 维 equicorr（ρ=0.5）高 N 重排估计对**精确 1-factor 1-D 求积参考** ≤2e-3；
**headline**：故意坏序问题固定 N=400、60 seed 平均 |误差| 重排 < ½ 未排（实测比 ~0.11，即 ~9× 降低）；重排=relabel（高 N 重排与未排同值 ≤3e-3）；
priority order 把 bound 升序（最小质量先）；满相关矩阵高 N 重排≈未排 ≤4e-3；m=1 闭式 + 确定性 + shape/非 SPD 守卫。
**诚实边界**：期望限用截断正态均值（启发式非证明最优）；不改 estimand 只降方差；新增 `genz_mvn_cdf_reordered` 不翻默认（保 D078/D086）；
满相关只能对未排 MC 互验（无闭式）；**未接入 lattice/series**（reopening）。

### 23.6 铺层顺序优化（Wave FFFFF，D095）

D087 的 `laminate_abd` 只**评估**一个铺层；本波加在固定 ply inventory 的**排列**上做优化。

```python
from structure_optimizer.core.orthotropic_simp import optimize_stacking_sequence, orthotropic_plane_stress_matrix

d0 = orthotropic_plane_stress_matrix(e1=140e3, e2=10e3, nu12=0.3, g12=5e3)
# 最大化弯曲 D_11：rearrangement 闭式（最硬的 0° ply 放表面），可证全局最优
r = optimize_stacking_sequence(d0, [0,0,45,90,-45,90], thickness=0.125, objective="max_bending")
# 对称约束保 B=0：ply_angles 是下半 stack，full = half + reversed(half)
rs = optimize_stacking_sequence(d0, [0,45,90], 0.125, objective="max_bending", symmetric=True)
# 最小化耦合 ‖B‖：穷举 distinct 排列（n≤8）
rc = optimize_stacking_sequence(d0, [0,0,90,90], 0.125, objective="min_coupling")
```

`max_bending` 因 `D_11=Σ c_k·Q̄_11(θ_k)` 中 `c_k` 只取决于位置（表面最大），最优解就是 **rearrangement 不等式**：最硬 ply 放最高 c 的表面位——闭式、可证全局。

**关键 / 定量锚点**（rearrangement 全局最优 + 精确对称解耦）：max_bending 闭式 `D_11` = 全排列 brute-force 最大（≤1e-9）；最优把 0° 放两表面、90° 放中面；
symmetric ⟹ ‖B‖<1e-9（精确镜像解耦）；min_coupling = brute min（≤1e-12）且 [0,0,90,90] 达 ‖B‖<1e-9；优化耦合 < 坏序 1e-6 倍；空/厚度/objective/>8 ply 守卫。
**诚实边界**：只优化**排列**非角度**值**；max_bending 仅 `D_11` 单分量（多向/off-axis 要搜索）；min_coupling O(n!) 限 n≤8；**无 balanced (+θ/−θ) 约束**（reopening）；均匀 ply 厚。

### 23.7 Ruppert 质量细化（Wave GGGGG，D096）

D088 的 Lawson flips 只能在**固定顶点集**上重排连接，最小角卡在顶点集允许的上限（4×1 矩形仅采角点 ⟹ ~14°）。Ruppert 通过**插 Steiner 点**突破：

```python
from structure_optimizer.core.stl_export import constrained_delaunay_ruppert

# 在 circumcenter 插点 + 分裂 encroached 边，直到最小角 ≥ min_angle_deg
pts, tris = constrained_delaunay_ruppert(outer_loop, holes=None, min_angle_deg=20.0)
```

算法：(1) **encroached 子段**（直径圆含其他顶点）从中点分裂；否则 (2) 对最差三角形插**circumcenter**——但若 circumcenter 会 encroach 某子段则改为分裂该段（Ruppert 优先规则，水密关键）。角度上界封顶在可证终止的 **20.7°**。

**关键 / 定量锚点**（达成的角度下界 + Lawson-做不到对比）：4×1 矩形 Lawson-only <15°（≈14.04°），Ruppert ≥20°（实测 26.57°）；只 ADD 顶点 + 原角点不变；
水密（边界顶点度全=2）；bound∈{10,15,20} 结果 ≥ bound；6×1 sliver 需更多 Steiner 点；bound>20.7°（或 ≤0）守卫。
**诚实边界**：上界封 20.7°（Ruppert/Shewchuk 终止保证仅到此，不吹 30°）；**无小输入角处理**（acute 角靠 max_steiner 兜底，concentric-shell 是 reopening）；每插一点全局重三角化 O(n²)；质量仅最小角（无尺寸分级）；2D caps only；**未接入 `write_stl_cdt_multi_hole`**（reopening）。

## 24. v14 — integration & production-wiring：把 v13 孤立原语接入生产驱动器

v14 与 v6-v13 不同——不加孤立新能力，而是把 v13 的原语**接入既有生产函数**（D097 记录的未接入项）。**v14 铁律**：每个改既有生产函数的 wave，新参数 opt-in 默认 + 锚点含 **backward-compat 逐位复现**断言（证明集成不回归）。

### 24.1 d-Gumbel copula 接入 system_reliability_series（Wave AAAAAA，D098）

D078 的 `system_reliability_series_exact` 用**高斯**相关矩阵建模模态相依；但结构失效模态常在**上尾**聚集（共同极端），正是 Gumbel copula 擅长、高斯低估的。本波把 d-Gumbel（D093）接入串联系统估计器。

```python
from structure_optimizer.core.reliability import system_reliability_series_copula, gumbel_d_copula

# 串联系统安全 ⟺ 所有模态安全；用 copula 建模联合安全 u_k=Φ(β_k)
# P_f = 1 − C(Φ(β_1),...,Φ(β_m))
betas = [2.0, 2.5, 3.0, 1.8]
p_f = system_reliability_series_copula(betas, gumbel_d_copula(4, theta=3.0))  # 上尾相关
```

**关键 / 定量锚点**（bit-exact 独立复现 + comonotone 极限）：Gumbel θ=1 逐位复现 `1−ΠΦ(β_k)` ≤1e-14（**backward-compat 铁律**）+ 匹配 D078 `series_exact(R=I)` ≤2e-4；θ↑（{1,1.5,3,10}）P_f 单调降（正相依使模态共同失效而非各自失效）；θ→∞ → max_k Φ(−β_k)（最弱模态失效，≤1e-3）；Clayton θ→0 也复现独立 ≤1e-5；dim/空模态守卫。
**诚实边界**：仅交换单 θ（异质相依要 nested/vine）；仅串联（并联是 reopening）；**无 FORM-相关→copula-θ 标定**（θ 是显式建模选择非从极限态几何推断）；高斯 full-R 能力仍只在 D078 路径。

### 24.2 Genz 重排接入 system_reliability_series_exact（Wave BBBBBB，D099）

D078 的精确串联估计器用 plain Genz MC；坏序极限态集方差偏大。本波把 D094 的 Genz–Bretz 重排接入，opt-in 默认保 D078。

```python
from structure_optimizer.core.reliability import system_reliability_series_exact, system_reliability_series_exact_reordered

p_f = system_reliability_series_exact(betas, R, n_samples=20000, reorder=True)  # 方差缩减
p_f = system_reliability_series_exact_reordered(betas, R)                       # 便捷别名
```

**关键 / 定量锚点**（bit-exact backward-compat + 固定 N 方差缩减）：reorder=False 与 `1−genz_mvn_cdf(...)`（D078 路径）**逐位相同**（`==`，**集成铁律**）+ 与默认调用相同；高 N 重排==未排（≤3e-3）==精确 equicorr 参考；**headline** 固定 N=400、60 seed 重排误差 < ½ 未排（实测 ~0.11，≈9×）；便捷别名 == reorder=True；R=I 两路都 1−ΠΦ(β)（≤2e-4）；shape/空模态守卫。
**诚实边界**：重排只改收敛不改 estimand（方差结果非精度）；**lattice 路径仍未重排**（D094 另一目标，reopening）；精确参考仅 equicorr；默认 reorder=False 保严格 backward-compat。

### 24.3 Ruppert 细化接入 write_stl_cdt_multi_hole（Wave CCCCCC，D100）

D080 的多孔 STL cap 用 plain CDT，可能含 sliver（6×6 带 2×2 孔的 cap 有 18.4° 角）。本波把 D096 Ruppert 接入。

```python
from structure_optimizer.core.stl_export import write_stl_cdt_multi_hole, write_stl_ruppert_multi_hole

r = write_stl_cdt_multi_hole(outer, holes, refine=True, min_angle_deg=20.0)  # cap 质量细化
r = write_stl_ruppert_multi_hole(outer, holes)                              # 便捷别名
```

**集成缺陷（v14 铁律抓到）**：refine=True 初版**非水密**——Ruppert 把边界段从中点分裂（Steiner 点落在环上），细化后 cap 有 wall 没有的边界顶点 → T-junction。**修法**：refine=True 时 wall 跟随**细化三角网边界边**（恰属一个三角形的边），外法向取背离内部 apex 的边垂直方向。refine=False 保留原环 wall 循环不变（byte-exact）。

**关键 / 定量锚点**（byte-exact backward-compat + 面积守恒 + 达成最小角）：refine=False 确定性 + `n_triangles=2·cap+2·环边`（D080 公式，**铁律**）；refine 加 Steiner 三角；面积 refine=True==False==32.0（6²−2²，≤1e-9）；**refine=True 水密**（修复后）；writer 用的 cap（constrained_delaunay_ruppert）最小角 ≥20° 而 plain CDT <20°（证明细化必要）；wrapper byte-identical。
**诚实边界**：wall 法向用 apex-away 启发式（凸边界对，病态非凸可能翻一个法向，但水密 edge-manifold 仍保证）；refine=True 改变 n_triangles（键不变）；Ruppert 上界 20.7° + acute 角靠 max_steiner（concentric-shell 是 FFFFFF）；2.5D 挤出非 3D remesh。

### 24.4 balanced laminate 约束 A₁₆=A₂₆=0（Wave DDDDDD，D101）

D095 的铺层优化做了 *symmetric*（B=0，拉-弯解耦）约束，留下 reopening：*balanced*（每个 +θ 配一个 −θ ⟹ A₁₆=A₂₆=0，拉-剪解耦）。本波补上。工程上最常用的解耦层合板是 **symmetric-balanced**（两者都满足）。

```python
import numpy as np
from structure_optimizer.core.orthotropic_simp import (
    make_balanced_laminate, is_balanced_laminate, laminate_abd,
)

# 从一组不同角度（弧度！）造一个 balanced + symmetric 的铺层
stack = make_balanced_laminate(np.deg2rad([30.0, 60.0]), symmetric=True)
# → 每个 +θ 配 −θ（0/±π2 自平衡不重复），再镜像成 symmetric
a, b, d = laminate_abd(D0, stack, thicknesses)
# a[0,2]=A₁₆≈0, a[1,2]=A₂₆≈0（balance），‖b‖≈0（symmetry）

is_balanced_laminate(np.deg2rad([45.0, -45.0]))            # True
is_balanced_laminate(np.deg2rad([45.0, -45.0]), [2.0, 1.0]) # False（厚度加权）
```

**原理**：旋转后的折减刚度 Q̄₁₆/Q̄₂₆ 在 θ 上是**奇函数**，所以 +θ 与 −θ 的贡献逐项抵消 ⟹ A₁₆=A₂₆=0。`is_balanced_laminate` 是几何（仅看角度）判定：按 acute |θ| 累计**带符号厚度**（+θ 加、−θ 减），全部净零才平衡——因此厚度加权，counts 相等但厚度不等不算平衡。

**关键 / 定量锚点**：balanced [+30,−30,+60,−60] 的 A₁₆,A₂₆=0（abs 1e-7）；symmetric-balanced 同时 A₁₆=A₂₆=0 **且** ‖B‖<1e-7；对照 unbalanced [+45,+45] 有 |A₁₆|,|A₂₆|>1e3；detection True/False（±θ 对、0/π2 self-balanced、孤立 +45）；厚度加权（[2,1] 不平衡且 A₁₆≠0）；guards（空板 / 厚度数不符 → SolverError）。
**诚实边界**：是 **construction+verification，不是 optimiser 约束**——`make_balanced_laminate` 造一个、`is_balanced_laminate` 检一个，但**没有**把 balanced 接进 `optimize_stacking_sequence`（D095 不变，reopening）。**角度是弧度**（rotate_plane_stress 约定，函数不转换，degree 入参得到错误耦合）。只零 A₁₆/A₂₆（拉-剪），**不**零 D₁₆/D₂₆（弯-剪）——symmetric-balanced 一般仍有 D₁₆,D₂₆≠0。构造器假设等厚。

### 24.5 离散角集选择（非仅排序）（Wave EEEEEE，D102）

D095 优化的是**排序**（固定 ply 清单怎么叠），留下 reopening：**选择**（用哪些角）。复合材料设计师从离散可制造角集（如 {0,±45,90}）选 plies。本波补上 selection，并把它**接到** D095 排序优化器上。

```python
import numpy as np
from structure_optimizer.core.orthotropic_simp import select_ply_angles

cands = np.deg2rad([0.0, 45.0, 90.0])  # 离散候选角（弧度）
# 选 4 plies 最大化 D_11：每个位置独立选最刚角 θ*=argmax Q̄_11 → 全选 θ*（闭式全局）
res = select_ply_angles(D0, cands, n_plies=4, thickness=0.125, objective="max_bending")
# res.d_matrix[0,0] == (h³/12)·Q̄_11(θ*)；res.sequence 全 = θ*

# 最小化耦合：brute-force multiset，balanced 选择 → ‖B‖=0
res = select_ply_angles(D0, np.deg2rad([-45.0, 45.0]), 4, objective="min_coupling")
# res.objective_value ≈ 0
```

**原理**：D_11=Σ c_k·Q̄_11(θ_k)，所有 c_k>0，每项独立由 θ*=argmax Q̄_11 最大化 ⟹ **全选 θ*** 是可证全局最优，闭式 D_11=(h³/12)·Q̄_11(θ*)，无需搜索。min_coupling 则 brute-force 枚举 size-n multiset，每个交给 `optimize_stacking_sequence`(D095) 排序，取 ‖B‖ 最小——balanced multiset 对称排列达 ‖B‖=0 下界。

**集成（v14 铁律）**：select 把选好的 multiset **交给 D095 排序**，是真正的 selection→ordering 复合。单候选 [θ] 时 select 结果**逐位复现** `optimize_stacking_sequence([θ]*n)`（sequence/A/B/D 全 `array_equal`，objective `==`）——证明复用不改变 D095。

**关键 / 定量锚点**：闭式 D_11=(h³/12)·max Q̄_11（rel 1e-9）；穷举全部 |C|^n 赋值确认无更优（可证全局）；selection 严格优于 ordering 固定混合清单；min_coupling 达 ‖B‖<1e-7 floor；单候选 bit-exact 复现 D095；guards（空集 / 0 plies / 未知目标 / n=7 太大 → SolverError）。
**诚实边界**：只选**角度值**，不优化 ply 数 / 每层厚度。`max_bending` 全局最优是退化的（全选一个角）——这是"自由选角最大化 D_11、无 ply 数或耦合约束"的诚实正确答案，测试穷举确认而非伪装多样性；要非退化解需加 balanced/symmetric/D₁₆ 约束（reopening）。`min_coupling` 是 brute-force（n≤6, |C|≤6）；symmetric=True 时 B 已被对称强制为 0，min_coupling 失去意义。角度弧度。未接入弹性 MMA 循环。

### 24.6 Ruppert concentric-shell 小输入角（Wave FFFFFF，D103）

D096 的 Ruppert 细化只对**无锐输入角**保证终止。当两条输入段在某顶点（apex）以小角度（<~60°）相交，midpoint 分裂会让相邻两段**互相 encroach、无限分裂**——D096 靠 `max_steiner` 兜底，实则非真正终止（一个 30×10 体 + 4.8° 尖刺，plain midpoint 插几十点后**破坏水密**）。本波补上。

```python
from structure_optimizer.core.stl_export import constrained_delaunay_ruppert

spike = [[0,0],[30,0],[30,10],[0,10],[-120,5]]  # 体 + 4.8° 尖刺 apex
# 默认 midpoint：raise ruppert_not_watertight（D096 的缺陷）
# concentric_shells=True：自然终止 + 水密 + 非 apex 区 ≥20°
pts, tris = constrained_delaunay_ruppert(spike, min_angle_deg=20.0, concentric_shells=True)
```

**两个协同机制**（都 gated 在 opt-in `concentric_shells=False` 之后）：(1) **concentric-shell 段分裂**——incident 到小角 apex 的段，按**距 apex 的 2 的幂半径**分裂（`r=2^round(log2(L/2))`，`r/L∈[0.354,0.707]` 恒为有效内点），两侧段分裂点落在同一同心圆 → isosceles → apex 侧角 `90°−θ/2<90°` → 不互相 encroach，ping-pong 停止；(2) **apex-lock 跳过**——`_apex_locked` 识别 apex 处不可消的 wedge 三角（两边都是约束段），其最小角**就是**输入角，skinny 循环跳过它，否则会永远追它的外心。两者合起来使 acute 输入**真正终止**，不靠 `max_steiner` 兜底。

**关键 / 定量锚点**：shells 下 n_steiner 在 max_steiner=300 与 600 相同且 <300（自然收敛非 budget 限）；plain midpoint 同输入 raise not_watertight（D096 缺陷）；shells 输出水密 + 非 apex-locked 三角 min 角 ≥20°（实测 33.7°）；**非 acute 输入（方形）flag byte-exact no-op**（apex 集空 → midpoint 路径，pts `array_equal` + tris/cons/n_steiner 全等）；apex 检测只标 <阈值角（尖刺 {4}，90° 角 ∅）；20.7° 安全 guard 不变。
**诚实边界**：**输入角本身永不被消除**（几何禁止）——apex wedge 三角恒为输入角；交付的是*终止*+*水密*+*能达标处达标*，不是"全部 ≥20°"，所以测试只在**非 apex-locked** 区量角。`shell_angle_deg=60°` 是经典阈值非逐输入调。2 的幂 shell 是趋向 isosceles 的**启发式非任意输入的形式终止证明**——`max_steiner` 兜底保留。**未接入 `write_stl_cdt_multi_hole` 的 refine 路径**（该 writer 仍 concentric_shells=False，byte-identical D100，reopening）。2.5D 挤出非 3D remesh。

### 24.7 peak-binding flanking-mode（Wave GGGGGG，D104，关闭 D091 二度 defer）

D083/D091 两次留下 peak-binding：min J(ω_op) 抬高 flanking 共振、约束 binding、in-loop regrid 改变设计。D091 把 ω_op 放在基频 ω₁ 附近，那里"变刚"会**整体压低**传递函数 → 目标与约束**一致**、约束不 binding，于是诚实 defer。**本波找到缺失要素：把 ω_op 放在两模态间的反共振谷**。

```python
from structure_optimizer.core.freq_response import peak_binding_mma

w_op = 0.5*(w1 + w2)          # 两模态间反共振谷（不是 ω₁ 附近）
flo, fhi = 0.85*w2, 1.15*w2   # flanking band 绕模态 2
r = peak_binding_mma(config, mesh, w_op, flo, fhi, peak_limit, beta=2e-6, regrid=True)
# regrid=False 把 flanking band 冻结在初始位置（stale）作对照
```

**原理**：在反共振谷深化 ω_op 处的反共振（pole–zero interlacing）会**抬高**相邻模态的 flanking 共振——probe 实测 min J(ω_op) 使 flanking band 峰 **+55%（24×10）/+16%（48×20）**，而 D091 在 ω₁ 附近只看到整体下降。driver 用动态目标 J(ω_op)（`dynamic_compliance_sensitivity`）+ flanking 峰约束（p-norm）+ 体积，走 D066/D075 MMA 对；`regrid=True` 每轮用 `adaptive_band_sample` 重定位移动的 flanking 共振。

**关键 / 定量锚点**（对独立 dense sweep）：unconstrained min J(ω_op) 降目标但 flanking 峰升过初始（>init·1.05）；约束设计 flanking 峰 <0.7× unconstrained（实测 4.5×）且 ρ 不同；regrid vs stale 设计差 >5%（实测 27%）+ tracked 共振移 >2%；feasible（真峰 ≤limit·1.15）；确定性 bit-identical；guards。
**诚实边界（关键）**：**约束并非严格 KKT-binding，J 未被牺牲**——0.3/0.5/0.8×init 的 limit 下约束都不 active，约束运行反而到达**更低** J（基非凸目标的 basin 效应）；约束起 **basin/轨迹选择器**作用（把优化器从"抬高 flanking"的路径引开），不是"压 flanking 必牺牲 J"的硬 trade-off。**已交付 vs D091**：(a) 耦合（min J(ω_op) 抬高 flanking）已证 = D091 真正的 blocker；(b) 约束改变设计；(c) in-loop regrid 改变设计。**仍 open**：严格 active 约束 + 可测 J 牺牲（reopening）。tracked drift ~5%（弱于 D075 的 ~100%），故 regrid-vs-stale 的**设计差 27%**是更强证据。smoke 24×10 测（快），48×20 已 probe 确认非细网格 artefact。

### 24.8 v14 收口（Wave HHHHHH，D105）

v14 七个能力 wave（D098-D104）收口：`scripts/v14_demos.py` 七个确定性 demo（每个跑真实生产驱动器）；fingerprints 65→70（series_copula / series_exact_reordered / balanced_laminate / angle_selection / concentric_shell，tolerant + bit-exact 双层）；property 57→60（balanced 零 A₁₆/A₂₆ / angle-selection 支配随机 multiset / Gumbel series θ=1 退化独立）；architecture §24 integration 叙事；CI v14 步从 `continue-on-error` 翻成 `--rubric v14 --strict`。

```bash
python scripts/v14_demos.py build/v14_demos        # 生成 7 个 demo HTML
python scripts/test_agent.py --rubric v14 --strict # 权威评分（~6h，跑 v4-v13 全回归链）
```

**门控（authoritative）**：v14 rubric **100/100**；v4-v13 回归 = False（各 100）；pytest gate green（D033，0 failed）；全红线保持。结果记入 `tests/v14_scorecard.json`。
**诚实边界**：v14 是 integration + robustness 里程碑，**不加新物理能力**（by design）。两条诚实 carrydown 留 open（不掩盖）：D101 balanced 是 construction+verification 未接 optimize_stacking_sequence；D104 peak-binding 证了耦合 + 设计改变但**非严格 KKT-binding**。D100/D103 的 refine 路径**未接 write_stl_cdt_multi_hole 的 refine=True**（concentric shells 只经 constrained_delaunay_ruppert 可达）。`--rubric v14 --strict` 慢（~6h+，回归链增至 v4-v13 共 10 里程碑全量 coverage）——别误杀轮替的 `pytest --cov` 子进程。

---

## 25. v15 — embedded constraints & rigorous closure

> v15 把 v14 standalone/construction 原语**嵌进生产优化器作真约束** + 关闭 v14 诚实 defer。
> **约束真绑定铁律**：每个 embedding wave 证 (a) 约束开启 feasible、(b) 约束**改变**无约束最优、(c) opt-in 默认逐位复现。

### 25.1 balanced 约束嵌入 optimize_stacking_sequence（Wave AAAAAAA，D106）

D101 把 balanced 做成 standalone 检查器（`make_balanced_laminate`/`is_balanced_laminate`），留下 reopening：接进生产排序优化器。本波把 balanced 嵌进 `optimize_stacking_sequence`，输出即 A₁₆=A₂₆=0。

```python
from structure_optimizer.core.orthotropic_simp import optimize_stacking_sequence

# balanced=True：输入角先 +θ/−θ 配对，再按目标排序 ⟹ 输出 A₁₆=A₂₆=0
r = optimize_stacking_sequence(d0, np.deg2rad([30.0, 60.0]), 0.125, objective="max_bending", balanced=True)
# r.a_matrix[0,2]=A₁₆≈0；配 symmetric=True ⟹ 同时 ‖B‖≈0（symmetric-balanced）
```

**原理**：扩展刚度 A=Σ Q̄_k t_k **与顺序无关**、Q̄₁₆/Q̄₂₆ 在 θ 上奇 ⟹ +θ/−θ 配对 multiset 对**任意**排序都 A₁₆=A₂₆=0。所以 balanced=True 把 inventory 换成配对 multiset（`_balanced_stacking_inventory`），目标排序照常跑而平衡恒不破；symmetric=True 再镜像 ⟹ B=0。

**关键 / 定量锚点（约束真绑定）**：(a) feasible — balanced=True ⟹ A₁₆=A₂₆=0（abs 1e-7）；(b) 改变设计 — balanced=False 同输入 |A₁₆|>1e3（raw inventory 不平衡）且序列不同；(c) **byte-exact** — balanced=False 逐位复现 D095 默认路径（sequence/A/B/D array_equal + objective ==）；order-independent（max_bending & min_coupling 都平衡）；guard（配对翻倍 ⟹ min_coupling n≤8 仍触发）。
**诚实边界**：平衡靠**构造非搜索限制**（A 与序无关，无序可限）；balanced=True **改变 ply 数**（非自平衡角翻倍）；只零 A₁₆/A₂₆ 非 D₁₆/D₂₆（弯-剪是 D110 anti-symmetric）；角度弧度；均匀厚。

### 25.2 concentric shells 接入 write_stl_cdt_multi_hole（Wave BBBBBBB，D107）

D103 给三角化加了 concentric-shell（acute 输入角自然终止+水密），但只在 `constrained_delaunay_ruppert` 可达——D100 的 STL writer 用 `concentric_shells=False`，acute 截面导不出（raise not_watertight）。本波把开关接进 writer。

```python
from structure_optimizer.core.stl_export import write_stl_concentric_export, write_stl_cdt_multi_hole

spike = [[0,0],[30,0],[30,10],[0,10],[-120,5]]  # ~4.8° 尖角截面
write_stl_concentric_export(spike, out_path="cap.stl")   # 端到端水密细化导出
# = write_stl_cdt_multi_hole(spike, refine=True, concentric_shells=True)
```

**关键 / 定量锚点（约束真绑定）**：(a) feasible — acute 截面 concentric_export ⟹ 水密 + 面积守恒 900.0；(b) necessary — refine 不带 concentric 同输入 raise not_watertight（开关改变结果）；(c) **byte-exact** — concentric_shells=False+refine 逐字节复现 D100、refine=False 复现 D080；guard concentric-requires-refine；wrapper 等价。
**诚实边界**：继承 D103 限制（输入角本身不可消、shell 是启发式非任意输入形式证明、max_steiner 兜底保留）；wall 法向 apex-away 启发式；多-apex 干涉留 D112；**纯 wiring 非新算法**，价值在端到端 acute 角导出。

---

## 常见错误

| 现象 | 原因 | 解决 |
|---|---|---|
| `pip install -e .` 报 setuptools 警告 | 老版本 pip | `pip install --upgrade pip` 后重试 |
| `structure-optimizer: command not found` | venv 未激活 | `source .venv/bin/activate` |
| `verification status = connectivity_failed` | 载荷区到固定边界没有连通材料路径 | 提高 `volume_fraction` 或减小 `filter_radius` |
| `verification status = volume_constraint_failed` | OC update 没收敛到目标体积分数 | 增大 `max_iterations` 或减小 `change_tolerance` |
| `optimization.gif` 全黑/全白 | 网格太小或 SIMP 完全消除材料 | 检查载荷强度 vs 材料强度比例 |
