# StructureOptimizer

> **本地、可验证、可解释的 2D/2.5D 结构优化候选生成工作台。**
> 不是 CAD 替代品，不是商业 CAE 替代品，不是云服务。提供的是**带 provenance 的优化候选 + 独立验证 + 可直接交工程评审的静态评审包**。
>
> 当前版本：v5.0.0（multi-physics 大阶段收口）。v1-v5 完整版本史见 `CHANGELOG.md`；逐版本架构演进见 `docs/architecture.md` §8/§10/§12/§14。

---

## 一句话定位

工程评审最害怕的不是"结构不漂亮"，而是"我没法复核它怎么来的"。StructureOptimizer 解决的是后者：每一个候选都有完整的配置快照、迭代历史、独立验证、制造性检查、限制声明，工程师评审时能在 5 分钟内信或拒。

## 能力矩阵（v5.0）

| 维度 | 覆盖 | 不覆盖 |
|---|---|---|
| **建模** | 2D 结构化 quad 网格 + 2.5D 厚度模型 + 非结构三角网格读入（v1.9） | CAD 内核 / STEP 布尔 / 全 3D |
| **物理（线弹性）** | 平面应力 / 平面应变 | 非线性接触 / 疲劳 |
| **物理（multi-physics, v5）** | 2D 热传导 Poisson（v3.6）/ 模态 + 频响 无阻尼（v3.7）/ 几何非线性 简化 TL（v3.8）/ 多材料（v3.9）/ 线性化屈曲（v3.3）| 热-结构强耦合求解 / Rayleigh 阻尼 / 全 TL Green 应变 / 各向异性热传导 |
| **优化算法** | SIMP（默认 OC）/ BESO（v1.7）/ MMA（v3.1）/ 多目标 NSGA-II 双目标 Pareto（v5）；plug-in 抽象 | level-set / phase-field / NSGA-III（≥3 目标）|
| **设计域** | frozen_solid / void 选择器（box / circle / element_box） | 任意几何 / CAD topology |
| **多工况** | weighted_sum / average / worst_case robust（v1.5） | 时变 / 谱响应 |
| **应力约束** | p-norm / KS verification-time（v1.6）+ **adjoint 梯度集成进 SIMP**（v2.1, D007）| 经典 penalty 不保证严格 σ ≤ limit |
| **不确定性 / 可靠性（v5）** | Monte Carlo UQ + worst-case (minimax) SIMP，Gaussian（v3.10）| FORM / SORM / importance sampling |
| **制造约束** | 对称 / 单向挤出 / min member size + 三角网格制造投影（v3.2）| overhang（deferred v6+, D001）|
| **求解器后端** | dense / cg（NumPy）/ sparse / sparse_cg（scipy）/ amg（pyamg）/ matrix-free CG（v3.5）| CalculiX / FEniCS（adapter 钩子留好）|
| **规模** | dense ≤ ~200²；sparse / amg / matrix-free 到 1000×1000 = 2M DOF（v3.5）| 分布式 / GPU |
| **网格输入** | 结构 quad（内置）/ 三角 CST + meshio adapter（v1.9）| 任意 3D 网格 |
| **批量 study** | grid / LHS / Sobol 采样（v2.4）+ Pareto 前沿 + lineage 追踪 + 并行 study | DOE 主动学习 / 通用 MDO |
| **几何输出** | SVG / DXF R12 / STL（2.5D 挤出 v2.0 + 2D voxel 边界 v5）| STEP / IGES / 真 3D solid CAD / marching-cubes |
| **梯度工具（v5）** | 纯 NumPy forward-mode AD + central-FD 校验 | reverse-mode / JAX |
| **产物** | 本地静态 HTML + PNG/GIF + CSV + Markdown + Jupyter `_repr_html_`/`_repr_png_`（v2.6）+ 几何文件 | Web UI / 云协同 / PLM |
| **runtime 依赖** | **NumPy（唯一 mandatory）**；optional extras：`[sparse]`=scipy / `[mesh]`=meshio / `[amg]`=scipy+pyamg / `[bayes]`=scipy+scikit-learn | matplotlib / Pillow / pydantic（PNG/GIF 走纯 numpy+zlib，无 matplotlib）|

---

## 快速上手

