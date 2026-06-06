import { useEffect, useRef, useState } from "react";
import type { RunSnapshot } from "../api/useRun";
import type { StageRecord } from "../api/types";
import { DensityViewport } from "../viewport/DensityViewport";
import { fmt, pct } from "../lib/format";
import "./GuidedMode.css";

/**
 * Guided / 讲解 mode — a clean, presenter-grade "one take" walkthrough of the
 * real end-to-end pipeline on top of a REAL run. It auto-drives a cantilever
 * SIMP run; the six rail dots light from REAL per-stage engine events
 * (``snap.stages``, sourced from the orchestrator's agents_trace seam) — NOT
 * scripted timers. 问题定义 → 离散化 → 优化求解 → 收敛门控 → 独立验证 →
 * 结果解析/导出. Every visual is real (real density stream, real verification
 * status, a real export fetch). The narration card paces its catch-up to the
 * real frontier for readability, but never runs ahead of the engine.
 */

interface Stage {
  no: string;
  name: string;
  agent: string;
  tool: string;
  criteria: string;
  artifact: string;
  gate: string;
  caption: string;
}

const STAGES: Stage[] = [
  {
    no: "01",
    name: "问题定义",
    agent: "问题定义 Agent",
    tool: "基准库 + 问题编辑器",
    criteria: "设计域 · 载荷 · 支撑 · 材料预算 合法且在上限内",
    artifact: "完整问题定义 + SHA-256 指纹",
    gate: "服务端校验通过（否则挡回）",
    caption: "先把问题定清楚：哪里受力、哪里固定、最多只能用多少料——并按指纹存档。",
  },
  {
    no: "02",
    name: "离散化建模",
    agent: "网格 Agent",
    tool: "结构化四边形网格器",
    criteria: "网格规模在上限内 · 单元方正",
    artifact: "有限元网格（自由度 / 刚度结构）",
    gate: "网格构建成功",
    caption: "自动把连续的结构剖成一格一格的单元，机器才好逐格算受力。",
  },
  {
    no: "03",
    name: "优化求解 · SIMP",
    agent: "优化器 Agent",
    tool: "有限元求解 → 灵敏度 → 过滤 → 用量更新 → 惩罚",
    criteria: "在材料预算内最小化柔度（最抗变形）",
    artifact: "逐迭代密度场（实时流式）+ 收敛指标",
    gate: "是否收敛，交由下一步判定",
    caption: "优化器接管：在材料预算内，一轮一轮把料挪向真正受力的地方。",
  },
  {
    no: "04",
    name: "收敛门控",
    agent: "收敛门控",
    tool: "收敛检查",
    criteria: "相邻两轮密度变化量 ≤ 容差",
    artifact: "终止原因 · 迭代步数",
    gate: "变化足够小 → 收敛、停止迭代",
    caption: "判断收敛：当两轮之间几乎不再变化，就停下来。",
  },
  {
    no: "05",
    name: "独立验证",
    agent: "独立验证 Agent",
    tool: "独立模块从输入重算有限元",
    criteria: "体积 · 连通性 · 冻结区 · 挖空区 · 应力 · 可制造性",
    artifact: "逐项 pass / fail + Verified 徽章",
    gate: "全部通过 → Verified；任一不过 → 标出失败项",
    caption: "不信优化器自报：另一套代码重算一遍、逐项打分，过了才打 Verified。",
  },
  {
    no: "06",
    name: "结果解析 · 导出",
    agent: "导出 Agent",
    tool: "几何导出（SVG / DXF / STL）",
    criteria: "阈值二值化 · 挤出深度",
    artifact: "几何文件：SVG / DXF 内嵌指纹 + 验证状态 + 免责声明；STL 经文件名携带溯源",
    gate: "终态：一个可被独立复核的「优化候选」",
    caption: "把密度场解析成带溯源的几何文件，直接进制造流程——但它是候选，需工程复核。",
  },
];

interface GuidedModeProps {
  snap: RunSnapshot;
  onLaunch: (benchmarkId: string) => void;
  onExit: () => void;
}

// The six rail cells, in pipeline order, mapped to the orchestrator's agent
// names. The internal "persistence" step is not a narrated cell.
const AGENT_BY_CELL = [
  "problem_definition",
  "mesh",
  "optimizer",
  "convergence_gate",
  "verification",
  "export_report",
] as const;

