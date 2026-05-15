# StructureOptimizer 质量评分体系

本文件定义"优秀水准（95+）"的客观、可测量的判断标准。**所有评分项必须是 binary 或带具体阈值**，避免主观打分。

> 评分原则：**自我贬低优先于自我吹嘘**。一条标准如果模糊到可争辩，就当不满足。

---

## 评分维度（100 分总分）

### 1. 正确性 + 测试（25 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 1.1 | `pytest -q` 全绿 | 命令退出码 0 | 5 |
| 1.2 | `core/` 覆盖率 ≥ 90% | `pytest --cov=structure_optimizer/core` | 5 |
| 1.3 | `adapters/` 覆盖率 ≥ 80% | 同上 | 3 |
| 1.4 | 每个 CLI 命令都有端到端测试（含错误路径） | grep test_cli.py | 5 |
| 1.5 | 关键算法有 property-style 测试（随机输入 → 不变式） | grep `_property_` or `for _ in range` 测试 | 3 |
| 1.6 | 同配置可复现：两次 run 产出 bit-identical 关键数值 | tests/test_reproducibility.py 存在且通过 | 4 |

### 2. 文档（15 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 2.1 | README 含一句话定位 + 能力矩阵 + CLI 完整表 | 文件存在 + 三块内容存在 | 3 |
| 2.2 | `docs/architecture.md` 含数据流 + 模块边界 + 永久红线 | 文件存在 + 三块内容存在 | 3 |
| 2.3 | `docs/tutorial.md` 含一个端到端 walk-through | 文件存在 + 含 ≥5 个命令 + 关键输出解读 | 3 |
| 2.4 | CHANGELOG 完整覆盖 v0.1 → 当前 | 含所有 tagged 版本 | 2 |
| 2.5 | `docs/performance.md` 是自动生成的 + 含 metadata | 文件存在 + 含平台/Python 信息 | 2 |
| 2.6 | 所有 public 函数有 docstring | mypy/ruff D 规则或人工抽查 | 2 |

### 3. 代码质量工具（15 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 3.1 | `ruff check .` 返回 0 issues | 命令退出码 0 | 5 |
| 3.2 | `ruff format --check .` 无 diff | 命令退出码 0 | 2 |
| 3.3 | `mypy structure_optimizer/` 在合理严格度下 0 errors | 命令退出码 0 | 5 |
| 3.4 | `pyproject.toml` 含 ruff + mypy 配置 | grep [tool.ruff] + [tool.mypy] | 3 |

### 4. CI / 可复现（10 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 4.1 | `.github/workflows/*.yml` 存在且 YAML 合法 | yamllint / yq parse | 3 |
| 4.2 | CI 跑 pytest + ruff + mypy 全套 | grep workflow 文件 | 2 |
| 4.3 | `pip install -e .` 在干净 venv 中成功 | 在 tempdir 实测 | 3 |
| 4.4 | `pyproject.toml` version 字段与 git tag 一致 | 比对 | 2 |

### 5. 功能完成度 vs 蓝图（15 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 5.1 | MVP slice 1-7（v0.4）全部交付 | tests + docs 验证 | 3 |
| 5.2 | v0.5 评审包收敛 | review_package.py + 每候选 demo.html | 2 |
| 5.3 | v0.6 制造约束（≥3 类落地） | symmetry + extrusion + min_member_size | 3 |
| 5.4 | v0.7 真 Pareto 前沿 | 非支配排序 + 测试覆盖 | 2 |
| 5.5 | v0.8 求解器抽象（≥2 个 backend 等价） | dense + cg 测试通过 | 2 |
| 5.6 | v0.6.1 overhang 制造约束 | 实装 OR 文档化为 "won't fix" 决策 | 3 |

### 6. UX / CLI / 错误信息（10 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 6.1 | CLI 错误是友好单行，不抛 stack trace | 测试触发各种错误并断言 stderr 格式 | 3 |
| 6.2 | `--version` 标志 | `python -m structure_optimizer --version` 输出版本号 | 2 |
| 6.3 | 每个子命令的 `--help` 含 example | grep 子命令 help 文本 | 2 |
| 6.4 | 错误状态码分类（v0.1 起 8 类）有测试覆盖 | tests 每类至少一个 | 3 |

### 7. 工程卫生（10 分）

| # | 标准 | 测量方式 | 分值 |
|---|---|---|---|
| 7.1 | 原子 commit + tag（每个里程碑独立） | git log 验证 | 2 |
| 7.2 | git history 干净（无 squash 必要） | 人工 | 1 |
| 7.3 | `.gitignore` 完整（无误提 runs / __pycache__ / .DS_Store） | grep | 1 |
| 7.4 | 无明显 dead code（未使用 import / 函数） | ruff F401 / vulture | 2 |
| 7.5 | 永久红线全程未破（无 CAD / GUI / 云 / 全 3D / 商业求解器） | 人工审查 + grep | 2 |
| 7.6 | pyproject.toml runtime deps 仍仅 NumPy | grep dependencies | 2 |

