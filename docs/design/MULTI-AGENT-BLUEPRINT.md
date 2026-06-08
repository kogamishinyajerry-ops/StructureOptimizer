# StructureOptimizer — 多智能体流水线拓扑优化 · 架构蓝图
<!-- 对外定位 = multi-agent pipeline（强调分工·非协作）。详见 §2。 -->


> **状态：** 设计（未实现）。由三套独立设计提案（reuse-first / contract-first / experience-first）综合，**折入两轮内部红队 + Codex 异源审查（第三轴，verdict=CHANGES_REQUIRED → 见 §11）**。定位口径已定：**中道「multi-agent pipeline」**（决策 B，2026-06-05，见 §2/§11）。
> **本设计必须不重蹈的伤疤：** v6–v16 是一条"自评打分跑步机"——约 30 个自己给自己打 100 分、却从无调用方的死代码模块。本蓝图里**每一个 agent 都是 `run_config` 唯一活路径上已存在的类**；零新增不可达类、零新引擎数值。

> **决策记录（2026-06-05）：** ① **Replan agent 已砍** —— 红队判定其"默认关、只靠造假 demo 触发"正中 v6–v16 死代码伤疤；范围**锁定 Phase 1-2**（trace 驱动实时轨道 + 诚实 gate 态/Verification critic 细节），两阶段 100% 可达、零新控制流、零引擎数值改动。下文 §7 Phase 3 / §9 决策 A 保留仅作存档。② 下一步 = 先经 Codex 异源审蓝图，再动手 Phase 1。

---

## 0. 一句话

6 阶段流水线**在代码里早已是 agent 形态**（`PipelineAgent` 子类 + `PipelineOrchestrator`，`structure_optimizer/core/pipeline.py`），每次 run 都已落 `agents_trace.json` 但**零消费者**；前端 `GuidedMode` 用 5 个 `setTimeout` **假装**在跑流水线。本工作不是"造 agent"，而是：**(a)** 让每个阶段已算出的 gate 裁决与产物**实时可观测**，**(b)** 让工作台渲染**真实** trace 的逐阶段产物接力、删掉脚本动画，**(c)** 把"自洽门 vs 分类门 vs 独立 critic 门"诚实分级。（综合稿曾含一个新协作语义 replan，已于 2026-06-05 砍掉，见决策记录。）

---

## 1. 已核实的地基（事实，非推断）

逐项对当前代码核对（红队 2 verdict=SOUND，逐行确认 `maps_to_code` 属实）：

| 断言 | 证据 |
|---|---|
| 6 阶段已是 agent 类 | `pipeline.py:132 class PipelineAgent(ABC)`；`:461 class PipelineOrchestrator` |
| 唯一活路径 | `workflow.py:67 return PipelineOrchestrator().run(ctx)`；CLI `cli.py:212`、study `study.py:253,313`、web `server/runner.py:131` 全部经此 |
| trace 写出（**仅成功完成的 run**，Codex 校正） | `pipeline.py:72 TRACE_FILENAME`、`:505-523 _write_trace`；今日 `runs/simple_bracket/2026-06-05-*/agents_trace.json` 实存。**非"每次 run"**——`precondition` 在 try 外(`:483`)、普通异常未捕获、既有目录 `FileExistsError` 直接抛(`tests/test_pipeline_orchestration.py:184-191`)，早期失败不写 trace |
| trace 零消费者 | `grep -rl agents_trace server web` → 空（前端硬编码 STAGES + setTimeout） |
| 前端是假动画 | `GuidedMode.tsx:105-145` 用 5 个 `setTimeout` 驱动 6 段转场中的 5 段 |
| 诚实标签已在 | `pipeline.py:74 PIPELINE_LABEL="deterministic-six-agent"`；`:8-15` 明示"agent 指契约化阶段，非自治/非 LLM" |

> 注：旧 `runs/cantilever/2026-06-04-*` 无 trace —— 它们是 trace 特性上线前的 run，不影响结论。

