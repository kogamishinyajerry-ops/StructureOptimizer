# StructureOptimizer v4.x 蓝图

> 用户授权语：
> "作为总负责人，规划下一个大阶段的蓝图。我授权你全权开发，一直瞄准蓝图执行，要有一套专门的测试 agent，有明确的完成度评分机制（要绝对诚实客观），一直迭代开发下去，直至达到你眼里的优秀水准（99分以上）"

v3.0.0 已发布（99/100，仅 §1.4 BESO-on-triangle 1 分 defer，详 D016）。v4.x 把 v3 的所有 defer 关掉 + 拉开工业级算法深度 + 加专用测试 agent，目标 **≥ 99/100 by v4 rubric**（rubric 本身更严，单纯 carry over v3 分不够）。

---

## 一、北极星（North Star）

> "本地、可验证、可解释的 2D/2.5D 结构优化工作台"（v1 北极星，**不变**）
> v4 维度：从"研究演示"升级到"工业可用"——
> - 应力约束**严格满足**（不再是 v3 的 nudge）
> - 优化器从 OC 升级到 MMA（工业标准）
> - 1000×1000 网格 + AMG 预条件
> - 屈曲约束 / Heaviside robust formulation（消除棋盘格、虚假最优）
> - 自动 refinement loop（Bayesian opt）
> - 专门测试 agent，rubric 验证自动化

---

## 二、v3.0.0 已交付能力（基线）

- 7 波（L→R），16 ADR，407 tests，core 94.2%
- adjoint stress-constrained SIMP（quad），SIMP-on-triangle
- 500×500 sparse direct + ProcessPool parallel study
- LHS + Sobol DOE + lineage tracking
- Cross-platform fingerprint DB
- Jupyter rich display + interactive demo HTML
- 永久红线 100% 守住

详 `docs/quality-rubric-v3.md` + `CHANGELOG.md v3.0.0`。

---

## 三、v4.0 主题（3 主线 + 1 基础设施）

### 主线 1 — 算法/物理深度（S + T + U 波）

- **S 波**：MMA 优化器 + Augmented Lagrangian stress constraint
- **T 波**：BESO-on-triangle + manufacturing projections on triangle（关 D008/D013）
- **U 波**：屈曲 (buckling) eigenvalue + Heaviside robust formulation

### 主线 2 — 性能与规模（W 波 · 一波打包）

- AMG preconditioner（via pyamg optional） + matrix-free CG + 1000×1000 mesh capability

### 主线 3 — 用户面 / 流程（V 波）

- Bayesian opt study driver + auto-refinement loop（关 D010） + comparative HTML report + CLI 增强

### 基础设施 — 测试 agent + v4 final（X 波）

- 专用 `scripts/test_agent.py`：读 rubric，运行验证，产出 `tests/v4_scorecard.json`；集成 CI
- 测试规模拉到 ≥ 600；core 覆盖 ≥ 95%；mutation testing 杀率 ≥ 70%
- tutorial v4 + architecture v4 + ADRs D017-D024+ + rubric 最终评分

---

## 四、6 波分解（S → X）

| 波 | 主题 | 版本 | 估计 LOC | 估计测试 |
|---|---|---|---:|---:|
| **S** | MMA + Augmented Lagrangian stress | v3.1.0 | 800-1200 | 30-50 |
| **T** | BESO-on-triangle + triangle manufacturing | v3.2.0 | 500-800 | 25-40 |
| **U** | Buckling eigenvalue + Heaviside robust | v3.3.0 | 700-1000 | 30-45 |
| **V** | Bayesian opt + auto-refinement + compare HTML + CLI 增强 | v3.4.0 | 600-900 | 25-40 |
| **W** | AMG + 1000×1000 + matrix-free CG + mutation testing | v3.5.0 | 500-800 | 20-35 |
| **X** | Test agent + ≥600 tests + ≥95% cov + v4 final closure | v4.0.0 | 400-700 | 30-50 |

**总计**：~3500-5400 LOC，~160-260 新测试。v3 → v4 测试数 407 → ≥600。

---

## 五、永久红线（v4 期间不破）

继承 v1+v2+v3 全部红线，**v4 加固**：

1. 无 CAD / GUI / cloud / full-3D / commercial 求解器
2. runtime mandatory deps 仍仅 NumPy；scipy / meshio / **pyamg / scikit-optimize** 全 optional
3. 本地可跑 — `pytest -q` 不依赖网络
4. 跨平台 bit-exact "canonical cell 严，其他 ≤1e-9 容忍"（D011 政策延续）
5. 失败仍单行 stderr + 状态码字符串
6. v3.0 rubric **不允许回退** —— v4 commit 必须先验证 v3 rubric 仍 ≥ 99/100
7. v2.0 rubric **不允许回退** —— ≥ 95/100（已是 97/100）
8. v1.0 rubric **不允许回退** —— = 100/100

v4 新增红线：
- **专用 test agent 必须在 CI 跑** —— 不依赖维护者手动校验
- **新可选 dep（pyamg / skopt）若失败必须 graceful degrade**，不让基线测试挂

---

## 六、波执行节奏

