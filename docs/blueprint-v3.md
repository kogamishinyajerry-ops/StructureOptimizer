# StructureOptimizer v3 大阶段蓝图

> **签发日期**：2026-05-16
> **签发人**：项目总负责人（用户授权 Claude Opus 4.7 主驱动）
> **基准版本**：v2.0.0-final（97/100，按 `docs/quality-rubric-v2.md` v2.x 标准）
> **目标版本**：v3.0.0（≥95/100，按 `docs/quality-rubric-v3.md` v3.x 新标准）

---

## 一、北极星（North Star）

> **把 v2 留白补齐 + 把性能做到能跑工业问题 + 把可复现做到位**。
>
> v1 做"基础工程化"，v2 做"广度扩展"；v3 做 **深度 + 真实性**。

具体说：

1. **填 v2 留白**：D003 应力约束 SIMP 梯度集成（adjoint method）、D005 SIMP-on-triangle 真实装。
2. **跑真实问题**：500×500 网格能跑通；大网格 incremental sparse assembly；多进程 study 加速。
3. **可复现**：跨 Python 版本 + 跨 OS bit-exact 关键数值；benchmark fingerprint DB。
4. **研究流程**：DOE study runner（拉丁超立方 + Sobol）、设计 lineage tracking。
5. **用户面**：Jupyter rich display、interactive review HTML 升级。

---

## 二、v2.0.0-final 已交付能力（基线）

| 能力 | 状态 |
|---|---|
| 单工况 / 多工况（3 aggregator）SIMP 拓扑优化 | ✅ |
| BESO 算法 + algorithm plug-in 抽象 | ✅ |
| 应力约束（p-norm + KS）verification-time 检查 | ✅ |
| 制造约束：symmetry / extrusion / min_member_size | ✅ |
| 4 个求解器后端（dense / cg / sparse / sparse_cg, 24× speedup） | ✅ |
| 三角网格读入（meshio adapter） + linear elastic solve | ✅ |
| 几何输出（SVG / DXF / STL） | ✅ |
| 8 类失败状态码（含 stress_constraint_failed） | ✅ |
| CI 双路径（vanilla + with-extras） | ✅ YAML 在位 |
| 文档（README / architecture / tutorial / 6 ADRs / physics-reference） | ✅ |
| 264 测试 / core 93.9% / adapters 92.6% | ✅ |

**v2.0 honest caveats（v3 主线攻击点）**：

- ❌ **应力约束未集成 SIMP 梯度**（D003 留白；v3 L 波要补）
- ❌ **SIMP-on-triangle 未做**（D005 留白；v3 M 波要补）
- ❌ **大网格 (500×500+) 未实测**（dense N×N 内存爆；sparse 需 incremental assembly）
- ❌ **study 是 single-process grid search**（v3 O 波要做 DOE + 多进程）
- ❌ **跨平台 bit-exact 未做**（v3 P 波要做）
- ❌ **Jupyter 无 rich display**（v3 Q 波要做）

---

## 三、v3.0 主题

**「Production-grade depth — fill v2 留白 + run real-size problems + reproduce them anywhere」**

三条主线：

### 主线 1 — 算法 / 物理深度（L + M 波）

把 v2 ADR 留白 D003 (应力约束 SIMP 梯度) 和 D005 (SIMP-on-triangle) 补齐。这是从"可用的 demo"到"严肃工程问题求解器"的关键鸿沟。

### 主线 2 — 性能与规模（N + O 波）

500×500 网格 (500K DOFs) 能跑通；incremental sparse assembly 避免每次 SIMP 迭代重建整个 K；多进程 study 加速 ≥3×；DOE study runner 替代 grid search。

### 主线 3 — 可复现 + 用户面（P + Q + R 波）

跨平台 bit-reproducibility 真测试；benchmark fingerprint DB；Jupyter rich display；interactive review HTML 升级；R 波收口。

---

## 四、7 波分解（L → R）