---

## 2. 定位与诚实分类法（决策 B = 中道「multi-agent pipeline」，2026-06-05）

**对外定位：「多智能体流水线 · multi-agent pipeline」** —— 强调 6 个契约化阶段的**分工**，**不**用"协作/协商/自治"等暗示智能体独立博弈的词（三轴一致判定那是 overclaim：流水线严格线性、确定性、单线程、`pipeline.py:464-467` 明令禁并行）。代码原生诚实标签 `deterministic-six-agent`(`pipeline.py:74`) 保持可见。

**"agent" 的诚实定义** = 携带 `precondition / gate / 产物契约` 的**确定性**流水线阶段（非 LLM、非自治、零随机）。6 个阶段按"决策权"诚实分三档（**Codex C3 校正**）：

- **1 个独立 critic（唯一名副其实）**
  - **Verification** —— 不信优化器自报，从 `input.json`+`density.npy` **独立重解 FEM**，可 veto（`ok=False`）。全流程唯一"证明了优化器没替自己断言过的东西"的阶段。
- **2 个分类/门控阶段（有 gate，但不独立决策）**
  - **Optimizer** —— 核心求解器，按 `config.optimization.algorithm` dispatch SIMP/BESO（`pipeline.py:231-232`），唯一吐实时密度帧。决策权 = 算法选择，仅此。
  - **ConvergenceGate** —— **读取**优化器已写的 `stop_reason` 做分类（`pipeline.py:266-280`），**非独立判定**。称 "stop-reason 分类门"，**不称 decider**。
- **3 个确定性变换阶段（唯一"自治"= fail-closed 自洽门）**
  - **ProblemDefinition**（指纹 provenance hash；真校验在上游 `validate_config`+server 400）· **Mesh**（离散化）· **Export/Report**（渲染产物）。
- **+ 1 coordinator** `PipelineOrchestrator.run`（线性 for-loop，单线程，**禁并行**）· **+ 1 内部 Persistence step**（`domain_agent=False`）· **~~Replan agent~~ 已砍**（2026-06-05）。

**Gate 三档（UI 视觉必须区分，红队 must-fix #3 + Codex C3）：**
| 门类型 | 阶段 | 语义 | 视觉 |
|---|---|---|---|
| 自洽门 | config / mesh / result-shape / export | 正确引擎下**永不失败**，只防内部损坏 | 低调绿勾（≠"独立质检通过"） |
| 分类门 | ConvergenceGate | 判读收敛 vs 预算 | 绿 / 琥珀 |
| **独立 critic 门** | **Verification** | 独立重解、可否决 | **最突出**；琥珀 = 真分歧 |

**UI legend 文案（直接落地用）：**
- 标题：**多智能体流水线 · multi-agent pipeline**
- 副标：**6 个契约化阶段分工 · 确定性 · 非 LLM · 唯一独立验证 critic = Verification**
- 「每个阶段亮起 = 真实引擎阶段完成（非脚本）」
- 「绿 = gate 通过 · 琥珀 = 工程负结果待复核（run 仍完成）· 红 = 结构中止」
- 三类门徽章：「自洽门」防内部损坏 ·「分类门」收敛判读 ·「独立 critic」独立重解可否决

---

## 3. Agent 名册（契约 · 落地代码）

每个 agent = 既有类。"agency" 的诚实定义 = **对真实引擎输出拥有一个 gate 裁决**。