- 每波结束：QA gate（ruff + format + mypy + pytest + coverage + 跑 test_agent）
- 每波 commit：atomic + 含 wave 名 + 评分 delta + 诚实 caveat
- 每波 tag：SemVer（v3.1.0 ... v3.5.0 ... v4.0.0）
- Test agent 必须给"绿"才能进下一波
- v4.0 final 前：跑 v1 + v2 + v3 + v4 rubric 全部确认无回退

---

## 七、退出准则（v4.0 final）

1. ✅ 6 波全部 atomic commit + SemVer tag
2. ✅ v4 rubric **≥ 99/100**
3. ✅ v3 rubric 重测 ≥ 99/100（无回退）
4. ✅ v2 rubric 重测 ≥ 95/100（无回退）
5. ✅ v1 rubric 重测 = 100/100（无回退）
6. ✅ test agent 在 CI 强制跑通
7. ✅ `pytest` 全绿（默认 + `--run-slow`）
8. ✅ tutorial v4 + architecture v4 + blueprint-v4 ✅ + ADRs D017-D024+

---

## 八、不在 v4 范围内（明确 defer 到 v5+）

- 3D FEM —— 仍要先评估"是否破 2D-only 红线"
- LLM / AI 顾问 —— 仍永久红线外
- 商业 CAE 适配 —— 永久红线外
- 真正的 GPU 加速 —— 不在 NumPy 路径上

---

## 九、v4.0 final 验收 checklist

- [ ] S 波：core/mma.py + core/augmented_lagrangian.py + stress benchmark σ_PN ≤ limit ±1%
- [ ] T 波：core/triangle_beso.py + core/triangle_manufacturing.py + benchmark
- [ ] U 波：core/buckling.py + core/robust.py + benchmark + eta-min/mean/max 三场对比
- [ ] V 波：core/bayesian_opt.py + core/refinement.py + core/compare.py + CLI 颜色 + 错误诊断
- [ ] W 波：optional [amg] dep + matrix-free CG + 1000×1000 < 10 min benchmark
- [ ] X 波：scripts/test_agent.py + CI step + tests/v4_scorecard.json + ≥600 tests + ≥95% cov + tutorial v4 + arch v4 + ADRs D017-D024
- [ ] v4 rubric 自评 ≥ 99/100（test agent 给绿）
- [ ] v3 rubric 重测 ≥ 99/100
- [ ] v2 rubric 重测 ≥ 95/100
- [ ] v1 rubric 重测 = 100/100

---

## 附录 A — MMA 备忘（S 波准备）

> Method of Moving Asymptotes (Svanberg 1987, 2002) — topology optimization
> 行业标准。OC 是 SIMP 早期专用；MMA 处理任意可微约束 + 任意目标，收敛性
> 比 OC 强很多，尤其在应力约束等多约束场景下。
>
> 算法核心：每次迭代用 **separable convex approximation** 拟合目标 + 约束，
> 然后解一个小型 dual problem 拿到下一步密度。asymptote 边界 (L, U) 随
> 迭代自适应调整。
>
> 实装：~300-500 LOC pure NumPy + 30+ tests + 与 OC 收敛性对比。
>
> 参考：
> - Svanberg, K. (1987). "The method of moving asymptotes—a new method for structural optimization." *IJNME* 24, 359-373.
> - Svanberg, K. (2002). "A class of globally convergent optimization methods based on conservative convex separable approximations." *SIAM J Optim* 12, 555-573.

---

## 附录 B — Augmented Lagrangian 备忘（S 波准备）

> v3.1 Wave L 的 penalty method 不保证应力严格满足 limit（D007 caveat）。
> Augmented Lagrangian 是其升级版：外循环更新 Lagrange 乘子 + 内循环 SIMP。
>
> Update：μ ← μ + ρ · max(0, g(x))，其中 g = σ_PN / σ_lim - 1
> penalty 系数 ρ 缓慢增大。
>
> 实装：~150-250 LOC + outer loop wrapper + 与 v3.1 baseline 对比。

---

## 附录 C — 测试 agent 设计（X 波 核心）

> `scripts/test_agent.py` —— 把 rubric 的每个分项编码成可执行验证。
> 读 `docs/quality-rubric-v4.md` → 跑实际验证（pytest 统计 / coverage /
> 文件存在 / grep 模式 / benchmark 跑通）→ 写 `tests/v4_scorecard.json` +
> 人类可读 summary。
>
> 设计目标：
> 1. **完全自动化** —— 维护者不需要心算各分项
> 2. **诚实客观** —— 直接比对实际产物，不接受人工"声明"
> 3. **可在 CI 强制跑** —— 退出码 0 = ≥ 99，否则非 0
> 4. **可在每波结束后跑** —— 增量看哪几个项目还没拿
>
> 输出格式（`tests/v4_scorecard.json`）：
> ```json
> {
>   "version": "v4.0.0",
>   "total_max": 100,
>   "total_earned": 99,
>   "items": [
>     {"code": "1.1", "title": "Augmented Lagrangian stress", "max": 8,
>      "earned": 8, "status": "PASS", "evidence": "σ_PN converged to 198.5 (≤ 200 limit)"}
>   ],
>   "v3_rubric_check": {"score": 99, "regression": false},
>   "v2_rubric_check": {"score": 97, "regression": false},
>   "v1_rubric_check": {"score": 100, "regression": false}
> }
> ```

---

**v4 蓝图签发。S 波即将开工。**
