# v5 蓝图 — Multi-physics 2D topology optimization

> Status: in progress. Charter (user, verbatim 2025-Q4):
> "作为总负责人，规划下一个大阶段的蓝图。我授权你全权开发，一直瞄准蓝图执行，
> 要有一套专门的测试 agent，有明确的完成度评分机制（要绝对诚实客观），一直迭代开发
> 下去，直至达到你眼里的优秀水准（99 分以上）"

## 永久红线（v1-v4 已建立 · v5 不可破）

- 无 CAD / GUI / cloud / full-3D / commercial 求解器
- 运行时 mandatory deps 仍仅 `numpy`（scipy / pyamg / meshio / matplotlib 全部 optional）
- 本地可跑 — `pytest -q` 不依赖网络
- 失败仍单行 stderr + 状态码字符串
- 自我贬低优先于自我吹嘘
- 无 LLM / AI 顾问能力

v5 在以上约束**内**扩展多物理场能力，不在以外做任何让步。

## v5 主题

v1-v4 已经把"单物理场（线弹性）下的拓扑优化"打到工业可用的水准：MMA + AL stress +
buckling + Heaviside robust + AMG + matrix-free CG + 1000×1000 网格。
v5 把同样的工程纪律推广到**多物理场**：

1. **热传导 TO** — 热阻最小化 / 散热器设计
2. **模态 + 频响 TO** — 特征频率最大化 / 反共振设计
3. **几何非线性 TO** — 大变形 cantilever / snap-through 检测
4. **多材料 TO** — ordered SIMP，2-3 种材料并存
5. **随机 / 可靠性 TO** — Monte Carlo over uncertain loads / 材料属性
6. **Pareto + 工业收口** — NSGA-II Pareto front / 2D→STL 边界导出 / pure-NumPy AD 验证

## v5 六波

| Wave | 主题 | 关键模块 | 关键 benchmark | ADR |
|------|------|----------|----------------|-----|
| Y    | 热传导 TO + 热顺度 | `core/thermal.py`, `core/thermal_simp.py` | `heat_sink`, `heat_exchanger_plate` | D025 |
| Z    | 模态 + 频响 TO | `core/modal.py`, `core/freq_response.py` | `vibrating_beam`, `anti_resonance_bracket` | D026 |
| AA   | 几何非线性 + 大变形 | `core/nonlinear_fem.py`, `core/nonlinear_simp.py` | `nonlinear_cantilever`, `snap_through_arch` | D027 |
| BB   | 多材料 ordered SIMP | `core/multi_material.py` | `bimaterial_beam`, `trimaterial_bracket` | D028 |
| CC   | 随机 / 可靠性 TO | `core/stochastic.py`, `core/reliability.py` | `uncertain_load_bracket`, `robust_compliance` | D029 |
| DD   | Pareto + STL 导出 + AD + 收口 | `core/pareto_nsga.py`, `core/stl_export.py`, `core/autodiff.py` | n/a | D030-D032 |

每波都按 v4 的节奏：模块 + 测试 + 至少 1 个 benchmark + fingerprint + ADR + tutorial 章节。

## 完成度门控

v5 完成 = `python scripts/test_agent.py` 报告

- `v5 rubric total ≥ 99 / 100`
- `v4 regression = False` (v4 = 100)
- `v3 regression = False`
- `v2 regression = False`
- `v1 regression = False`

四个旧版本任何一个回归 → release blocked.

## 失败模式守则（v5 特化）

- 多物理场容易"看起来收敛了但其实算错了" — **每个新求解器必带 analytical 校验测试**
  （e.g. 热传导：1D 杆解析解；模态：单跨梁 Euler-Bernoulli 频率公式；几何非线性：
  end-loaded cantilever 大变形 Gere 公式）。
- 多材料 SIMP 的 ordered penalization 容易 cheating（在两材料之间反复横跳）—
  必须 fingerprint 化 + 物理一致性测试。
- Monte Carlo 必须 RNG-seed 化 + 跨平台 bit-exact 校验。

## v5 完成的标志

- 6 波全部 LANDED，tag v3.6.0 → v4.5.0（按 v4 间隔节奏）
- v5.0.0 tag 标志完成
- `tests/v5_scorecard.json` 报告 ≥ 99
- `docs/blueprint-v5.md` 所有 wave 标 [x]
- `docs/quality-rubric-v5.md` 每条 PASS 且证据可追溯
- 4 代旧 rubric 全部零回归

## 完成进度

- [ ] v5 foundation: blueprint + rubric + test_agent + scorecard baseline (this commit)
- [ ] Wave Y · 热传导 TO + 热顺度
- [ ] Wave Z · 模态 + 频响 TO
- [ ] Wave AA · 几何非线性 + 大变形
- [ ] Wave BB · 多材料 ordered SIMP
- [ ] Wave CC · 随机 / 可靠性 TO
- [ ] Wave DD · Pareto + STL + AD + v5 收口
