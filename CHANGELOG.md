# Changelog

本项目使用 [Keep a Changelog](https://keepachangelog.com/) 风格，版本号遵循 [SemVer](https://semver.org/)。

所有日期为 ISO 8601 (`YYYY-MM-DD`)。

---

## [Unreleased]

### Planned (post v1.7, per `docs/blueprint-v2.md`)
- H 波 v1.8：scipy sparse optional backend
- I 波 v1.9：非结构 2D 三角网格 + meshio adapter
- J 波 v2.0：boundary extraction + SVG/DXF/STL 几何输出
- K 波 v2.0-final：tutorial v2 + rubric ≥95 收口

### Decided
- overhang 制造约束已正式 deferred 到 v2.x+；理由见 `docs/decisions/D001-overhang-deferred.md`
- v2.0 大蓝图：`docs/blueprint-v2.md` 已签发；v2.x 评分体系：`docs/quality-rubric-v2.md`
- F 波（应力约束）仅做 verification-time 检查；SIMP 梯度集成（adjoint method）留给未来 ADR
- G 波 algorithm plug-in 抽象：基于 ABC + 注册表（同 solver backend 模式）

---

## [1.7.0] — 2026-05-16

### BESO 算法 + algorithm plug-in 抽象（Wave G）

第三个 v2 增量：第二种 topology 算法 BESO（Bidirectional Evolutionary Structural Optimization）落地，与 SIMP 共存于统一插件接口。CLI 增 `--algorithm` flag 切换。

### Added
- **`adapters/algorithm_base.py`** — 算法 plug-in 抽象（同 `solver_base.py` 模式）
  - `TopologyAlgorithm` ABC：契约方法 `run(config, mesh) -> OptimizationResult`
  - `SimpAlgorithm` / `BesoAlgorithm` — 内置实现
  - `_REGISTRY` 字典 + `available_algorithms()` + `get_algorithm(name)` 工厂
  - 大小写不敏感；默认 `"simp"`；未知 → ValueError
- **`core/beso.py`** — BESO 算法实装
  - 起步全 1.0 密度，逐步演化到 `volume_fraction`
  - 演化率 `er`（默认 0.02）每代缩减目标体积
  - 按敏感度排序 → 阈值 cut → 顶部成 solid，底部成 min_density
  - 完全复用 SIMP 的 `density_filter` / `apply_manufacturing_projections` / `solve_and_aggregate`
  - 输出 `OptimizationResult` 与 SIMP 同 schema → demo/report/study 透明
- **`OptimizationConfig.algorithm: str = "simp"`** + **`beso_er: float = 0.02`**
  - 验证算法名在注册表内；`beso_er` ∈ (0, 1)
- **CLI `--algorithm {simp,beso}` flag** on `structure-optimizer run`
  - 覆盖 config 值；argparse 自动校验枚举
- **`tests/test_beso.py`** — 22 个测试：
  - registry：列两算法、get_algorithm 返回正确类、case-insensitive、未知报错
  - config：默认 simp、默认 er=0.02、accept beso、拒绝 level_set / er>1 / er=0
  - BESO 行为：reach target volume (±5%)、near-binary density (gray <5%)、honor frozen/void mask、completed not max_iter
  - workflow 集成：默认 simp / beso override 路径都跑通
  - CLI: --algorithm beso E2E + --algorithm genetic 被 argparse 拒

### Changed
- `core/workflow.py` —
  - `run_benchmark(..., algorithm=None)` 新增覆盖参数（不破坏现有调用）
  - `run_config` 通过 `get_algorithm(config.optimization.algorithm)` dispatch
  - 移除直接的 `run_simp` 导入
- `core/config.py` — `validate_config` 加 algorithm + beso_er 校验
- `structure_optimizer/cli.py` — `run` 子命令加 `--algorithm` 选项
- `pyproject.toml` version: 1.6.0 → 1.7.0

### Coverage
- 全测试 183 → **205** (+22)
- `adapters/algorithm_base.py`: **100%**
- `core/beso.py`: **96.7%**
- `core/workflow.py`: 97.8% → **98.0%**
- 整体覆盖率：93.0% → **93.2%**

### Engineering principles
- BESO 与 SIMP 共享 80% 工具链（filter / manufacturing / aggregator / FEM）→ 接口稳定不蔓延
- 算法选择驱动从两处可入（config / CLI flag），但内部唯一 dispatcher → 单一真相源
- BESO 数学：Huang & Xie 2010，硬 kill 形式（无 soft-kill 的 `min_density` ramp）；不增加内部超参，仅 `er`
- 不引入 level-set / phase-field / MMA（避免 v2 scope creep；列入未来 hooks 文档）

### v2.x rubric 增量
- 1.5 BESO 算法 + 等价 benchmark: +6
- 1.6 algorithm plug-in 抽象: +3
- 1.7 CLI `--algorithm` flag: +2

总分 18/100 → **29/100**

---

## [1.6.0] — 2026-05-16

### 应力约束（Wave F）

第二个 v2 增量：von Mises 应力 + p-norm / KS 两种 smooth-max aggregation + 新的失败状态码 `stress_constraint_failed`。**verification-time** 检查：检验生成的 density 是否满足应力上限；SIMP 优化循环本身不变（梯度集成留给未来 adjoint-method ADR）。

### Added
- **`core/stress.py`** — 应力聚合模块
  - `element_von_mises_stresses(config, mesh, displacements)` — 每元素 σ_vm
  - `p_norm_stress(stresses, p, mask=None)` — p-norm 平滑最大值，max-shift 防溢出
  - `ks_stress(stresses, p, mask=None)` — Kreisselmeier-Steinhauser 平滑最大值
  - `aggregate_stress(stresses, aggregation, p, mask=None)` — dispatch
- **`StressConstraintConfig`** 新字段在 BenchmarkConfig：
  - `enabled` / `aggregation` (`p_norm` | `ks`) / `p` / `limit` / `density_threshold`
  - 默认 `enabled=False`，零侵入 v1.5 配置
- **新失败状态码 `stress_constraint_failed`** 加入 FAILURE_STATUSES（共 8 类）
- **`stress_limited_bracket` benchmark** — top_edge 固支 + right_mid 载荷 + σ_lim=250 MPa
  - presets: `smoke` (small mesh) / `tight` (limit=50, 演示 violation) / `ks` (KS aggregation)
- **`tests/test_stress.py`** — 31 个测试：
  - p-norm 数学：单调递减 in p、上界 max σ、mask 行为、empty mask、p≤0 报错
  - KS 数学：≥ max σ、p→∞ 收敛、p≤0 报错
  - `aggregate_stress` dispatch + 未知 aggregation 报错
  - `element_von_mises_stresses` 长度 + 与 FEMResult.max_stress 一致
  - config 默认 disabled / 4 个 validation 错误路径
  - verification 集成：disabled 时无 record；enabled+宽限通过；enabled+紧限 stress_constraint_failed；优先级在 volume 后
  - benchmark 加载（smoke + ks preset）
- **`tests/test_failure_statuses.py`** 增 2 测试：
  - `test_stress_constraint_failed_status` 通过 verify_run 触发
  - `test_stress_constraint_failed_via_cli` CLI E2E（断言 no traceback）

### Changed
- `core/verification.py` —
  - FAILURE_STATUSES 加 `stress_constraint_failed`
  - status 优先级：design_space → volume → connectivity → **stress** → passed
  - constraints[] 在 enabled 时多一条 `stress_constraint` record
  - 内部 `_check_stress_constraint` + `_stress_constraint_record` 私有 helpers
- `pyproject.toml` version: 1.5.0 → 1.6.0

### Coverage
- 全测试 152 → **183** (+31)
- `core/stress.py`: **97.6%**
- `core/verification.py`: 94.7% → **95.3%**
- 整体覆盖率：**93.0%**

### Engineering principles
- 应力评估走"重 solve 一次 + 静态计算"，不污染 SIMP 主循环（保持向后兼容）
- p-norm 用 max-shift 归一化，p=64 仍稳定（不溢出 / 不下溢）
- KS 用经典 `(1/p) log Σ exp(p (σ - max σ))` 形式
- mask gate 用 `densities ≥ density_threshold`，避免低密度伪应力主导
- 不引入 adjoint method（避免 v2 scope creep；留给独立 ADR）

### v2.x rubric 增量
- 1.3 应力约束（p-norm + KS）+ 1 benchmark: +6
- 1.4 stress_constraint_failed 状态码有专测: +2
- 2.5 总测试 ≥ 250 进度：134→183 (差 67 仍未到)
- 6.4 全测试 < 60s: 还在 9.6s ✓
- 7.1 红线未破 ✓
- 7.2 仅 NumPy mandatory ✓

总分 10/100 → **18/100**

---

## [1.5.0] — 2026-05-16

### 多工况 robust formulation（Wave E）

把单工况 / weighted_sum 唯一一种 multi-case 行为，扩展成三种 aggregator 可选；多工况 robust topology optimization 正式落地。这是 v2 大阶段的第一个增量。

### Added
- **`core/objectives.py`** — multi-case aggregator 抽象模块
  - `AGGREGATORS` 集合：`{"weighted_sum", "average", "worst_case"}`
  - `CaseResult` dataclass：单 case 的 FEMResult + name + weight
  - `solve_all_cases(...)` — 独立 solve 每个 case，返回 `list[CaseResult]`
  - `aggregate(mode, cases) -> FEMResult` — 三模式合并
  - `solve_and_aggregate(...)` — 组合便利函数
- **`OptimizationConfig.case_aggregator: str = "weighted_sum"`** — 新字段；config 校验拒绝未知字符串
- **`structure_optimizer/benchmarks/configs/multi_load_cantilever.json`** — 3-case 悬臂梁
  - cases: down (fy=-800) / up (fy=+800) / shear (fx=+400)
  - presets: `smoke` (worst_case + small mesh) / `weighted` (weighted_sum) / `average`
- **`tests/test_objectives.py`** — 18 个测试：
  - aggregator 集合 / 默认值 / 配置校验
  - weighted_sum 数学正确性（按 weight 加权）
  - average 数学正确性（忽略 user weight）
  - worst_case 选 argmax + strain_energy 跟随
  - **property test**: 50 随机 case 集下 worst_case ≥ average 不变式
  - max_displacement / max_stress 取 max-over-cases（所有 mode 一致）
  - 空 case list / 未知 aggregator 报错路径
  - 多工况 benchmark E2E 在三种 mode 下都跑通

### Changed
- `core/simp.py` — `_solve_weighted_load_cases` 删除；改调 `objectives.solve_and_aggregate(aggregator)`
- `core/verification.py` — `_solve_load_case_metrics` 改调 `objectives.aggregate`；返回 dict 增加 `aggregator` 字段；`objective.name` 从 `weighted_compliance` 改为 `{aggregator}_compliance`（多 case 时）
- `pyproject.toml` version: 1.4.0 → 1.5.0

### Coverage
- 全测试 134 → **152** (+18)
- `core/objectives.py`: **100%**
- 整体覆盖率仍 **92.7%**

### Engineering principles
- aggregator 模式数学定义在 docstring 里写明（含公式 + 文献引用）
- worst_case "梯度" 用 argmax case 的 strain energy（subgradient，但实务有效；Bendsøe & Sigmund 2003 §1.4）
- 不为多工况引入新依赖：纯 NumPy + 现有 FEM
- 配置默认值保持 `"weighted_sum"`，v1.4 配置零修改即可继续运行

### v2.x rubric 增量
- 1.1 worst_case formulation + 1 benchmark: +5
- 1.2 weighted_sum + average formulation: +3
- 2.4 多工况 property test: +2

总分 0 → **10/100**（v2.x 起步，还有 90 分要爬）。详见 `docs/quality-rubric-v2.md` 评分历史。

---

## [1.4.0] — 2026-05-16

### 覆盖率达标 + 错误状态码全测（Wave D）

把 v1.3 剩下的两块短板（core 覆盖率 88.8% / FAILURE_STATUSES 部分类未直接触发）补齐。自评 **100/100**（按 `docs/quality-rubric.md` 的 binary/threshold 标准）。

### Added
- **`tests/test_design_space_coverage.py`** — 23 个 selector 边角 case 测试：
  - box / rect / element_box 选择器（normalized + absolute 两种坐标模式）
  - circle 选择器（normalized + absolute）
  - 全部命名 string 选择器（left_edge / right_load / top_edge / bottom_edge / *_mid_pad / all）
  - 错误路径：非法 axis range / 反转范围 / 错误坐标模式 / 未知选择器 / 非字符串非字典
  - design_space 集成路径：空区域 / 重名区域 / 全覆盖（无 design）/ 不相交 frozen+void
  - 遗留 `mesh.void_regions` 路径（rect 通过，非 rect 报错）
  - 结果：`core/design_space.py` 覆盖率 57% → **100%**
- **`tests/test_failure_statuses.py`** — 10 个测试，显式触发每一类 `FAILURE_STATUSES`：
  - `volume_constraint_failed`：fabricated density 全 1.0 → fraction 1.0 > target+0.02
  - `connectivity_failed`：全 min_density → 无 load-support 路径
  - `design_space_constraint_failed`：frozen_solid 区域 doctored 为 0.1
  - `solver_failed`：1×1 mesh + 全 4 边固支 → 无自由 DOF
  - `singular_matrix`：通过 solver_adapter 测试覆盖（meta-test 锁定字符串在 set 内）
  - 每个状态都有 CLI 端到端版本（断言 stderr 无 Traceback）

### Coverage
- core 覆盖率：88.8% → **92.5%**（≥90% 阈值达成，rubric 1.2 满分）
- adapters 覆盖率：**96.6%**（≥80% 阈值，rubric 1.3 满分）
- 整体测试数：101 → **134**（+33）

### Changed
- `pyproject.toml` version: 1.3.0 → 1.4.0

### Engineering principles
- 不为冲覆盖率而写"假"测试：每个新增测试都断言一个**真实可观察的属性**（mask 形状、错误状态码字符串、CLI 输出格式）
- 覆盖率漏洞先做 root-cause 分析：`design_space.py` 漏的 43 行都是 selector 解析的错误分支与替代 schema 分支，正好对应文档承诺的接口契约
- 错误状态码用 fabricated run dir（input.json + density.npy）测试，不依赖真跑完一次优化 — 速度快、信号清晰

### Honest score caveat
100/100 仅指本项目 `docs/quality-rubric.md` 定义的 binary/threshold 标准全部满足，**不等于"完美无缺"**。本版本承认但不计分的短板：仅 2D / 仅 SIMP / 仅 dense+CG / overhang 已正式延后（D001）。具体见 rubric 文件评分历史小节。

---

## [1.3.0] — 2026-05-16

### UX + 文档收口（Wave C）

把 v1.2 的工程化基线往用户面 + 决策面收紧。自评 **93/100**。

### Added
- **`structure-optimizer --version`**：从 importlib.metadata 读取，console script + `python -m` 两种入口都支持
- **每个子命令含 example epilog**：`structure-optimizer run --help` 等都带具体调用样例
- **`docs/tutorial.md`** — 15 分钟新工程师入门：安装 → 跑 benchmark → 读产物 → demo → study + Pareto → 加制造约束 → 切换求解器后端 → 常见错误表
- **`docs/decisions/D001-overhang-deferred.md`** — 正式 ADR 形式 deferral：overhang 在纯 2D 下定义模糊，需先有 3D FEM；明列重启条件
- **公共 API docstring 全补**：所有 `core/` / `adapters/` / `benchmarks/` / `cli.py` 中的公共函数、方法、dataclass 都有简明 docstring（70 个原本缺失，全部补齐）
- **`tests/test_cli.py` 扩展**：`--version` flag 测试 + 子命令 `--help` 含 Example 断言（20 测试）

### Changed
- `pyproject.toml` version: 1.0.0 → 1.3.0（与最新 tag 对齐）
- README "已知限制" §6：overhang 措辞改为正式 deferred 引用 D001
- ruff 配置增 `RUF002 + RUF003` 忽略：项目 docstring 用到 ν / ρ / ≈ / → 等数学/物理符号是有意保留

### Engineering principles
- docstring 不追求长篇大论：一句话说清"做什么"即可，避免过度文档化
- decision records 跟随代码：`docs/decisions/` 目录保留所有需要明确"won't fix"的项

### Test coverage
99 → 101（CLI +2：--version, --help example）

---

## [1.2.0] — 2026-05-16

### CI + reproducible install（Wave B）

将 v1.1 的 dev-tooling 基础接入 CI 工作流；干净 venv 中验证 `pip install -e .` 全链路。自评 **82/100**。

### Added
- **`.github/workflows/test.yml`** — GitHub Actions 工作流，YAML 已本地通过 PyYAML 解析校验
  - `test` job：matrix Python 3.11/3.12/3.13 ×（pytest + ruff check + ruff format check + mypy + coverage 上报）
  - `smoke` job：依赖 test 通过后跑完整 CLI 端到端（run / verify / report / demo / study）
  - pip cache + coverage artifact 上传
- **`pip install -e .` 在干净 venv 中验证通过**：用 `uv venv --seed` 隔离环境，编辑安装 + 控制台脚本 + run/verify smoke 全链路 OK

### Verified
- `structure-optimizer` 控制台脚本在 fresh venv 中可用
- v1.1 的 console_scripts entry 在隔离环境中无 PYTHONPATH 依赖

### Engineering principles
- CI 在三个 Python 版本上跑（3.11 最低支持，3.12/3.13 前向）
- Smoke job 用真实 CLI 命令验证（不是 pytest mock）
- 注意：CI workflow 已声明，需用户 push 到 GitHub 才能实际触发；本地不依赖 `act` 运行器

---

## [1.1.0] — 2026-05-16

### 质量基线建立（Wave A 工程化）

跨过 v1.0 蓝图边界，开始按客观评分体系（`docs/quality-rubric.md`）向"优秀（95+）"迭代。本版自评 **74/100**（v1.0 = 42）。

### Added
- **`docs/quality-rubric.md`**：100 分客观评分体系（7 维度 + 评级界线 + 评分历史表）
- **dev tooling**（`pyproject.toml [project.optional-dependencies].dev`）：ruff / mypy / pytest-cov
- **`tool.ruff` + `tool.mypy` + `tool.coverage` 配置**：项目级 lint / 类型 / 覆盖率规则
- **`[build-system]` + `[project.scripts]`**：声明 setuptools 构建后端 + `structure-optimizer` console script
- **`[tool.setuptools] packages`**：显式声明包列表，消除自动发现 warning
- **新测试 34 个**（65 → 99）：
  - `tests/test_cli.py`（18 测试）：每个 CLI 命令的 happy + 错误路径；CLI stderr 单行无 traceback 不变量
  - `tests/test_reproducibility.py`（6 测试）：bit-identical 输出 / input_hash 稳定 / CG 后端确定性
  - `tests/test_properties.py`（10 测试）：随机种子驱动 SIMP/Pareto/projection 不变式（无 hypothesis 依赖）
- **`structure-optimizer` console script**：`pip install -e .` 后可直接 `structure-optimizer run ...`

### Fixed (property test 抓出)
- `format_metric_value("")` 之前返回空字符串 → HTML 表格会出现空 cell；现统一为 `"n/a"`

### Refactor (mypy 友好)
- `verification.py`：早期返回的 `result` dict 改用 `invalid_result` / `solver_failure` 局部变量避免类型重定义
- ruff 规则：忽略 RUF001（中文全角标点是有意保留）
- mypy override：`structure_optimizer.visualization.*` 排除（bespoke GIF/PNG 编码的 numpy/tuple 类型限制不值得深度重构）

### Coverage (首次测量)
- 总覆盖率 **88.8%**（omit visualization + adapter stubs + __main__）
- core/ 文件群覆盖率分布：filtering 100% / manufacturability 98.5% / mesh 98.8% / simp 98% / fem2d 97.5% / workflow 97.8% / run_store 97.7% / review_package 95.7% / demo 94% / study 89.8% / verification 88.1% / reporting 87.3% / config 84.1% / manufacturing 78.9% / design_space 57%
- adapters/solver_base.py 96.6%
- cli.py 96.4%

### Engineering principles
- 零 runtime 新依赖；ruff/mypy/pytest-cov 全部在 `[dev]` optional
- 中文文档保留全角标点（RUF001 ignored）
- Property tests 不依赖 hypothesis，使用 stdlib `random` + 固定种子保证可复现

---

## [1.0.0] — 2026-05-16

### 首个可冻结里程碑

v1.0.0 是 StructureOptimizer 第一个标记为"可冻结"（freezable）的版本：MVP slice 1-7 + v0.5 评审包 + v0.6 制造约束 + v0.7 Pareto + v0.8 求解器抽象屏障，叠加 README / 文档 / 性能基线。

### Added
- **`scripts/benchmark_performance.py`**：自动生成 `docs/performance.md` 性能基线
  - 跑全部内置 benchmark（smoke preset 优先）
  - 记录 wall time + ΔRSS + 验证状态
  - 加入平台 / Python / 解释器 metadata，便于跨机对照
  - 支持 `--dry-run` / `--preset` 选项
- **`docs/performance.md`**：自动生成的性能基线表格（首版于 macOS arm64 / Python 3.12 / NumPy 2.x）
- **README 全面 polish**：
  - 一句话定位 + 能力矩阵（覆盖 vs 不覆盖）
  - 完整 CLI 参考表
  - Run 目录布局图
  - **v1.0 验收清单**：可复制粘贴的 7 条命令
  - 9 条**已知限制**清单（评审前必告知）
  - 项目结构 + 文档导航
  - 贡献指南（如何加 benchmark）
- **`pyproject.toml`**：version 0.1.0 → 1.0.0，description 升级反映完整能力

### Acceptance (v1.0.0 验收)
所有以下命令成功完成：

```bash
python -m pytest                                                              # 65/65 passed
python -m structure_optimizer run     --benchmark mbb_beam      --preset smoke
python -m structure_optimizer verify  --run runs/mbb_beam/<latest>            # status=passed
python -m structure_optimizer report  --run runs/mbb_beam/<latest>
python -m structure_optimizer demo    --benchmark simple_bracket --preset demo
python -m structure_optimizer study   --config studies/simple_bracket_tradeoff.json
PYTHONPATH=. python scripts/benchmark_performance.py                          # 5 benchmark 全 pass
```

### 累计能力（v0.1 → v1.0）
- **5 个 benchmark**：mbb_beam / cantilever / l_bracket / loaded_hook / simple_bracket
- **5 个 CLI 命令**：run / verify / report / demo / study
- **8 类失败状态**：明确分类便于排错
- **3 类制造约束**：symmetry / extrusion / min_member_size 投影 + 合规性度量
- **2 种求解器后端**：dense / cg（adapter ABC 抽象屏障）
- **真 Pareto 前沿**：非支配排序 + 视觉凸显
- **65 个测试**：覆盖配置校验 / FEM 冒烟 / SIMP / verify / report / demo / study / Pareto / manufacturing constraints / solver adapter / review package

### Engineering principles (v1.0 全程守住)
- 零新框架依赖（仅 NumPy + pytest）
- 本地优先：无云、无 GUI、无服务端
- 配置优先：每个 benchmark 由显式 JSON 驱动
- 验证优先：迭代指标与独立验证指标在所有产物中严格区分
- 适配器边界清晰：solver / optimizer / file_export 三 stub，solver 已实装为示范
- 渐进可逆：每个里程碑独立 commit + tag（v0.4.0 / v0.5.0 / v0.6.0 / v0.7.0 / v0.8.0 / v1.0.0）

---

## [0.8.0] — 2026-05-16

### Added (求解器 adapter 稳固化)
- **`adapters/solver_base.py` 从 Protocol stub 升级为真实抽象**：
  - `LinearSolver` ABC：抽象方法 `solve(matrix, rhs)`
  - `NumpyDenseSolver`（`dense`）：`np.linalg.solve` 直解，保持 v0.1-v0.7 行为完全等价
  - `NumpyCGSolver`（`cg`）：纯 NumPy Jacobi-preconditioned 共轭梯度迭代解
  - `get_linear_solver(backend)` 工厂 + `available_backends()` 注册查询
  - 全模块独立 import，避免循环依赖；`SolverError` 仍在 `core/fem2d.py` 定义
- **`BenchmarkConfig.solver.backend` 字段**：可选，默认 `"dense"`
  - 完整向后兼容：缺失字段 = dense
  - 校验拒绝未注册的 backend 名（启动时报错而非运行时崩溃）
- **`fem2d.solve_linear_elastic` 透明 swap**：内部仅通过 `get_linear_solver` 取实例，不直接 `np.linalg.solve`

### Refactor (内部)
- 把硬编码 `np.linalg.solve` 调用移到 adapter 内部
- `SolverError` 仍在 `core/fem2d.py` 定义，adapters 通过局部 import 引用（避免双向依赖）

### Tests
- 新 `tests/test_solver_adapter.py`：11 个测试
  - 双 backend 在合成 SPD 系统上数值等价（atol 1e-7）
  - 双 backend 在完整 FEM 流水线上工程级等价（相对误差 < 1e-5）
  - CG 在零 rhs / 非 SPD 矩阵 / 不收敛系统上的正确异常
  - 默认 backend 字段 = "dense" 不影响旧配置
  - SIMP 完整循环 + CG backend 跑通

### Engineering principles
- 不引入新依赖：CG 是 100 行 NumPy；scipy sparse 留给 v0.9+ spike
- 抽象屏障检验：`fem2d.py` 不再 import `np.linalg.solve` 直接调用；只通过 `LinearSolver.solve`
- 文档同步：`docs/architecture.md` §4 反映 adapter 实装状态 + 未来扩展方向

### Test coverage
54 → 65（+11 新）

---

## [0.7.0] — 2026-05-16

### Added (Pareto 前沿)
- **非支配排序**（non-dominated sorting）在 study runner 中落地
  - `_assign_pareto_ranks(rows, objectives)`：迭代剥离法，每次找当前剩余集合中非支配元素作为下一层
  - `_dominates`：支持 minimize/maximize 混合方向
  - 已被独立 unit test 完整覆盖（13 个测试，含混合方向 / 数值并列 / 链式支配 / 失败排除）
- **`StudyConfig.objectives` 字段**：默认 `[{mass, minimize}, {compliance, minimize}]`
  - 完整向后兼容：缺失字段 = 默认双目标
  - 校验：拒绝空列表 / 非法 direction（仅接受 `minimize` / `maximize`）/ 缺失 name
- **`candidates.csv` 新增 `pareto_rank` 列**：1 = 前沿；2+ = 被支配；空字符串 = 验证未通过（不参与前沿）
- **`study.html` 视觉凸显前沿**：
  - 新增 "Pareto 前沿" 摘要节，明确写出前沿候选数 + 当前目标定义
  - 表格新增 "Pareto 前沿" 列，前沿候选显示橙色 "前沿" 徽标 + 行底色淡橙
  - Pareto 散点图中前沿候选用橙色填充 + 白色描边
- 验证未通过的候选（`verification_status != passed`）**不**参与前沿计算 — 工程上有意义的设计是：不挑跑挂掉的候选作为前沿"最佳"

### Tests
- 新 `tests/test_pareto.py`：13 个独立测试覆盖支配判断与非支配排序算法
- 扩展 `tests/test_study.py`：CSV 新列断言 + study.html Pareto chip / pareto-front / pareto-summary 断言

### Engineering principles
- 不引入新依赖（纯 Python set 操作 + 简单二重循环；对 ≤ 64 候选无性能问题）
- Pareto 与 `ranking` 字段正交：`ranking` 决定表格排序顺序，`pareto_rank` 是工程评审的独立维度
- 失败候选不参与前沿是**有意为之**：避免推荐评审者关注"看起来低质量但其实根本跑不通"的候选

### Test coverage
41 → 54（+13 新）

---

## [0.6.0] — 2026-05-16

### Added (制造约束粗→实)
- **新模块 `core/manufacturing.py`**：制造约束**预先**投影（区分 `manufacturability.py` 的事后 warning）
  - `apply_symmetry_projection(mesh, densities, symmetry)`：沿 x 或 y 轴线镜像取均值
  - `apply_extrusion_projection(mesh, densities, extrusion)`：沿轴取均值产出轴向均匀场
  - `apply_manufacturing_projections(config, mesh, densities)`：deterministic 顺序应用所有声明的约束
  - `symmetry_residual` / `extrusion_residual` / `min_member_size_compliance` / `evaluate_manufacturing_compliance`：合规性度量
- **`BenchmarkConfig` 扩展**：新增 `manufacturing_constraints` 字段（`SymmetryConstraintConfig` + `ExtrusionConstraintConfig` + `min_member_size: float | None`）
  - 完整向后兼容：缺失字段 = 无约束
- **SIMP 循环 wire-in**：每轮 OC update 之后、design-space mask 之前应用 manufacturing projection
  - frozen_solid / void mask 永远胜过 projection（design intent 是 hard，制造投影是 best-effort）
- **`verification.json` 新增约束记录**：
  - `symmetry_compliance`（residual ≤ 1e-3 为 passed）
  - `extrusion_compliance`（residual ≤ 1e-3 为 passed）
  - `min_member_size_compliance`（按 `2 * filter_radius * cell_size ≥ target` 启发式判断）
  - 未声明的约束**不**写入 constraint 列表（避免噪音）
- **`verification.json` 顶层新增 `manufacturing_compliance` 字段**：完整 projection 报告 + 残差数值
- 完整 schema 校验：拒绝非法 axis（z 等）、负 min_member_size、超 [0,1] 的 symmetry position

### Tests
- 新 `tests/test_manufacturing_constraints.py`：14 个测试
  - symmetry / extrusion projection 单元测试 + SIMP-loop 集成（小网格 5 iter）
  - min_member_size 三态（passed / warning / missing）
  - 4 条 ConfigError 校验路径
  - 正交组合（symmetry-y + extrusion-x）

### Engineering principles
- 不引入新依赖（projection 全 NumPy 单步操作）
- 双模块清晰分工：`manufacturing.py` = 预先约束（影响 SIMP 解），`manufacturability.py` = 事后检查（仅报告）
- overhang 制造约束**故意**推迟到 v0.6.1（2D 下定义模糊，需要更明确的 build direction 语义）

### Test coverage
27 → 41（+14 新）

---

## [0.5.0] — 2026-05-16

### Added (评审包收敛)
- **`core/review_package.py`**：单一来源的评审包共享片段
  - 中文映射：`zh_status` / `zh_check_name` / `zh_stop_reason`
  - 状态徽章：`status_class` + `status_badge_html`
  - 数值格式化：`format_metric_value`、`percent_reduction`
  - 限制声明工厂：`limitation_disclaimer_html(tone)`
    - `evaluator` tone（demo.html）：软调，无 "2D/2.5D benchmark model" 工程术语
    - `engineering` tone（study.html）：显式 `optimization candidate` / `2D/2.5D benchmark model` / 高保真校核要求
  - 双 tone 分裂是**有意保留**的契约：测试两端互锁（`test_demo.py` 否定 / `test_study.py` 肯定）
- **`study.html` 每候选详情页链接**：`candidate_xxx/demo.html` 一键跳转
  - 表格新增"详情页"列
  - study runner 在每个 candidate `verify+report` 完成后自动生成 `demo.html`
- **demo.html 新增"结果适用范围"声明节**（evaluator tone）
- 测试：
  - `tests/test_review_package.py`：共享模块单元测试（zh 映射 / 徽章 / 双 tone 措辞）
  - 扩展 `tests/test_study.py`：断言每候选目录含 `demo.html`，study.html 含 "详情页"、"查看详情"、"candidate_001/demo.html"

### Changed
- `study.py` 候选表的"验证状态"列从英文 raw status 改为中文 `zh_status` 输出（CSS 类保持英文）
- 删除 study.py 内 `_format_number`（被 `format_metric_value` 取代）
- 删除 demo.py 内 `_fmt` / `_zh_status` / `_zh_stop_reason` / `_zh_check_name` / `_status_class` / `_percent_reduction` 私有副本（被 `review_package` 取代）

### Engineering principles
- 共享模块零新依赖（仅 `html.escape`）
- 双 tone 不强制统一：单页评审与多候选评审受众不同
- 测试覆盖 17 → 27（+12 新 test）

---

## [0.4.0] — 2026-05-15

### Added
- **本地参数 study runner**：`python -m structure_optimizer study --config <path>` 命令行入口
- `studies/simple_bracket_tradeoff.json` 作为参考 study 配置
- 支持的 study 参数：`volume_fraction`、`filter_radius`、`load_weights.<load_case_name>`
- 候选排序（默认 `verification_status → mass → compliance → max_displacement`）
- `runs/studies/<study_id>/` 输出目录布局：
  - `study_input.json`：解析后的 study 配置快照
  - `candidates.csv`：排名后的所有候选指标与参数
  - `study.html`：候选对比静态页（Pareto 风格散点 + 排名表 + 限制说明）
  - `candidate_NNN/`：每个候选完整的 run 产物（input.json / metrics.csv / density.png / verification.json / report.md）
- `max_candidates` 上限保护（默认 64），避免参数矩阵爆炸
- `tests/test_study.py`：study 命令冒烟测试 + 空参数值拒绝测试

### Engineering principles
- 本地静态 HTML 产物，不引入 OpenMDAO/Dakota 依赖
- 仅做参数 grid search，不承担通用优化驱动职责

---

## [0.3.0] — 2026-05-12

### Added
- **`design_space` 工程约束对象**：在结构化网格上声明工程语义
  - `frozen_solid` 区域：优化过程中保持 `density = 1.0`
  - `void` 区域：优化过程中保持 `density = min_density`，质量统计按空区处理
  - 矩形（`box`）与圆形（`circle`）`RegionSelector`
  - 重叠 frozen / void 区域显式拒绝
- **多载荷工况（`load_cases`）**：每个 case 带 `weight`，目标改为权重归一化后的 weighted compliance
- **统一 `verification.json` schema**：
  - `objective`：当前优化目标（`compliance` 或 `weighted_compliance`）
  - `responses`：质量 / 柔度 / 最大位移 / 近似最大应力
  - `constraints`：每条 `{name, value, limit, unit, source, status}`
  - `load_cases`：多工况 baseline / candidate 独立验证指标
- 报告输出分层：Objective / Responses / Constraints / Independent verification / Manufacturability warnings
- `simple_bracket` 加入 `demo` preset，演示 frozen / void / 多载荷工况
- `tests/test_design_space.py`：mask 一致性 + 重叠拒绝 + 多载荷工况冒烟

### Engineering principles
- 不引入 CAD、外部网格器、外部求解器或 GUI
- 现有 `run` / `verify` / `report` / `demo` CLI 保持向后兼容
- 缺少 `load_cases` 时旧的 `loads` 配置自动视为 `primary` 工况

---

## [0.2.0] — 2026-05-12

### Added
- **`demo` 命令**：`python -m structure_optimizer demo --benchmark <name> --preset <preset>`
- `demo.html` 单次运行的静态工程评审页（中文 + popover 指标解释 + 收敛动画 + 制造性表格）
- **粗制造性检查（`manufacturability.json`）**：
  - `isolated_islands`：孤立材料岛
  - `thin_member_warning`：薄构件风险
  - `local_density_warning`：灰度密度区域
- `tests/test_demo.py`：demo 命令产物与 manufacturability schema 测试

### Engineering principles
- 粗检查作为 warning 输出，不阻断流程，不作为投产判断依据
- 静态 HTML 直接从磁盘打开，不依赖 web server

---

## [0.1.0] — 2026-05-12

### Added
- **MVP 核心闭环**：`benchmark config → mesh/model → baseline FEA → SIMP optimization → independent verification → report`
- 5 个内置 benchmark：
  - `mbb_beam`（2D 标准拓扑优化主线）
  - `cantilever`（2D 载荷路径与边界条件）
  - `l_bracket`（2D 应力集中与几何敏感性）
  - `loaded_hook`（2D 非矩形设计域）
  - `simple_bracket`（2.5D 厚度模型，3D 扩展接口预留）
- CLI 入口：
  - `python -m structure_optimizer run --benchmark <name> [--preset smoke]`
  - `python -m structure_optimizer verify --run <path>`
  - `python -m structure_optimizer report --run <path>`
- `BenchmarkConfig` loader 与校验器（dataclass + 手写校验）
- 结构化 quadrilateral mesh + 线弹性 2D FEM（NumPy dense）
- SIMP 主循环：密度初始化 / 刚度插值 / 灵敏度计算 / 密度过滤 / OC update
- 默认 SIMP 参数：`volume_fraction=0.4`、`penalty=3.0`、`filter_radius=1.5`、`max_iterations=120`、`change_tolerance=0.01`、`min_density=0.001`
- 独立验证流程：连通性检查 / volume fraction 余量 / frozen-void mask 校验 / FEA 重算
- 失败状态分类：`invalid_config` / `solver_failed` / `singular_matrix` / `volume_constraint_failed` / `connectivity_failed` / `design_space_constraint_failed` / `report_failed`
- 运行产物（`runs/<benchmark>/<run_id>/`）：
  - `input.json`、`metrics.csv`、`density.npy`、`density.png`
  - `baseline.png`、`loadcase.png`、`convergence.png`、`optimization.gif`
  - `optimization_frames/`：选定的密度演化帧
  - `verification.json`、`report.md`
- 测试：
  - `tests/test_config_validation.py`：配置校验
  - `tests/test_mbb_beam_smoke.py`：网格 / FEM / SIMP 冒烟
  - `tests/test_run_verify_report.py`：完整 run → verify → report 路径

### Engineering principles
- 本地优先：所有功能本地可跑，零云依赖
- 配置优先：每个 benchmark 由显式 JSON 驱动，无硬编码工况
- 验证优先：迭代指标与独立验证指标在报告中明确区分
- 适配器边界清晰（`adapters/solver_base.py`、`adapters/optimizer_base.py`、`adapters/file_export.py`），便于后续替换

---

## 文档参考

- `docs/PRD-v0.1.md`：v0.1 产品定义
- `docs/MVP-technical-plan.md`：v0.1 技术方案与 Slice 1-7
- `docs/open-source-alignment-roadmap.md`：v0.3 / v0.4 / v0.5+ 开源对标路线
- `docs/architecture.md`：模块边界与扩展点（M0 新增）