---

## 评级界线

| 总分 | 等级 | 含义 |
|---|---|---|
| ≥ 95 | **优秀** | 可放心交付，无明显短板 |
| 85–94 | 良好 | 大多数维度过关；有 1-2 个明显短板 |
| 70–84 | 合格 | 跑得起来，可演示；上线/外部交付前需补 |
| 50–69 | MVP | 主线通，工程化粗糙 |
| < 50 | 半成品 | 缺核心维度（如无测试、无文档） |

---

## 评分历史

| 版本 | 总分 | 关键短板 | 备注 |
|---|---:|---|---|
| v1.0.0 | 42/100 | 无 lint / 无 type / 无 cov 测量 / 无 CI / 无 tutorial / 无 --version / 无可复现性测试 | 蓝图首次完成 — 自评 "MVP" |
| v1.1.0 (Wave A) | 74/100 | core 覆盖率 88.8% (target ≥90%) / CI 未做 / tutorial 未做 / overhang 未决策 | tooling 基线打通 — ruff/mypy/pytest-cov 全绿，99 测试 |
| v1.2.0 (Wave B) | 82/100 | core 覆盖率仍 88.8% / tutorial 未做 / --version 未做 / overhang 未决策 | CI workflow + fresh-venv install 验证通过 |
| v1.3.0 (Wave C) | 93/100 | 仅剩 1.2 core 覆盖率 88.8% (-5) 和 6.4 错误状态码覆盖不全 (-2) | tutorial / --version / 子命令 examples / overhang 决策文档 / 公共 API docstring 全补 |
| v1.4.0 (Wave D) | 100/100 | — | core 覆盖率 92.5% (≥90%) · adapters 96.6% (≥80%) · 7 类 FAILURE_STATUSES 全有专测 · 134 测试 |

### v1.0.0 → v1.4.0 详细变化

| 维度 | v1.0.0 | v1.1.0 | v1.2.0 | v1.3.0 | v1.4.0 | Δ (累计) |
|---|---:|---:|---:|---:|---:|---:|
| 1. 测试 | 5/25 | 20/25 | 20/25 | 20/25 | 25/25 | +20 |
| 2. 文档 | 11/15 | 11/15 | 11/15 | 15/15 | 15/15 | +4 |
| 3. 代码质量工具 | 0/15 | 15/15 | 15/15 | 15/15 | 15/15 | +15 |
| 4. CI / 可复现 | 2/10 | 2/10 | 10/10 | 10/10 | 10/10 | +8 |
| 5. 功能完成度 | 12/15 | 12/15 | 12/15 | 15/15 | 15/15 | +3 |
| 6. UX / CLI | 3/10 | 4/10 | 4/10 | 8/10 | 10/10 | +7 |
| 7. 工程卫生 | 9/10 | 10/10 | 10/10 | 10/10 | 10/10 | +1 |
| **总分** | **42** | **74** | **82** | **93** | **100** | **+58** |

> v1.3.0 评分明细（与上一版对比的 +11）：
> - 2.3 tutorial.md 落地：+3
> - 2.6 公共 API docstring 全补：+1
> - 5.6 overhang 决策文档化（D001）：+3
> - 6.2 --version flag：+2
> - 6.3 子命令 --help 含 example：+2
> - 6.4 错误状态码测试覆盖更广：+0（已经满分）

> v1.4.0 评分明细（与上一版对比的 +7）：
> - 1.2 core 覆盖率 88.8% → 92.5%（design_space.py 57% → 100%，靠 23 个 selector 边角 case 测试拉满）：+5
> - 6.4 错误状态码全 7 类有专测（volume / connectivity / design_space / solver 全部用 fabricated run dir 触发）：+2

> 诚实自评 caveat：100/100 不代表"完美无缺"，仅代表本文件定义的 binary/threshold 标准全部满足。下列短板**承认存在但不计分**（不在评分维度内）：
> - 仅支持 2D 结构网格，3D 与非结构网格延后到 v2.x
> - 仅 SIMP 一种 topology 算法，无 ESO / level-set / phase-field
> - 制造约束仅 symmetry + extrusion + min_member_size，overhang 已正式延后（D001）
> - 求解器仅 dense / CG 两种 NumPy backend，无稀疏 / Krylov advanced precond
> - 评分历史本身依赖人工核对（CI 不自动评分）

（每次迭代后追加一行）
