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

---

## 常见错误

| 现象 | 原因 | 解决 |
|---|---|---|
| `pip install -e .` 报 setuptools 警告 | 老版本 pip | `pip install --upgrade pip` 后重试 |
| `structure-optimizer: command not found` | venv 未激活 | `source .venv/bin/activate` |
| `verification status = connectivity_failed` | 载荷区到固定边界没有连通材料路径 | 提高 `volume_fraction` 或减小 `filter_radius` |
| `verification status = volume_constraint_failed` | OC update 没收敛到目标体积分数 | 增大 `max_iterations` 或减小 `change_tolerance` |
| `optimization.gif` 全黑/全白 | 网格太小或 SIMP 完全消除材料 | 检查载荷强度 vs 材料强度比例 |