| # | Agent | 输入 | 产物 | Gate | 失败处理 | maps_to_code |
|---|---|---|---|---|---|---|
| 01 | **ProblemDefinition**(确定性) | `BenchmarkConfig`(上游已校验) | `ctx.input_hash="sha256:"+…`（仅 hash/裁决，**无文件**） | `GATE-CONFIG`：hash 带 `sha256:` 前缀且 name 非空（**自洽门**） | 硬中止；UI 须暴露真失败模式=HTTP-400，不伪造"已校验" | `pipeline.py:169-189` → `run_store.input_hash` |
| 02 | **Mesh**(确定性) | `ctx.config` | 内存 `StructuredMesh` | `GATE-MESH`：mesh 有 `.elements`（**自洽门**） | 硬中止（几何损坏≠工程负结果） | `pipeline.py:192-213` → `mesh.create_structured_mesh` |
| 03 | **Optimizer**(决策) | `ctx.config`+`ctx.mesh`+`ctx.on_iteration` | `ctx.result:OptimizationResult` + 实时密度帧 | `GATE-RESULT-SHAPE`：字段齐（**自洽门**） | 硬中止；**BESO 忽略 on_iteration**(`algorithm_base.py:97-99`)→无实时帧，UI 不得伪造 | `pipeline.py:216-247` → `run_simp`(`simp.py:74`)，实时缝 `simp.py:158-159` |
| 04 | **ConvergenceGate**(决策) | `ctx.result.stop_reason`+metrics | 仅裁决，**无文件**(`run()` no-op) | `GATE-CONVERGENCE`：`change_tolerance`=绿 / `max_iterations`=**琥珀**(replan-eligible)（**真决策门**） | 仅未知 stop_reason 才硬中止 | `pipeline.py:250-282` |
| — | **Persistence**(内部) | config+result+hash+lineage | `input.json/metrics.csv/density.npy/lineage.json/summary.json` | `GATE-RUNDIR`：summary.json 存在 | 目录在 optimize **之后**建(`:309 exist_ok=False`)→崩溃不留孤儿目录 | `pipeline.py:285-354` |
| 05 | **Verification**(critic) | `run_dir/input.json`+`density.npy`（文件边界） | `verification.json`+`manufacturability.json`（逐约束，`source:"independent_verification"`） | `GATE-VERIFICATION`（**FAIL-SOFT，唯一真 critic 门**）：工程 FAIL→`ok=False` 但 run **仍 completed**(exit 0) | 两值：软 veto(继续) vs schema 损坏(中止)；`verify_run` 契约 no-raise | `pipeline.py:357-385` → `verification.verify_run` |
| 06 | **Export/Report**(确定性) | run_dir+mesh+result+config | 6 个 PNG/GIF + `report.md`（SVG/DXF/STL 走按需 `/export`，不在此阶段） | `GATE-EXPORT`：6 文件齐（**自洽门**） | 硬中止；终产物明示"优化候选，待工程复核" | `pipeline.py:388-439` |

**Gate 分级（UI 视觉必须区分，红队 must-fix #3）：**
- **自洽门**（config/mesh/result-shape/export）—— 正确引擎下**永不失败**，只防内部损坏，是低门槛。绿=「无内部损坏」，**不可**渲染成"独立质检通过"。
- **真决策门**（Convergence：收敛 vs 预算）+ **真 critic 门**（Verification：独立重解可 veto）—— 唯一证明"优化器没自己断言过的东西"的两道。**Verification 的琥珀态视觉上要最突出。**

---

## 4. Coordinator 与引擎接缝（on_stage）

**位置：** `PipelineOrchestrator.run`（`pipeline.py:461-507`）——它**已经是** coordinator：线性 for-loop，每阶段 `precondition→run→postcondition(gate)→文件系统快照 diff→trace.append`，已实现 all-or-nothing（`PipelineGateError` 原样重抛）。**扩展，不替换。禁并行**（并行会重排浮点累加、毁字节复现，`pipeline.py:464-467` 已明令禁止）。