| 波 | 主题 | 版本 | 估计 LOC | 估计测试 |
|---|---|---|---:|---:|
| **L** | Adjoint stress-constrained SIMP | v2.1.0 | 500-800 | 30-40 |
| **M** | SIMP-on-triangle（mesh-agnostic SIMP refactor） | v2.2.0 | 700-1000 | 30-40 |
| **N** | 大网格 + incremental sparse assembly + 多进程 study | v2.3.0 | 400-600 | 25-35 |
| **O** | DOE study runner (LHS + Sobol) + 设计 lineage | v2.4.0 | 500-700 | 25-35 |
| **P** | 跨平台 bit-reproducibility + fingerprint DB | v2.5.0 | 300-500 | 20-30 |
| **Q** | Jupyter rich display + interactive review HTML | v2.6.0 | 400-600 | 15-25 |
| **R** | v3.0 final 收口（tutorial v3 + ADRs + rubric） | v3.0.0 | 200-400 | — |

**总计**：~3000-4600 LOC，~145-205 新测试。v2 → v3 测试数 264 → ~400+。

---

## 五、永久红线（v3 期间不破）

继承 v1 + v2 全部红线，明确加固：

1. **无 CAD / GUI / cloud / full-3D / commercial 求解器**
2. **runtime mandatory deps 仍仅 NumPy**（scipy / meshio / 任何 v3 新 dep 进 optional）
3. **本地可跑** — `pytest -q` 不依赖网络
4. **可复现** — v3 把这条**升级**：不止"同环境内确定"，要"跨 Python 版本 bit-exact 关键数值"
5. **失败仍单行 stderr + 状态码字符串**

红线 v3 新增 / 明确：
- **v2 不允许扩展导致基础回退** —— v3 把这条扩到 "v3 不允许任何 wave 让 v1.x rubric < 100/100 或 v2.x rubric < 95/100"。任何 commit 必须先验证两者都不破。
- **Jupyter 集成是 opt-in display 协议**——不引入 ipykernel / jupyterlab 等 mandatory 依赖；只输出 `_repr_html_` / `_repr_png_`，让 IPython / Jupyter 自动渲染。
- **多进程并行用 stdlib `multiprocessing`** ——不引入 joblib / dask / ray 等 mandatory 依赖（joblib 仅可进 optional `[parallel]`）。

---

## 六、波执行节奏

每波严格走：

1. **设计** — 在波 README 注释或 ADR 里写：要解决什么、不解决什么、接口契约 + 数学推导（L/M 波）
2. **核心实装** — 新增 / 扩展 `core/` 或 `adapters/` 模块
3. **测试同步落地** — 单元测试 + property test + benchmark（如适用）
4. **质量门** — `ruff check`, `ruff format --check`, `mypy`, `pytest -q` 全绿；**v1.x + v2.x rubric 不回退**
5. **文档同步** — CHANGELOG + （如适用）architecture / tutorial / ADR
6. **commit + tag** — atomic commit + SemVer tag

不跳过任何一步。**不为冲分数写假测试。** 不破任何红线。

---

## 七、退出准则（v3.0 final）

`docs/quality-rubric-v3.md` 总分 ≥ 95/100，且：

- 全部 7 波 commit + tag
- 测试 ≥ 400 个
- core 覆盖率 ≥ 92%（v3 新模块同等覆盖）
- v1.x rubric 仍 100/100（不允许回退）
- v2.x rubric 仍 ≥ 95/100（不允许回退）
- 永久红线全程未破（人工 + grep 双重审查）
- tutorial v3 含每个新能力的端到端示例
- rubric 历史表完整记录每波得分增量

---

## 八、不在 v3 范围内

明确**不做**，避免范围蔓延：

- **3D FEM / 3D mesh**：留给 v4+（永久红线之一；如真要破必须先评估）
- **GUI / commercial solver / CAD kernel**：永远不做（永久红线）
- **AI 顾问 / LLM 集成**：永远不做（永久红线 + 红线原则）
- **CalculiX / FEniCS 真适配**：留给 v4+
- **非线性 / 接触 / 疲劳**：留给 v4+
- **Jupyter notebook 文件** 作为 first-class deliverable：保持 .py 脚本 + CLI 主干；Jupyter 只是 display 协议
- **Sphinx / mkdocs / RTD 集成**：保持 .md 文档，不引入文档构建系统

