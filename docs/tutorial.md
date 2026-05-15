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

## 8. 下一步

- `docs/architecture.md` — 模块边界、永久红线、扩展点
- `docs/quality-rubric.md` — 质量评分体系（如果你想衡量整个项目工程化水平）
- `CHANGELOG.md` — v0.1 → v1.x 完整版本历史
- `README.md` — CLI 完整表 + 已知限制

如果 `verification.json` 出现 `volume_constraint_failed` / `connectivity_failed` 之类的失败状态，先看 `report.md` 的诊断段落。

---

## 常见错误

| 现象 | 原因 | 解决 |
|---|---|---|
| `pip install -e .` 报 setuptools 警告 | 老版本 pip | `pip install --upgrade pip` 后重试 |
| `structure-optimizer: command not found` | venv 未激活 | `source .venv/bin/activate` |
| `verification status = connectivity_failed` | 载荷区到固定边界没有连通材料路径 | 提高 `volume_fraction` 或减小 `filter_radius` |
| `verification status = volume_constraint_failed` | OC update 没收敛到目标体积分数 | 增大 `max_iterations` 或减小 `change_tolerance` |
| `optimization.gif` 全黑/全白 | 网格太小或 SIMP 完全消除材料 | 检查载荷强度 vs 材料强度比例 |