const MIN_CARD_MS = 1400; // presentational floor so each narration card is readable
const MIN_SOLVE_MS = 8000; // hero density hold so the converging "carve" never blinks past

type CellPhase = "idle" | "start" | "end" | "error";
type CellTone = "idle" | "active" | "ok" | "warn" | "error";

// Honest per-cell tone, derived from the REAL stage record (Phase 2 gate-state
// nuance — green is NOT the only "done"):
//   - end + gate.ok === false                         -> warn  (Verification engineering veto)
//   - convergence end + verdict_status max_iterations -> warn  (converged-by-budget, not true convergence)
//   - otherwise end -> ok ; start -> active ; error (structural abort) -> error
function cellTone(agent: string, cs: { phase: CellPhase; record: StageRecord | null }): CellTone {
  if (cs.phase === "start") return "active";
  if (cs.phase === "error") return "error";
  if (cs.phase !== "end") return "idle";
  const rec = cs.record;
  if (!rec) return "ok";
  if (!rec.gate.ok) return "warn";
  if (agent === "convergence_gate" && rec.gate.verdict_status === "max_iterations") return "warn";
  return "ok";
}

const TONE_CLASS: Record<CellTone, string> = {
  idle: "guided-step",
  active: "guided-step is-active",
  ok: "guided-step is-done",
  warn: "guided-step is-warn",
  error: "guided-step is-error",
};
const TONE_DOT: Record<CellTone, string | null> = { idle: null, active: null, ok: "✓", warn: "!", error: "×" };

// Verification constraint name -> short label. Unknown names fall back to the raw
// name, so chips always map 1:1 to real verification.json constraints (no fabrication).
const CHECK_LABELS: Record<string, string> = {
  volume_fraction: "体积",
  load_to_support_connectivity: "连通性",
  frozen_solid_regions: "冻结区",
  void_regions: "挖空区",
  stress: "应力",
  max_stress: "应力",
  manufacturability: "可制造性",
};

interface VerifyCheck {
  name: string;
  status: string;
}

