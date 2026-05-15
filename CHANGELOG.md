# Changelog

本项目使用 [Keep a Changelog](https://keepachangelog.com/) 风格，版本号遵循 [SemVer](https://semver.org/)。

所有日期为 ISO 8601 (`YYYY-MM-DD`)。

---

## [Unreleased]

### Planned
- v0.8 求解器 adapter 稳固化（dense ⇄ sparse 透明切换，留 CalculiX/FEniCS 钩子）
- v0.6.1 overhang 制造约束（additive manufacturing build direction）— v0.6 暂未支持

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