**三处加性、opt-in 改动：**
1. **事件汇 `on_stage`** —— `PipelineContext` 加 `on_stage:Any=None` 字段（`simp.py:158` 同款 None-guard）。循环内发 `stage_start`/`stage_end`/`stage_error`，**`stage_end` 帧用与 trace record 完全同一份 dict 构造（减 `wall_ms`）**（红队 2 must-fix #1：否则 live 帧多对一、无法 diff，guarantee「live==disk」沦为口号）。`on_stage` 经 `run_config` 签名穿线，与 `on_iteration` 一致。**on_stage 帧不带任何 density**（红队 2 P3：实时密度只走 on_iteration）。
2. **server 桥** —— `runner._execute` 加 `on_stage` 闭包，把新帧 `.put()` 到**同一个** `state.frames` 队列（保单 SENTINEL、单消费者守卫不变）。
3. **(Phase 3) 重派** —— `GateVerdict` 加 `action:str="proceed"` 默认字段（frozen，加性、向后兼容，红队 2 must-fix #2）；ConvergenceGate 仅在 `status=="max_iterations"` 且 budget 在场时设 `action="replan"`，**`ok` 始终 True**（max_iterations 仍是合法 PASS），琥珀态从 `status` 派生而非翻 `ok`。

---

## 5. 字节复现保证（含必须先落地的回归测试）

**缝法：** 一个新观测回调 `on_stage`，与已验证的 `on_iteration` 同构——None 默认、纯观测、引擎不从中取态。

**默认路径字节不变的 4 条理由：**
1. 所有字节敏感调用方传 None：CLI(`cli.py:212`)、study(`study.py:253,313`) 从不传 on_stage；仅 `server/runner.py` 传。
2. 纯观测：收已算好的 `verdict/new_files/detail/wall_ms`，无返回、无 RNG、无重排、无并行。
3. 唯一新文件仍是 `agents_trace.json`，唯一非确定字段 `wall_ms` 不入 summary/density/metrics/verification，且 `SO_TRACE_DETERMINISTIC=1` 置零。
4. 循环保持线性单线程；`on_stage=None` 保持 `PipelineContext` 可 pickle（study 的 `ProcessPoolExecutor` 不破）。

**回归门（红队 must-fix #2/#4 —— Phase 1 的第一个 commit，先于任何 on_stage 发射）：**
> 在当前 main 上先采 golden hash → 再加 on_stage → 断言**所有稳定产物**在 `SO_TRACE_DETERMINISTIC=1`、`on_stage=None`（CLI 路径）下**字节一致**。产物集 = `{input.json, density.npy, metrics.csv, summary.json, verification.json, lineage.json, manufacturability.json}`（**Codex P2 校正：原稿漏了 `lineage.json`(`pipeline.py:317-325`) + `manufacturability.json`(`verification.py:112-113`)**），仅排除 `agents_trace.json` 自身。再加一例：带一个 no-op `on_stage` 回调也须字节一致（证明 None-guard 在场亦不扰动）。**此测试不绿，任何 on_stage 代码不许合入。** 在它落地前，「字节路径不变」是承诺、不是保证。

---

## 6. 工作台可视化（真·协作，删假动画）

建在既有 `GuidedMode` + WS 流之上，**删掉 `GuidedMode.tsx:105-145` 的 5 个 setTimeout**，改由真实事件驱动。

- **数据脊柱：** `useRun.ts` 的 `RunSnapshot` 加 `stages:StageEvent[]`（与 `iterations[]` 同级），在既有 `onmessage` 分发里累积（同款 stale-socket 守卫、单 SENTINEL）。**新帧走既有队列，不开第二消费者。**
- **轨道（升级既有 stepper）：** 每格态 = idle(灰)→active(脉冲)→ 绿(gate ok) / 琥珀(工程软失败：Convergence `max_iterations` 或 Verification `ok=false`) / 红(结构中止)。中心仍是真 `DensityViewport` 流式密度。
- **握手动画必须数据驱动**（红队 P2）：仅 trace 实测 `artifacts[]` 非空的格（persistence/verification/export）或持具名内存产物的格（optimizer→density）才播"产物滑块"；**无产物的格（problem_definition/mesh/convergence_gate）只显原地裁决徽章，不伪造握手。**
- **money shot（诚实戏剧）：** Verification 格激活时独立重解，可翻**琥珀**并点出具体失败项（体积/连通/应力）——优化器与验证器真实分歧。
- **诚实 legend：** 明说"每个亮起=真实引擎阶段完成·非脚本"，并解释绿/琥珀/红、以及"自洽门 vs 独立 critic 门"的区别（红队 must-fix #1/#3）。
- **历史回放：** 新增 `GET /api/runs/{id}/trace` 直供磁盘 `agents_trace.json`；`loadRun` 由它重建 `stages[]`。（红队 2 P2：这需 route + `fetchTrace()` + loadRun 接线共 ~3 处后端触点，非一行。）

