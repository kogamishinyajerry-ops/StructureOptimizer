# StructureOptimizer

> **本地、可验证、可解释的 2D/2.5D 结构优化候选生成工作台。**
> 不是 CAD 替代品，不是商业 CAE 替代品，不是云服务。提供的是**带 provenance 的优化候选 + 独立验证 + 可直接交工程评审的静态评审包**。
>
> 当前版本：v1.0.0（首个可冻结里程碑）

---

## 一句话定位

工程评审最害怕的不是"结构不漂亮"，而是"我没法复核它怎么来的"。StructureOptimizer 解决的是后者：每一个候选都有完整的配置快照、迭代历史、独立验证、制造性检查、限制声明，工程师评审时能在 5 分钟内信或拒。

## 能力矩阵（v2.0）

| 维度 | 覆盖 | 不覆盖 |
|---|---|---|
| **建模** | 2D 结构化 quad 网格 + 2.5D 厚度模型 + **非结构三角网格读入**（v1.9） | CAD 内核 / STEP 布尔 / 全 3D / 非线性 |
| **物理** | 线弹性平面应力 / 平面应变 | 非线性接触 / 疲劳 / 屈曲 / 多物理 |
| **优化算法** | **SIMP**（默认）/ **BESO**（hard-kill 进化算法，v1.7）；plug-in 抽象 | level-set / MMA / phase-field |
| **设计域** | frozen_solid / void 区域选择器（box / circle / element_box） | 任意几何 / CAD topology 选择 |
| **多工况** | **3 种 aggregator**: weighted_sum / average / **worst_case**（robust，v1.5） | 时变 / 频域 / 谱响应 |
| **应力约束** | **p-norm / KS aggregation**（verification-time，v1.6）+ stress_constraint_failed | SIMP-梯度集成（需 adjoint method，留给未来）|
| **制造约束** | 对称 / 单向挤出 / min member size 验证 | overhang（已 deferred 到 v3+，D001） |
| **求解器后端** | dense / cg（NumPy）/ **sparse / sparse_cg**（scipy optional，**24× 加速**，v1.8）| CalculiX / FEniCS（adapter 钩子留好） |
| **网格输入** | 结构 quad（内置 benchmark）/ **meshio adapter**（v1.9）| 任意 3D 网格 |
| **批量 study** | 参数 grid search + Pareto 前沿 + 候选评审页 | DOE / 主动学习 / 通用 MDO |
| **几何输出** | **SVG / DXF R12 / STL ASCII**（v2.0） | STEP / IGES / 真 3D solid CAD |
| **产物** | 本地静态 HTML + PNG/GIF + CSV + Markdown + 几何文件 | Web UI / 云协同 / PLM |
| **runtime 依赖** | NumPy（mandatory）/ scipy（optional `[sparse]`）/ meshio（optional `[mesh]`）| matplotlib / pydantic / 其他 |

---

## 快速上手

```bash
# 安装依赖（推荐 venv / uv）
pip install -e .

# 跑全部测试（应该全绿，65 个）
python -m pytest

# 跑一个最快的 benchmark smoke
python -m structure_optimizer run --benchmark mbb_beam --preset smoke

# 生成单次评审 demo 页（推荐评审者入口）
python -m structure_optimizer demo --benchmark simple_bracket --preset demo
# 命令打印 runs/simple_bracket/<run_id>/demo.html，直接在浏览器打开

# 跑一个参数 study（Pareto 候选对比）
python -m structure_optimizer study --config studies/simple_bracket_tradeoff.json
# 命令打印 runs/studies/<study_id>/study.html
```

---

## CLI 完整参考

| 命令 | 用途 |
|---|---|
| `run --benchmark <name> [--preset <p>]` | 跑单次优化 → 生成 run 目录 + verification.json + report.md |
| `verify --run <path>` | 对已有 run 目录重新做独立验证（不依赖优化迭代的中间指标） |
| `report --run <path>` | 重新生成 `report.md` |
| `demo --benchmark <name> [--preset <p>]` | run + 生成 `demo.html` 评审页（含限制声明 + 指标解释） |
| `study --config <path>` | 批量参数 grid search + Pareto 前沿 + `study.html` 候选对比页 |

所有命令打印产物路径到 stdout，错误打印到 stderr 并以非零退出。

## 内置 benchmark

| Benchmark | 维度 | 用途 |
|---|---|---|
| `mbb_beam` | 2D | SIMP 标准拓扑优化主线验证 |
| `cantilever` | 2D | 载荷路径与边界条件 |
| `l_bracket` | 2D | 应力集中与几何敏感性 |
| `loaded_hook` | 2D | 非矩形设计域 |
| `simple_bracket` | 2.5D | frozen / void / 多载荷工况 demo（有 `demo` preset） |

## Run 目录布局

每次 `run` / `demo` / study candidate 都生成：

```
runs/<benchmark>/<timestamp>/
├── input.json              # 解析后的完整配置快照（含 input_hash）
├── summary.json            # 顶层运行摘要
├── metrics.csv             # 每轮迭代指标（compliance / volume_fraction / change / mass）
├── density.npy             # 最终密度场（numpy 序列化）
├── density.png             # 最终密度可视化
├── baseline.png            # 原始实心设计域
├── loadcase.png            # 边界 + 载荷可视化
├── convergence.png         # 柔度收敛曲线
├── optimization.gif        # 密度演化动画
├── optimization_frames/    # 选取的密度演化关键帧 PNG
├── verification.json       # 独立验证产物（objective / responses / constraints / manufacturing_compliance）
├── manufacturability.json  # 粗制造性检查（孤立岛 / 薄构件 / 灰度区域）
├── report.md               # 工程报告
└── demo.html               # 静态评审页（demo 命令生成 / study 自动生成）
```

