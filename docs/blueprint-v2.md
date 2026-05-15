# StructureOptimizer v2 大阶段蓝图

> **签发日期**：2026-05-16  
> **签发人**：项目总负责人（用户授权 Claude Opus 4.7 主驱动）  
> **基准版本**：v1.4.0（100/100，按 `docs/quality-rubric.md` v1.x 标准）  
> **目标版本**：v2.0.0（≥95/100，按 `docs/quality-rubric-v2.md` v2.x 新标准）

---

## 一、北极星（North Star）

> **让结构工程师在本地、一杯咖啡的时间内，完成"问题描述 → 候选方案 → 多工况 + 多约束 Pareto → 选定方案 → 几何输出 (SVG/DXF)"完整设计闭环。**
>
> 全程：
> - **本地** — 无云、无 GUI、无商业求解器（永久红线）
> - **可复现** — 同配置两次跑产出 bit-identical 关键数值
> - **可解释** — 每一步有可读 artifact（PNG / HTML / JSON / 文本日志）
> - **可下游** — 输出几何描述给下游 CAD/CAE/制造，不是黑盒

---

## 二、v1.4.0 已交付能力（基线）

| 能力 | 状态 |
|---|---|
| 单工况 SIMP topology optimization (2D 结构网格) | ✅ |
| 制造约束：symmetry / extrusion / min_member_size | ✅ |
| Pareto 评审包（多候选 + 非支配排序） | ✅ |
| 求解器抽象（dense / CG 两种 NumPy backend） | ✅ |
| 独立 verification 报告（6 类失败状态） | ✅ |
| CLI（run / verify / report / demo / study） | ✅ |
| 质量工具（ruff / mypy / pytest-cov 全绿） | ✅ |
| CI workflow（Python 3.11/3.12/3.13 matrix） | ✅ |
| 文档（README / architecture / tutorial / ADR） | ✅ |
| 测试 134 个 / core 92.5% / adapters 96.6% | ✅ |

**承认的短板**（v1.4.0 100/100 的 honest caveat）：
- 仅 2D，无 3D（红线之内，3D 由 v3 才考虑）
- 仅 SIMP 一种算法
- 仅单工况 / 单 compliance 目标
- 求解器仅两种 NumPy backend，大网格慢
- 仅结构网格，无非结构 / 无 meshio 输入
- 无几何输出（用户拿到 density.npy 后还得自己提边界）

---

## 三、v2.0 主题

**「From single-load SIMP to multi-physics, multi-algorithm topology workbench」**

v2 不是 v1 的 inflate，是**广度扩展 + 工程深度**。三条主线：

### 主线 1 — 物理表达力（E + F 波）
单工况单目标 → 多工况 robust + 应力约束。这是从"教学 demo"迈向"真实设计问题"的关键。

### 主线 2 — 算法 + 后端多样性（G + H 波）
SIMP 单算法 + dense/CG NumPy → BESO 共存 + scipy sparse 可选后端。算法 plug-in + 后端 plug-in 都基于 ABC 抽象。

### 主线 3 — 输入 + 输出真实化（I + J 波）
仅生成结构网格 → 读 meshio 任意 2D 三角网格；仅产出 density.npy → 输出 SVG / DXF / STL 给下游。

收口主线（K 波）：tutorial v2 + architecture v2 + rubric 重测。

---

## 四、7 波分解（E → K）

| 波 | 主题 | 版本 | 估计 LOC | 估计测试 |
|---|---|---|---:|---:|
| **E** | 多工况 robust formulation | v1.5.0 | 300-500 | 25-35 |
| **F** | 应力约束（p-norm aggregation） | v1.6.0 | 400-600 | 30-40 |
| **G** | BESO 算法 + algorithm plug-in 抽象 | v1.7.0 | 300-500 | 20-30 |
| **H** | scipy sparse optional backend | v1.8.0 | 200-300 | 15-25 |
| **I** | 非结构 2D 三角网格（meshio adapter） | v1.9.0 | 600-1000 | 40-60 |
| **J** | boundary extraction + SVG/DXF 几何输出 | v2.0.0 | 400-600 | 20-30 |
| **K** | v2.0 final 收口（tutorial + rubric） | v2.0.0-final | 200-400 | — |

**总计**：~2400-3900 LOC，~150-220 测试。v1 → v2 测试数 134 → ~300+。

---

## 五、永久红线（v2 期间不破）

继承 v1 全部红线：

1. **无 CAD/GUI/云/全 3D/商业求解器**
2. **runtime mandatory deps 仍仅 NumPy**（scipy / meshio 进 `[project.optional-dependencies].extra`）
3. **本地可跑** — `pytest -q` 不依赖网络
4. **可复现** — 同配置 bit-identical
5. **失败状态机** — 任何错误 → 单行 stderr + 状态码字符串，无 traceback 泄漏