---

## 7. 分阶段路线图

### Phase 1 —— trace 驱动实时轨道（最薄诚实切片）
**目标：** 轨道由真实逐阶段事件点亮（非 setTimeout），cantilever 端到端，**零引擎数值改动**。
**切片：** ①**先落字节回归测试**(§5)；② `PipelineContext` 加 `on_stage`，循环发 start/end/error（end 帧复用 trace record dict 减 wall_ms）；③ `run_config` 穿线；④ `runner._execute` 加 on_stage 闭包 + `StageFrame` pydantic + TS union；⑤ `useRun` 折进 `stages[]`；⑥ `GuidedMode` 由 `stages[]` 驱动，删 5 个 timer（`MIN_SOLVE_MS` 仅留作 hero 密度展示地板）。
**demo 证明：** 录 cantilever run，6 点各在其 agent 启动时 active、gate 过时打勾；屏上转场顺序 diff `agents_trace.json` 的 `wall_ms` 顺序——一致。字节门：CLI run 前后哈希一致。

### Phase 2 —— 诚实 gate 态 + Verification critic 细节
**目标：** gate 能因真实原因非绿；验证器的独立分歧逐项可读。
**切片：** 把 `verification.json` 既有 `constraints[]/*_ok` + 收敛 `stop_reason` 带进 stage 事件；渲染逐项 chip（体积/连通/冻结/挖空/应力/可制造）绿/琥珀/红；Convergence 区分 `change_tolerance`(绿) vs `max_iterations`(琥珀)；替掉永远"复核完成"的假徽章（`GuidedMode.tsx:232-236`）。
**demo 证明：** 两 run 并排——一全绿 Verified，一连通性失败(琥珀+具体红项)。**两者都 completed、都不崩**(exit 0)。琥珀态 1:1 映射真实 `verification.json` 字段。

### ~~Phase 3 —— Replan 重派~~ ❌ 已砍（2026-06-05 · 仅存档）+ 主工作台同款轨道（降级为 Phase 2 stretch）
> **决策：砍。** 红队 must-fix #2 判定 Replan 默认 `replan_budget=0`→所有真实路径永不触发、只靠手造 demo config=正中 v6-v16 伤疤；用户裁决砍掉。下文保留仅作存档。
> **注：** "主工作台同款轨道"（把轨道从 GuidedMode 推广到 `App.tsx` 主视图）与 Replan 无关，复用同一份 `stages[]` state，可作为 **Phase 2 的 stretch** 纳入，不随 Replan 一起砍。
>
> ~~两条出路，需人裁决（见 §9 决策 A）：~~
> - **(a) 砍** —— 只发 Phase 1-2（100% 可达、零新控制流），最诚实最稳。
> - **(b) 留但严格** —— 必须在**某真 benchmark 的默认配置**上自然触发 `max_iterations`（非 rigged seed），且**预先实跑验证 attempt-2 真能收敛**（红队 P1：`max_iter*1.5` 不保证第二次撞 `change_tolerance`，刚性问题可能再次耗尽 cap=2→demo 反而展示"协作失败"）。另加测试断言 `replan_budget=0` ⇒ 恰好一个 run_dir、无 replan 记录。

