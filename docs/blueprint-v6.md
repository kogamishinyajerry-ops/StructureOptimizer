# v6 蓝图 — Production-grade formulations（把 v5 的简化升级为严格实现）

> Status: in progress. Charter (user, 2026-05-24):
> "按照多 agent 分工的架构，持续开发，瞄准一个里程碑持续开发，如果完成了一个步骤、
> 获得了下一步的建议，则自动执行每一个新的建议，如果完成了里程碑，则继续开发下一个
> 里程碑。" — 即：自主规划 v6 大阶段、瞄准蓝图迭代到 ≥99/100、绝对诚实评分、wave 自动推进。

## 永久红线（v1-v5 已建立 · v6 不可破）

- 无 CAD / GUI / cloud / full-3D / commercial 求解器
- 运行时 mandatory deps 仍仅 `numpy`（scipy / pyamg / meshio 全部 optional）
- 本地可跑 — `pytest -q` 不依赖网络
- 失败仍单行 stderr + 状态码字符串
- 自我贬低优先于自我吹嘘
- 无 LLM / AI 顾问能力

v6 在以上约束**内**把精度/严格性推到生产级，不在以外做任何让步。
注：`marching-cubes` 在 2D 即 `marching-squares`（仍 2.5D 挤出，不引入 3D）；
`reverse-mode AD` 用纯 numpy tape 实现（JAX 仍 deferred，避免重依赖）。

## v6 主题

v5 把多物理场打通，但 7 处公式是**有意简化版**（D032 §"Honest scope notes" + 各 ADR
"Reopening criteria" 明列）。v6 = 把这些简化升级为严格、可解析校验的生产级实现：

1. **几何非线性** — 简化 TL → **完整 Total-Lagrangian Green-strain + 2nd PK + 一致切线**
2. **频响** — 无阻尼 → **Rayleigh 阻尼复频响**（C = αM + βK）
3. **热传导** — scalar k → **各向异性 / 正交各向异性张量 k**
4. **多目标** — NSGA-II 双目标 → **NSGA-III ≥3 目标**（Das-Dennis 参考方向 + niching）
5. **可靠性** — Gaussian MC → **FORM/SORM + importance sampling**（尾事件）
6. **几何导出** — voxel STL → **marching-squares 平滑边界 STL**
7. **AD** — forward-mode → **reverse-mode（tape）**

每个升级都配**定量解析校验**（不是 v5 的 qualitative trend）。

## v6 八波

| Wave | 主题 | 关键模块 | 关键校验 | ADR |
|------|------|----------|----------|-----|
| EE | 完整 TL Green-strain Newton | `core/total_lagrangian.py` | Gere elastica **定量**吻合 + patch test | D034 |
| FF | Rayleigh 阻尼复频响 | `core/freq_response.py` (+damped) | SDOF 半功率带宽解析 | D035 |
| GG | 各向异性张量热传导 | `core/thermal.py` (+tensor k) | 正交各向异性 patch test + 旋转不变 | D036 |
| HH | NSGA-III ≥3 目标 | `core/pareto_nsga.py` (+nsga3) | 3-obj DTLZ 参考点关联 + coverage | D037 |
| II | FORM/SORM + importance sampling | `core/reliability.py` (+form) | 线性极限态 β 解析 + IS 方差缩减 | D038 |
| JJ | Marching-squares 平滑边界 STL | `core/stl_export.py` (+smooth) | 面积收敛 vs voxel + 闭合轮廓 | D039 |
| KK | Reverse-mode AD（tape） | `core/autodiff.py` (+reverse) | reverse vs forward vs 中心差分一致 | D040 |
| LL | v6 收口 | 覆盖率 + tutorial §16 + 架构 §16 | rubric ≥ 99 | D041 |

每波按 v5 节奏：模块 + 测试 + 定量校验 + fingerprint（如适用）+ ADR + tutorial 章节。

## 完成度门控

v6 完成 = `python scripts/test_agent.py --rubric v6` 报告：

- [ ] v6 rubric total ≥ 99 / 100
- [ ] v5 regression = False（v5 = 100）
- [ ] v4 regression = False（v4 = 100）
- [ ] **pytest gate green**（D033 — 0 failed / 0 errors）
- [ ] 全红线保持

## 进度（wave 勾选 — 本文件即 v6 progress 文件）

- [x] EE — 完整 TL Green-strain Newton（D034 · 8 tests green · objectivity + 解析 patch）
- [ ] FF — Rayleigh 阻尼复频响
- [ ] GG — 各向异性张量热传导
- [ ] HH — NSGA-III ≥3 目标
- [ ] II — FORM/SORM + importance sampling
- [ ] JJ — Marching-squares 平滑边界 STL
- [ ] KK — Reverse-mode AD（tape）
- [ ] LL — v6 收口（rubric ≥ 99）

> 完成一波把对应 `[ ]` 改 `[x]`，rubric §6.1 检查 ≥6 个 tick。