Study 额外生成：

```
runs/studies/<study_id>/
├── study_input.json        # 解析后的 study 配置 + 默认 objectives
├── candidates.csv          # 候选指标 + pareto_rank + parameters_json
├── study.html              # 候选对比页（含 Pareto 前沿凸显）
└── candidate_NNN/          # 每个候选完整 run 产物（同上）
```

---

## v1.0 验收清单

下面这些命令应该**全部成功**（在干净 checkout 下）：

```bash
python -m pytest                                                              # 65/65 passed
python -m structure_optimizer run     --benchmark mbb_beam      --preset smoke
python -m structure_optimizer verify  --run runs/mbb_beam/<latest>
python -m structure_optimizer report  --run runs/mbb_beam/<latest>
python -m structure_optimizer demo    --benchmark simple_bracket --preset demo
python -m structure_optimizer study   --config studies/simple_bracket_tradeoff.json
PYTHONPATH=. python scripts/benchmark_performance.py                          # 5 个 benchmark 全 pass
```

实测性能基线见 `docs/performance.md`。

---

## 已知限制

工程上**重要**：必须在评审前主动告知。

1. **维度** — 仅 2D 平面应力 / 2.5D 厚度模型。`simple_bracket` 的 3D 字段是数据预留，未做 3D 求解。
2. **物理** — 仅线弹性、小变形。无非线性接触、无屈曲、无疲劳、无热-结构耦合。
3. **网格** — 仅结构化 quadrilateral；FEM 装配是 dense NumPy，不适合 ≫ 200×200 网格。
4. **应力指标** — 单元中心近似 von Mises，**不能**替代认证级 FEA。
5. **几何选择器** — `box` / `circle` 二选一，无任意几何 / CAD topology。
6. **制造约束** — symmetry / extrusion / min_member_size 已支持；overhang 正式 deferred 到 v2.x+（见 `docs/decisions/D001-overhang-deferred.md` 的理由：2D 下定义模糊，需先有 3D FEM）。
7. **study runner** — 仅参数 grid search，无 DOE / 主动学习 / 自适应采样。
8. **求解器** — NumPy dense 默认；纯 NumPy CG 备用；scipy sparse / CalculiX / FEniCS adapter **钩子留好但未实装**。
9. **结果定位** — **优化候选 ≠ 投产零件**。所有产物均标记 "engineering review required"。

完整设计边界 + 永久红线见 `docs/architecture.md` §5。

---

## 项目结构

```
StructureOptimizer/
├── README.md                   # 本文件
├── CHANGELOG.md                # v0.1 → v1.0 版本历史
├── pyproject.toml              # 依赖：numpy, pytest
├── docs/
│   ├── PRD-v0.1.md             # 产品定义
│   ├── MVP-technical-plan.md   # MVP 技术方案
│   ├── open-source-alignment-roadmap.md  # v0.3 / v0.4 / v0.5+ 路线
│   ├── architecture.md         # 模块边界 + 数据流 + 扩展点 + 永久红线
│   └── performance.md          # 自动生成的性能基线（脚本可重生成）
├── structure_optimizer/
│   ├── cli.py                  # argparse 入口
│   ├── benchmarks/             # 内置 benchmark JSON + registry
│   ├── core/                   # config / mesh / fem2d / simp / verification / reporting / demo / study / review_package / manufacturing / manufacturability / design_space
│   ├── adapters/               # solver_base (LinearSolver ABC + Dense / CG) / optimizer_base / file_export
│   └── visualization/          # density_plot / convergence_plot / gif / png
├── tests/                      # 65 个 pytest 测试
├── studies/                    # 参考 study 配置
├── scripts/
│   └── benchmark_performance.py  # 性能基线生成
└── runs/                       # 本地运行产物（gitignored）
```

---

## 文档导航

- `docs/architecture.md` — 数据流、模块边界、扩展点、永久红线
- `docs/PRD-v0.1.md` — 产品定义与目标用户
- `docs/MVP-technical-plan.md` — 算法主线与 Slice 划分
- `docs/open-source-alignment-roadmap.md` — 开源生态对标方向
- `docs/performance.md` — 性能基线（脚本生成）
- `CHANGELOG.md` — 完整版本历史

---

## 版本与许可

- v1.0.0 — 首个"可冻结"里程碑（2026-05-16）
- 许可：未指定（项目内部）
- 引用：请引用本仓库 + commit hash

## 贡献

新增 benchmark 流程：
1. 在 `structure_optimizer/benchmarks/configs/<name>.json` 写完整配置（至少一个载荷 + 一个约束）
2. 在 `structure_optimizer/benchmarks/registry.py` 注册名字
3. 在 `tests/` 加冒烟测试覆盖该 benchmark 小网格 `run → verify`
4. `python -m pytest` 全绿后 commit

不要为单个新 benchmark 引入新依赖。