**若留，技术事实（红队 2 P3）：** replan = 一次**完整的第二趟 pipeline**入兄弟目录（7 阶段全重跑，非"只重派 Optimizer"），经 `lineage.json parent_id` 链接，轨道渲染为"attempt1(折叠)→attempt2(完整)"，帧加 `attempt` 标签消歧。复用 study 已证安全的 re-entrant `run_config`，无新数值。

---

## 8. 反表演保证（折入红队）

1. 每个 agent 都在唯一活路径上（CLI/study/web 全经 `PipelineOrchestrator.run`）；新代码只是回调 + UI 读已产数据。本设计**删除**表演（5 个 setTimeout），不新增抽象。
2. 无假产物：ConvergenceGate/ProblemDefinition 不产文件，trace 诚实记 `artifacts:[]`，UI 只显裁决徽章。
3. gate 裁决真实两值：Phase-2 连通性失败 demo 证 Verification 琥珀=真独立 FEM 重解分歧，区别于崩溃。
4. live==disk：Phase-3 diff live `stages[]` 与磁盘 `agents_trace.json`；on_stage 只发 orchestrator 已为 trace 算好的值（同 dict 构造）。
5. 字节路径可证不变：§5 的 CI 哈希测试 Phase-1 先落。
6. Replan 触发即可见、否则按构造惰性，绝不"静默死亡却宣称可用"。
7. 保留诚实标签 `deterministic-six-agent` + 非 LLM 声明。"协作"只指 Verification 真独立 + 有界 replan，不夸自治。
8. **诚实分级**（红队新增）：UI 区分"自洽门"与"独立 critic 门"，不给 7 门同样绿勾，不把 ~1.5 层真质检吹成 6 层。

---

## 9. 留给人的决策（建之前要对齐）

- **决策 A · Replan：✅ 已决 = 砍（2026-06-05）。** 只发 Phase 1-2；§7 Phase 3 仅存档。
- **决策 B · "协作"对外口径：** 接受"3 决策 agent + 3 确定性步骤 + 1 coordinator"的诚实说法，还是想要更强的市场措辞（红队 P2 警告：线性依赖叫"协作"是叙事膨胀）。
- **决策 C · ProblemDefinition 格：** 暴露真失败模式（HTTP-400 pre-rail 守卫）/ 直接改标签为"指纹(provenance hash)"不声称校验。
- **决策 D · 验证负例触发器：** 是否也让 Verification 工程失败触发 replan（需定哪些 `OptimizationConfig` 杠杆、防无限调参环）——Phase 3+，暂不纳入。
- **决策 E · 多 socket/双视图：** 单消费者守卫不支持两个并发流消费者；若要 presenter+audience 双视图需队列 fan-out 广播（超本蓝图范围）。

---

## 附：红队折入清单（相对综合初稿的修订）

| 来源 | 修订 |
|---|---|
| 红队1 P1 #1 | 弃"6 自治 agent"→"3 决策+3 确定+1 coordinator"诚实分类，写进 UI legend |
| 红队1 P1 #2 | Replan 降级为**开放决策**（砍/严格条件化），不再作为核心宣称 |
| 红队1 P1 #3 | gate 分级（自洽门 vs critic 门），视觉区分，Verification 琥珀最突出 |
| 红队1 P2 #2 | 握手动画数据驱动 trace `artifacts[]`，无产物格不伪造握手 |
| 红队1 P2 #2(repro) | 字节回归测试列为 Phase-1 **第一个** commit |
| 红队2 P2 #1 | on_stage end 帧用与 trace record 同一 dict 构造（减 wall_ms）才可 diff |
| 红队2 P3 #4 | `GateVerdict` 加 `action="proceed"` 默认字段，max_iter 保 ok=True |
| 红队2 P3 #5 | on_stage 帧不带 density（实时密度只走 on_iteration） |
| 红队2 P3 #3 | 明示 replan=完整第二趟 pipeline（非只重派 Optimizer） |

---

## 11. Codex 异源审查（第三轴 · 86gs gpt-5.5 xhigh · 2026-06-05）