---

## 九、v3.0 final 验收 checklist

- [ ] `pytest -q` 全绿（≥ 400 测试）
- [ ] `ruff check . && ruff format --check .` 0 issues
- [ ] `mypy structure_optimizer/` 0 errors
- [ ] `pytest --cov=structure_optimizer/core` ≥ 92%
- [ ] `pyproject.toml` runtime mandatory deps 仍仅 NumPy
- [ ] CI workflow 跑 vanilla + with-extras + Linux/macOS matrix
- [ ] `docs/blueprint-v3.md` 七波全勾
- [ ] `docs/quality-rubric-v3.md` 总分 ≥ 95
- [ ] `docs/quality-rubric-v2.md` 总分仍 ≥ 95（v2 不回退）
- [ ] `docs/quality-rubric.md` 仍 100/100（v1 不回退）
- [ ] `CHANGELOG.md` 含 v2.1 → v3.0 完整条目
- [ ] git tag v2.1.0 / v2.2.0 / v2.3.0 / v2.4.0 / v2.5.0 / v2.6.0 / v3.0.0 全存在

---

## 附录 A — Adjoint method 备忘（L 波准备）

应力约束 SIMP 优化问题：

$$
\min_\rho \, c(\rho, u) = f^T u
$$

s.t. $K(\rho) u = f$，$V(\rho) \leq V_{\text{target}}$，$\sigma_{PN}(\rho, u) \leq \sigma_{\text{lim}}$。

应力对密度的梯度（adjoint method）：

$$
\frac{d\sigma_{PN}}{d\rho_e} = \frac{\partial \sigma_{PN}}{\partial \rho_e} + \lambda^T \frac{\partial K}{\partial \rho_e} u
$$

其中伴随向量 $\lambda$ 满足：

$$
K \lambda = -\left(\frac{\partial \sigma_{PN}}{\partial u}\right)^T
$$

每个 SIMP 迭代需要 **2 次** linear solve：一次正向 $Ku=f$，一次伴随 $K\lambda=-\partial\sigma_{PN}/\partial u$。
SIMP 主循环里把 $d\sigma_{PN}/d\rho_e$ 与 $\partial c/\partial \rho_e$ 加权进 OC update。

References:
- Bendsøe & Sigmund 2003 §3.5
- Le, Norato, Bruns, Ha & Tortorelli (2010) — stress-based topology optimization

精确公式 + 验证基准在 L 波实装文档里。

---

## 附录 B — DOE sampling 备忘（O 波准备）

### 拉丁超立方采样 (LHS)

给定 $n$ 个采样点，$d$ 个参数维度：

1. 把每个参数区间 $[a_i, b_i]$ 分成 $n$ 个等概率子区间
2. 在每个子区间内均匀采样一个点
3. 对每一维独立随机置换，组合成 $n$ 个 $d$ 维样本

NumPy-only 实装：~30 LOC。

### Sobol 序列

低偏差准随机序列，跨参数空间均匀填充。$2^k$ 个点。

NumPy-only 实装基础版（用方向数 $V_i^{(k)}$ XOR 累加）：~80 LOC。或用 `scipy.stats.qmc.Sobol`（optional `[doe]` extra）。

References:
- McKay, Beckman & Conover (1979) — LHS 原始论文
- Sobol (1967) — Sobol 序列原始论文

---

## 附录 C — v3 → v4 展望（不在 v3 范围）

v3 完成后可考虑：

- v4.0：3D mesh + 3D FEM（先要评估永久红线）
- v4.1：非线性 / 大变形 / 接触
- v4.2：疲劳 / 屈曲 / 多物理耦合
- v4.3：可选 CalculiX / FEniCS 后端

**v3 不预设 v4。** 每项 v4 工作都要先写"红线评估"ADR。

---

**蓝图签发完成。L 波即将开工。**
