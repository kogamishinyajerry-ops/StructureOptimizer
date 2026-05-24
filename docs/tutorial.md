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

---

## 常见错误

| 现象 | 原因 | 解决 |
|---|---|---|
| `pip install -e .` 报 setuptools 警告 | 老版本 pip | `pip install --upgrade pip` 后重试 |
| `structure-optimizer: command not found` | venv 未激活 | `source .venv/bin/activate` |
| `verification status = connectivity_failed` | 载荷区到固定边界没有连通材料路径 | 提高 `volume_fraction` 或减小 `filter_radius` |
| `verification status = volume_constraint_failed` | OC update 没收敛到目标体积分数 | 增大 `max_iterations` 或减小 `change_tolerance` |
| `optimization.gif` 全黑/全白 | 网格太小或 SIMP 完全消除材料 | 检查载荷强度 vs 材料强度比例 |