**VERDICT: CHANGES_REQUIRED** —— 底线："Phase 1-2 值得建，但只能定位为『真实流水线可观测化 + 独立验证可视化』，先修正 trace/error/live==disk 契约和过度『多 agent 协作』措辞后再开工。"

**事实核实（Codex 逐条对照源码）：** 6 阶段=`PipelineAgent` 子类 [真]；`run_config` 唯一路径 [真]；CLI/study/server 全经此 [真]；`GuidedMode` setTimeout 假动画 [真]；`on_iteration` None-guard 字节安全 [真]；**`agents_trace.json` "每次必写" [部分]——只有成功完成的 run 写**（已折入 §1）。

| # | 严重度 | 发现 | 处置 |
|---|---|---|---|
| C1 | P1 | **trace/error 接缝不稳**：`precondition` 在 try 外、普通异常无 trace、`PipelineGateError` 后裸 `raise` 在 except 块外，不保证原异常重抛。Phase 1 的 `stage_error` 依赖此接缝 | **Phase 1 实现项**：要么把 stage_error 降级为"仅 completed run 必写 trace"，要么把 precondition/run/postcondition 全纳入异常记录路径、在 except 内写 partial trace + 原样重抛。先补一个失败注入测试 |
| C2 | P1 | **live==disk 契约不精确**：设计发 start/end/error 三类帧，但磁盘 trace 每阶段只有一条完成 record；混入 start/error 就无法直接等价 | **折入 §4 wire 契约**：`stage_start` 仅驱动 active；**只有 `stage_end.record` 减 `wall_ms` 后** 与磁盘 `agents[]` 逐项相等；测试按此过滤规则 diff |
| C3 | P2 | **诚实口径仍偏营销**：ConvergenceGate 不独立决策、只读优化器已写的 `stop_reason`(`pipeline.py:266-280`)；Optimizer 主要按 config dispatch(`:231-232`)。**只有 Verification 是名副其实的 critic** | **✅ 已决（决策 B = 中道, 2026-06-05）**：对外定位"多智能体流水线 · multi-agent pipeline"（强调分工、非协作）；ConvergenceGate 称 "stop-reason 分类门"、不称 decider；只有 Verification 称 critic。**§2 已据此重写**（含 UI legend 文案） |
| C4 | P2 | **新 WS pydantic 帧不自动守约**：`server/app.py:241-246` 直接 `send_json(frame)`，加 `StageFrame` model 不会强制 wire 形状 | **Phase 1 实现项**：runner 构造 frame 时用 model 序列化，或加后端契约测试校验所有 live stage frame |
| C5 | P2 | **单消费者守卫的重连盲点**：断线于 SENTINEL 前，第二个消费者会继续 drain 同一破坏性队列、历史帧已丢 | **Phase 1 实现项**：加 stream_started/consumed 一次性守卫，或重连走 `/trace`+final result 重建、不再 drain 残队列 |
| C6 | P2 | **字节回归测试漏产物**：原稿只测 5 个，漏了 `lineage.json`+`manufacturability.json` | **已折入 §5**：产物集扩到 7 个，仅排除 `agents_trace.json` |
| C7 | P3 | **trace route run-id 不匹配**：内存 run id 是 UUID、磁盘是 timestamp，`RunState.run_dir` 仅进程内 | **Phase 1 文档/实现项**：注明 `/trace` 仅支持当前 manager 内 run，或补磁盘索引 lookup |

**Codex ENDORSEMENTS：** Replan 砍掉正确；"自洽门 vs 独立 critic 门"必须保留；删 setTimeout 用真实 trace 驱动值得做；`on_stage` opt-in + 不带 density 的方向安全。

**三轴共识：** Understand→Design workflow + 两轮内部红队 + Codex 全部指向 **建 Phase 1-2**，且全部要求**诚实定位**。三轴一致认定唯一真 critic = Verification。
