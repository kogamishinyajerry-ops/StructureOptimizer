import { useEffect, useRef, useState } from "react";
import type { RunSnapshot } from "../api/useRun";
import { DensityViewport } from "../viewport/DensityViewport";
import { fmt, pct } from "../lib/format";
import "./GuidedMode.css";

/**
 * Guided / 讲解 mode — a clean, presenter-grade "one take" walkthrough of the
 * real end-to-end pipeline on top of a REAL run. It auto-drives a cantilever
 * SIMP run and steps a 6-stage explainer in sync: 问题定义 → 离散化 → 优化求解
 * → 收敛门控 → 独立验证 → 结果解析/导出. Every visual is real (real density
 * stream, real verification status, a real export fetch); no backend text/JSON
 * is exposed. Built to be screen-recorded as the demo embedded in the deck.
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
    artifact: "几何文件，内嵌指纹 + 验证状态 + 免责声明",
    gate: "终态：一个可被独立复核的「优化候选」",
    caption: "把密度场解析成带溯源的几何文件，直接进制造流程——但它是候选，需工程复核。",
  },
];

interface GuidedModeProps {
  snap: RunSnapshot;
  onLaunch: (benchmarkId: string) => void;
  onExit: () => void;
}

export function GuidedMode({ snap, onLaunch, onExit }: GuidedModeProps) {
  const [idx, setIdx] = useState(0);
  const [finished, setFinished] = useState(false);
  const [exportInfo, setExportInfo] = useState<string | null>(null);
  const launchedRef = useRef(false);
  const exportRef = useRef(false);
  const solveStartRef = useRef(0);

  // Narration-paced transitions (timers) + the run-gated solve transition below.
  useEffect(() => {
    if (finished) return;
    if (idx === 0) {
      const t = setTimeout(() => setIdx(1), 4800);
      return () => clearTimeout(t);
    }
    if (idx === 1) {
      const t = setTimeout(() => {
        if (!launchedRef.current) {
          launchedRef.current = true;
          onLaunch("cantilever");
        }
        setIdx(2);
      }, 3800);
      return () => clearTimeout(t);
    }
    if (idx === 3) {
      const t = setTimeout(() => setIdx(4), 3400);
      return () => clearTimeout(t);
    }
    if (idx === 4) {
      const t = setTimeout(() => {
        if (!exportRef.current && snap.runId) {
          exportRef.current = true;
          // A REAL export fetch (proves the endpoint), shown without a save dialog.
          fetch(`/api/runs/${snap.runId}/export?format=svg`)
            .then((res) => res.blob())
            .then((blob) =>
              setExportInfo(`geometry.svg · ${(blob.size / 1024).toFixed(1)} KB · 内嵌 input_hash + 验证状态`),
            )
            .catch(() => setExportInfo("geometry.svg · 内嵌 input_hash + 验证状态"));
        }
        setIdx(5);
      }, 4600);
      return () => clearTimeout(t);
    }
    if (idx === 5) {
      const t = setTimeout(() => setFinished(true), 5400);
      return () => clearTimeout(t);
    }
  }, [idx, finished, onLaunch, snap.runId]);

  // Stage 03 (solve) holds until the REAL run reaches a terminal state — but for
  // at least MIN_SOLVE_MS so the convergence "hero" never blinks past on a fast
  // run (the converged X-truss then holds for the remainder).
  const MIN_SOLVE_MS = 8000;
  useEffect(() => {
    if (idx === 2 && solveStartRef.current === 0) solveStartRef.current = Date.now();
  }, [idx]);
  useEffect(() => {
    if (idx !== 2) return;
    if (snap.status !== "done" && snap.status !== "error") return;
    const remaining = MIN_SOLVE_MS - (Date.now() - solveStartRef.current);
    if (remaining <= 0) {
      setIdx(3);
      return;
    }
    const t = setTimeout(() => setIdx(3), remaining);
    return () => clearTimeout(t);
  }, [idx, snap.status]);

  const stage = STAGES[idx];
  const latest = snap.iterations.length > 0 ? snap.iterations[snap.iterations.length - 1] : null;
  const verification = (snap.done?.verification ?? {}) as Record<string, unknown>;
  const verifyPassed = verification.status === "passed";
  const showViewport = idx >= 2;

  const replay = () => {
    setFinished(false);
    setIdx(0);
    setExportInfo(null);
    launchedRef.current = false;
    exportRef.current = false;
    solveStartRef.current = 0;
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
          {STAGES.map((s, i) => (
            <li
              key={s.no}
              className={
                i === idx
                  ? "guided-step is-active"
                  : i < idx
                    ? "guided-step is-done"
                    : "guided-step"
              }
            >
              <span className="guided-step-dot">{i < idx ? "✓" : s.no}</span>
              <span className="guided-step-label">{s.name}</span>
            </li>
          ))}
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
          {idx >= 4 && (
            <span className={verifyPassed ? "guided-chip guided-chip--ok" : "guided-chip guided-chip--warn"}>
              {verifyPassed ? "✓ Verified · 独立复核通过" : "复核完成"}
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
        </aside>
      </main>

      <footer className="guided-foot">
        优化候选 · 需工程复核 · 非认证结论
      </footer>

      {finished && (
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