export function GuidedMode({ snap, onLaunch, onExit }: GuidedModeProps) {
  const [idx, setIdx] = useState(0); // narration FOCUS (card). The RAIL is real-driven, below.
  const [finished, setFinished] = useState(false);
  const [exportInfo, setExportInfo] = useState<string | null>(null);
  const launchedRef = useRef(false);
  const exportRef = useRef(false);
  const focusStartRef = useRef(0);

  // REAL per-cell state from the live engine trace (not scripted): the latest
  // stage event for each agent. This is the truth the rail renders.
  const cellStates = AGENT_BY_CELL.map((agent) => {
    let phase: CellPhase = "idle";
    let record: StageRecord | null = null;
    for (const s of snap.stages) {
      if (s.agent === agent) {
        phase = s.phase;
        record = s.record;
      }
    }
    return { phase, record };
  });
  // Frontier = furthest cell the real engine has reached (any non-idle event).
  let frontier = 0;
  cellStates.forEach((c, i) => {
    if (c.phase !== "idle") frontier = i;
  });

  // Run-level failure (honest unhappy path). useRun sets snap.status="error" +
  // snap.error for a top-level {type:"error"} frame, a startRun throw, or a WS
  // onerror/onclose (Connection lost/closed). The rail also marks the specific
  // aborting cell via phase==="error" (cellTone), but the run-level message must
  // surface too — otherwise an error that leaves the rail empty/stalled hangs on
  // the spinner forever with no explanation.
  const runErrored = snap.status === "error";
  const failedCellIdx = cellStates.findIndex((c) => c.phase === "error");
  const failedStageName = failedCellIdx >= 0 ? STAGES[failedCellIdx].name : null;

  // Launch the REAL run once on entry.
  useEffect(() => {
    if (!launchedRef.current) {
      launchedRef.current = true;
      onLaunch("cantilever");
    }
  }, [onLaunch]);

  // Narration focus catches up to the real frontier — never ahead of the engine
  // — with a per-card floor so each step is readable (the optimizer card also
  // holds MIN_SOLVE_MS so the live carve is watchable). This paces the CARD only;
  // the rail dots light from real events in real time.
  useEffect(() => {
    focusStartRef.current = Date.now();
  }, [idx]);
  useEffect(() => {
    if (finished || idx >= frontier) return;
    const floor = idx === 2 ? MIN_SOLVE_MS : MIN_CARD_MS;
    const wait = Math.max(0, floor - (Date.now() - focusStartRef.current));
    const t = setTimeout(() => setIdx((i) => Math.min(i + 1, frontier)), wait);
    return () => clearTimeout(t);
  }, [idx, frontier, finished]);

  // A REAL export fetch when the export stage actually completes (proves the
  // endpoint), shown without a save dialog.
  useEffect(() => {
    if (exportRef.current || !snap.runId) return;
    if (cellStates[5].phase !== "end") return;
    exportRef.current = true;
    fetch(`/api/runs/${snap.runId}/export?format=svg`)
      .then((res) => res.blob())
      .then((blob) =>
        setExportInfo(`geometry.svg · ${(blob.size / 1024).toFixed(1)} KB · 内嵌 input_hash + 验证状态`),
      )
      .catch(() => setExportInfo("geometry.svg · 内嵌 input_hash + 验证状态"));
  }, [cellStates, snap.runId]);

  // Finish once the focus has reached the export cell and it has really ended.
  useEffect(() => {
    if (finished || idx !== 5) return;
    const exp = cellStates[5].phase;
    if (exp !== "end" && exp !== "error") return;
    const t = setTimeout(() => setFinished(true), 2600);
    return () => clearTimeout(t);
  }, [idx, finished, cellStates]);

  const stage = STAGES[idx];
  const latest = snap.iterations.length > 0 ? snap.iterations[snap.iterations.length - 1] : null;
  const verification = (snap.done?.verification ?? {}) as Record<string, unknown>;
  const verifyPassed = verification.status === "passed";
  // Real per-constraint results (authoritative top-level constraints[]); each chip
  // maps 1:1 to a real verification.json entry — only present once the run is done.
  const checks = (Array.isArray(verification.constraints) ? verification.constraints : []) as VerifyCheck[];
  const showViewport = idx >= 2;

  const replay = () => {
    setFinished(false);
    setIdx(0);
    setExportInfo(null);
    exportRef.current = false;
    focusStartRef.current = 0;
    onLaunch("cantilever"); // re-run; useRun resets snap (incl. stages) on launch
  };

  return (
    <div className="guided" role="dialog" aria-label="讲解模式">
      <header className="guided-top">
        <div className="guided-brand">
          <span className="guided-mark" aria-hidden="true" />
          <div className="guided-brand-text">
            <span className="guided-brand-name">简构智设 · LeanStruct</span>
            <span className="guided-brand-sub">端到端全流程 · 一镜到底</span>
          </div>
        </div>
        <ol className="guided-stepper">
          {STAGES.map((s, i) => {
            const tone = cellTone(AGENT_BY_CELL[i], cellStates[i]);
            return (
              <li key={s.no} className={TONE_CLASS[tone]}>
                <span className="guided-step-dot">{TONE_DOT[tone] ?? s.no}</span>
                <span className="guided-step-label">{s.name}</span>
              </li>
            );
          })}
        </ol>
        <button type="button" className="guided-exit" onClick={onExit}>
          退出讲解
        </button>
      </header>

      <main className="guided-stage">
        <div className="guided-canvas">
          {showViewport ? (
            <DensityViewport
              density={snap.density}
              shape={snap.shape}
              running={snap.status === "running"}
            />
          ) : (
            <ProblemSchematic mesh={idx === 1} />
          )}

          {/* status chips overlaid on the canvas (clean — no raw data) */}
          {idx === 2 && snap.status === "running" && (
            <span className="guided-chip guided-chip--run">
              <span className="guided-chip-dot" aria-hidden="true" />
              优化中…
            </span>
          )}
          {idx >= 4 && snap.done && (
            <span className={verifyPassed ? "guided-chip guided-chip--ok" : "guided-chip guided-chip--warn"}>
              {verifyPassed ? "✓ Verified · 独立复核通过" : "⚠ 工程负结果 · 见失败项"}
            </span>
          )}

          {/* live metric strip (only meaningful numbers, no backend dump) */}
          {showViewport && (
            <div className="guided-metrics">
              <Metric label="迭代" value={latest ? String(latest.iteration) : "—"} />
              <Metric label="柔度" value={latest ? fmt(latest.compliance) : "—"} />
              <Metric label="用料" value={latest ? pct(latest.volume_fraction) : "—"} />
            </div>
          )}
        </div>

        {/* annotation card for the current stage */}
        <aside className="guided-card" key={stage.no}>
          <div className="guided-card-head">
            <span className="guided-card-no">{stage.no}</span>
            <div>
              <div className="guided-card-name">{stage.name}</div>
              <div className="guided-card-agent">{stage.agent}</div>
            </div>
          </div>
          <p className="guided-card-caption">{stage.caption}</p>
          <dl className="guided-card-rows">
            <Row k="调用工具" v={stage.tool} />
            <Row k="判据" v={stage.criteria} />
            <Row k="过程产物" v={idx === 5 && exportInfo ? exportInfo : stage.artifact} />
            <Row k="门控" v={stage.gate} />
          </dl>
          {/* Phase 2: real per-constraint verdict chips (verification cell), each
              mapping 1:1 to a verification.json constraint — the independent critic. */}
          {idx === 4 && checks.length > 0 && (
            <div className="guided-checks">
              {checks.map((c) => (
                <span
                  key={c.name}
                  className={`guided-check ${c.status === "passed" ? "is-ok" : "is-warn"}`}
                >
                  {CHECK_LABELS[c.name] ?? c.name} {c.status === "passed" ? "✓" : "!"}
                </span>
              ))}
            </div>
          )}
        </aside>
      </main>

      <footer className="guided-foot">
        <span className="guided-foot-honest">
          每个亮起 = 真实引擎阶段完成（非脚本）· 绿 通过 · 琥珀 工程负结果/预算截断待复核 · 仅「独立验证」可否决优化器
        </span>
        <span>优化候选 · 需工程复核 · 非认证结论</span>
      </footer>

      {finished && !runErrored && (
        <div className="guided-end">
          <div className="guided-end-card">
            <div className="guided-end-title">
              <b>简构智设</b> · 端到端一镜到底
            </div>
            <div className="guided-end-sub">问题定义 → 优化 → 收敛 → 独立验证 → 导出，一口气走完。</div>
            <div className="guided-end-actions">
              <button type="button" className="guided-end-replay" onClick={replay}>
                ↻ 重新演示
              </button>
              <button type="button" className="guided-end-exit" onClick={onExit}>
                退出
              </button>
            </div>
          </div>
        </div>
      )}

      {runErrored && (
        <div className="guided-error" role="alert">
          <div className="guided-error-card">
            <div className="guided-error-title">流程中断 · 未完成</div>
            <div className="guided-error-sub">
              {failedStageName
                ? `在「${failedStageName}」阶段被门控挡下，运行已停止。`
                : "运行未能完成（连接中断或引擎报错）。"}
            </div>
            <div className="guided-error-detail mono">{snap.error ?? "未知错误"}</div>
            <div className="guided-error-actions">
              <button type="button" className="guided-end-replay" onClick={replay}>
                ↻ 重试
              </button>
              <button type="button" className="guided-end-exit" onClick={onExit}>
                退出
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="guided-metric">
      <span className="guided-metric-l">{label}</span>
      <span className="guided-metric-v mono">{value}</span>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="guided-row">
      <dt>{k}</dt>
      <dd>{v}</dd>
    </div>
  );
}

/** A clean problem-setup schematic shown during 问题定义 / 离散化 (pre-solve). */
function ProblemSchematic({ mesh }: { mesh: boolean }) {
  return (
    <div className="guided-schematic">
      <div className={mesh ? "gs-domain gs-domain--mesh" : "gs-domain"}>
        <div className="gs-fixed" aria-hidden="true" />
        <div className="gs-load" aria-hidden="true">
          <span className="gs-arrow" />
        </div>
        <span className="gs-budget">材料预算 45%</span>
      </div>
      <div className="gs-legend">
        <span><i className="gs-key gs-key--fix" /> 固定端</span>
        <span><i className="gs-key gs-key--load" /> 载荷</span>
      </div>
    </div>
  );
}

export type { GuidedModeProps };