```bash
# 安装依赖（推荐 venv / uv）
pip install -e .

# 跑全部测试（约 800 个；canonical numpy-only host 全绿，见验收清单的平台说明）
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

**线弹性主线**

| Benchmark | 维度 | 用途 |
|---|---|---|
| `mbb_beam` | 2D | SIMP 标准拓扑优化主线验证 |
| `cantilever` | 2D | 载荷路径与边界条件 |
| `l_bracket` | 2D | 应力集中与几何敏感性 |
| `loaded_hook` | 2D | 非矩形设计域 |
| `simple_bracket` | 2.5D | frozen / void / 多载荷工况 demo（有 `demo` preset） |
| `multi_load_cantilever` | 2D | 多工况 aggregator（weighted / worst_case） |
| `stress_limited_bracket` / `stress_multi_load_bracket` | 2D | 应力约束（p-norm/KS + adjoint）｜应力 + 多工况同时 |
| `large_cantilever` / `xlarge_cantilever` | 2D | sparse / amg / matrix-free 规模标杆（后者 1000×1000 = 2M DOF）|

**Multi-physics（v5）**

| Benchmark | 物理 | 用途 |
|---|---|---|
| `heat_sink` | 热传导 | 2D Poisson 热 SIMP + 1D-rod 解析校验（D025）|
| `vibrating_beam` | 模态 / 频响 | 广义本征值 + 谐响应（D026）|
| `nonlinear_cantilever` | 几何非线性 | 简化 TL Newton-Raphson + Gere 趋势校验（D027）|
| `bimaterial_beam` | 多材料 | Sigmund-Tortorelli 多材料 SIMP（D028）|
| `uncertain_load_bracket` | 随机 / 可靠性 | Monte Carlo UQ + worst-case SIMP（D029）|

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

## v5.0 验收清单

干净 checkout 下，下面这些应当成立（约 800 个测试）：

```bash
python -m pytest                                    # 799 passed, 4 skipped (slow perf, 加 --run-slow 启用)
python scripts/test_agent.py --rubric v5            # TOTAL 100/100, release ready
python scripts/test_agent.py --rubric v4            # 100/100, 无 v4 回归
python -m structure_optimizer run    --benchmark mbb_beam       --preset smoke
python -m structure_optimizer verify --run runs/mbb_beam/<latest>
python -m structure_optimizer report --run runs/mbb_beam/<latest>
python -m structure_optimizer demo   --benchmark simple_bracket --preset demo
python -m structure_optimizer study  --config studies/simple_bracket_tradeoff.json
PYTHONPATH=. python scripts/benchmark_performance.py
```

> **fingerprint 校验机制（参 D011）**：fingerprint 测试分两层 —— 默认对人类可读值做 `rtol=atol=1e-9` 容差比对（跨 BLAS/LAPACK 后端稳健）；设 `REQUIRE_BIT_EXACT_FINGERPRINT=1` 时（canonical 单一 OS/Python CI cell）才严格比对 SHA-256。quad-SIMP fingerprint 在 `test_fingerprints.py`，三角网格在 `test_triangle_fingerprints.py`，v5 multi-physics（modal/thermal/nonlinear/stochastic）在 `test_multiphysics_fingerprints.py`（各按对应 solver 重跑）。
>
> ⚠️ **诚实提示**：`test_agent.py` 用 collect-count + coverage 给 rubric 打分，**不以 `pytest` 全绿为 gate**——所以"rubric 100/100"与"pytest 是否全绿"是两个独立信号，应分别核对。

实测性能基线见 `docs/performance.md`。

---

## 已知限制

工程上**重要**：必须在评审前主动告知。完整 v5 限制清单见 `docs/architecture.md` §15，各项的 "Reopening criteria" 见对应 ADR。

1. **维度** — 仅 2D 平面应力 / 2.5D 厚度模型（永久红线，跨版本不变）。`simple_bracket` 的 3D 字段是数据预留，未做 3D 求解。
2. **物理（线弹性主线）** — 小变形线弹性；单元中心近似 von Mises 应力，**不能**替代认证级 FEA。
3. **物理（multi-physics，v5，均为有意简化版）** — 热传导仅 scalar conductivity（无各向异性）；模态 dense `eigh` ~2000 DOF 上限；频响 undamped only（无 Rayleigh 阻尼）；几何非线性是简化 TL（qualitative Gere，非 bit-exact）；多材料共享 Poisson 比；随机仅 Gaussian Monte Carlo（无 FORM/SORM）。**无热-结构强耦合求解**。
4. **网格** — 结构化 quad + 三角 CST 读入；dense 路径适合 ≤ ~200²，更大需 `sparse`/`amg`/matrix-free 后端（标杆到 1000×1000 = 2M DOF）。
5. **几何选择器** — `box` / `circle`，无任意几何 / CAD topology。
6. **制造约束** — symmetry / extrusion / min_member_size + 三角网格制造投影已支持；overhang deferred 到 v6+（`docs/decisions/D001`：2D 下定义模糊，需先有 3D FEM）。
7. **study runner** — grid / LHS / Sobol 采样 + lineage + 并行已支持；无 DOE 主动学习 / 自适应采样。
8. **求解器** — dense / NumPy-CG / scipy sparse / sparse_cg / pyamg AMG / matrix-free CG **均已实装**（scipy/pyamg 为 optional extra）；CalculiX / FEniCS adapter **钩子留好但未实装**。
9. **几何输出** — STL 是 2.5D 挤出 + 2D voxel 边界；无 marching-cubes 平滑、无真 3D solid CAD。
10. **可复现性** — fingerprint bit-exact 仅 canonical numpy-only CI host 严格保证；跨 BLAS/LAPACK 后端容许浮点差异（D011），部分 v5 数值敏感 benchmark 在 Apple Silicon 等平台会超容差。
11. **结果定位** — **优化候选 ≠ 投产零件**。所有产物均标记 "engineering review required"。

完整设计边界 + 永久红线见 `docs/architecture.md` §5 / §7.x / §14.7。

---

## 项目结构

```
StructureOptimizer/
├── README.md                   # 本文件
├── CHANGELOG.md                # v0.1 → v5.0 完整版本历史（按真实开发时序）
├── pyproject.toml              # runtime 仅 numpy；optional extras: sparse/mesh/amg/bayes/dev
├── docs/
│   ├── PRD-v0.1.md / MVP-technical-plan.md / open-source-alignment-roadmap.md
│   ├── architecture.md         # 模块边界 + 数据流 + 扩展点 + 永久红线（§8/§10/§12/§14 = v2/v3/v4/v5）
│   ├── physics-reference.md / tutorial.md / performance.md
│   ├── blueprint-v{2..5}.md    # 各大阶段蓝图
│   ├── quality-rubric{,-v2..v5}.md  # 各阶段 100 分制评分表
│   └── decisions/              # ADR D001-D032（含每项 "Reopening criteria"）
├── structure_optimizer/
│   ├── cli.py                  # argparse 入口（run/verify/report/demo/study/export）
│   ├── benchmarks/             # 15 个 benchmark JSON + registry
│   ├── core/                   # 主线: config/mesh/fem2d/simp/verification/reporting/workflow/run_store/demo/study
│   │                           #   v2: beso/triangle*/geometry_export/stress/manufacturing/objectives/filtering
│   │                           #   v3: adjoint/mma/augmented_lagrangian/matrix_free_cg/sampling/lineage/bayesian_opt/refinement/compare/repr_html
│   │                           #   v5: thermal*/modal/freq_response/nonlinear_*/multi_material/stochastic/reliability/pareto_nsga/stl_export/autodiff
│   ├── adapters/               # algorithm_base (SIMP/BESO) / solver_base (dense/cg/sparse/sparse_cg/amg) / mesh_source (meshio) / optimizer_base·file_export (stub)
│   └── visualization/          # density_plot / convergence_plot / gif / png（纯 numpy+zlib，无 matplotlib）
├── tests/                      # ~800 个 pytest + fingerprints/（≥25 bit-exact 指纹）+ v4/v5_scorecard.json
├── studies/                    # 参考 study 配置
├── scripts/
│   ├── test_agent.py             # rubric 机械验证器（--rubric v4|v5），写 scorecard
│   ├── run_mutation_test.py      # 4-mutator 突变测试（≥75% kill）
│   ├── drift_check.py            # 跨版本 benchmark 输出漂移检测
│   ├── generate_fingerprints.py / generate_triangle_fingerprints.py
│   └── benchmark_performance.py  # 性能基线生成
└── runs/                       # 本地运行产物（gitignored）
```

---

## 文档导航

- `docs/architecture.md` — 数据流、模块边界、扩展点、永久红线（§8/§10/§12/§14 = v2/v3/v4/v5 抽象）
- `docs/tutorial.md` — 端到端教程（含各 wave 子节）
- `docs/physics-reference.md` — FEM / SIMP / 多工况 / 应力聚合 数学参考
- `docs/blueprint-v{2..5}.md` — 各大阶段蓝图（"我们打算做什么"）
- `docs/quality-rubric-v{2..5}.md` — 各阶段 100 分制评分表（"如何判定"）
- `docs/decisions/D001-D032` — 逐 wave 工程决策记录（ADR），每项含 "Reopening criteria"
- `docs/PRD-v0.1.md` / `docs/MVP-technical-plan.md` / `docs/open-source-alignment-roadmap.md` — 产品定义 / 算法主线 / 生态对标
- `docs/performance.md` — 性能基线（脚本生成）
- `CHANGELOG.md` — 完整版本历史（按真实开发时序，含 tag 复用说明）

---

## 版本与许可

- v5.0.0 — multi-physics 大阶段收口（2026-05-16）；v1.0.0 是首个"可冻结"里程碑，v1-v5 演进见 `CHANGELOG.md`
- 许可：未指定（项目内部）
- 引用：请引用本仓库 + commit hash

## 贡献

新增 benchmark 流程：
1. 在 `structure_optimizer/benchmarks/configs/<name>.json` 写完整配置（至少一个载荷 + 一个约束）
2. 在 `structure_optimizer/benchmarks/registry.py` 注册名字
3. 在 `tests/` 加冒烟测试覆盖该 benchmark 小网格 `run → verify`
4. `python -m pytest` 全绿后 commit

不要为单个新 benchmark 引入新依赖。