红线更新：
- v2 新增 **几何输出**（SVG/DXF/STL）**不算"输出 CAD"** —— 这是"几何描述"，下游用户可选择把它当 CAD 起点；我们不调 CAD 内核，不嵌 GUI。
- v2 新增 **scipy 可选依赖**——optional，不是 mandatory；CI 同时跑 NumPy-only 和 with-scipy 两条路径。

---

## 六、波执行节奏

每波严格走：

1. **设计** — 在波 README 注释或 ADR 里写：要解决什么、不解决什么、接口契约
2. **核心实装** — 新增/扩展 `core/` 或 `adapters/` 模块
3. **测试同步落地** — 单元测试 + property test + benchmark（如适用）
4. **质量门** — `ruff check`, `ruff format --check`, `mypy`, `pytest -q` 全绿
5. **文档同步** — CHANGELOG + （如适用）architecture.md / tutorial.md / ADR
6. **commit + tag** — atomic commit + 带 SemVer tag

不跳过任何一步。**不为冲分数写假测试。** 不破红线。

---

## 七、退出准则（v2.0 final）

`docs/quality-rubric-v2.md` 总分 ≥ 95/100，且：

- 全部 7 波 commit + tag
- 测试 ≥ 250 个
- core 覆盖率 ≥ 90%（v2 新模块同等覆盖）
- 永久红线全程未破（人工 + grep 双重审查）
- tutorial v2 含每个新能力的端到端示例
- rubric 历史表完整记录每波得分增量

---

## 八、不在 v2 范围内

明确**不做**，避免范围蔓延：

- **3D FEM / 3D mesh**：留给 v3+（永久红线之一）
- **GUI 工具**：留给永远不做（永久红线之一）
- **AI 顾问**：不破"LLM 离线可跑" 边界
- **CalculiX / FEniCS 真适配**：v3 spike，不在 v2
- **commercial solver wrapper（ANSYS/Abaqus/Nastran）**：永远不做（红线）
- **CAD 内核（Open CASCADE 等）**：永远不做（红线）
- **真 robust topology optimization with stochastic loads**：留给 v3

---

## 九、v2.0 final 验收 checklist

- [ ] `pytest -q` 全绿（≥ 250 测试）
- [ ] `ruff check . && ruff format --check .` 0 issues
- [ ] `mypy structure_optimizer/` 0 errors
- [ ] `pytest --cov=structure_optimizer/core` ≥ 90%
- [ ] `pyproject.toml` runtime deps 仍仅 NumPy
- [ ] `[project.optional-dependencies]` 含 `scipy` / `meshio` 分类
- [ ] CI workflow 跑两条路径（vanilla + with-extras）
- [ ] `docs/blueprint-v2.md` 七波全勾
- [ ] `docs/quality-rubric-v2.md` 总分 ≥ 95
- [ ] `CHANGELOG.md` 含 v1.5 → v2.0 完整条目
- [ ] git tag v1.5.0 / v1.6.0 / v1.7.0 / v1.8.0 / v1.9.0 / v2.0.0 / v2.0.0-final 全存在

---

## 附录 A — 物理 formulation 备忘（E + F 波准备）

### 多工况 compliance（E 波）
给定 K 个 load case $\{f_k\}$，三种 aggregator：
- **worst-case**: $c(\rho) = \max_k f_k^T u_k(\rho)$
- **weighted_sum**: $c(\rho) = \sum_k w_k f_k^T u_k(\rho)$
- **average**: $c(\rho) = \frac{1}{K} \sum_k f_k^T u_k(\rho)$

灵敏度：每个 case 独立 solve → 元素灵敏度叠加（worst-case 取 argmax 那个；weighted/avg 线性叠加）。

### 应力约束（F 波）
- von Mises 应力 $\sigma_{vm,e}$ per element from displacement
- p-norm aggregation: $\sigma_{PN} = (\sum_e \sigma_{vm,e}^p)^{1/p}$，p 通常 8-12
- 约束：$\sigma_{PN} \leq \sigma_{\text{lim}}$
- 灵敏度：链式法则 + adjoint method

公式精确版 + 参考文献在 `docs/physics-reference.md`（K 波创建）。

---

## 附录 B — v2 → v3 展望（不在 v2 范围）

v2 完成后的下一里程碑（仅供未来参考，不承诺）：

- v3.0：3D mesh + 3D FEM
- v3.1：scipy sparse 真稀疏 cholmod / preconditioned Krylov
- v3.2：可选 CalculiX / FEniCS 适配（仍 optional dep）
- v3.3：真实 robust formulation under uncertainty

v3 任何项目都要先开"红线评估" — 是否破"无全 3D" 等约束。**v2 不预设 v3。**

---

**蓝图签发完成。E 波即将开工。**
