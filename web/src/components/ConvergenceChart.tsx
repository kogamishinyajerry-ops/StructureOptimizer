import { useMemo } from "react";
import type { IterationFrame } from "../api/types";
import { fmt } from "../lib/format";
import "./ConvergenceChart.css";

interface ConvergenceChartProps {
  iterations: IterationFrame[];
}

// viewBox coordinate space — SVG scales responsively to its container.
const VIEW_W = 320;
const VIEW_H = 160;
const PAD_L = 8;
const PAD_R = 8;
const PAD_T = 10;
const PAD_B = 16;
const PLOT_W = VIEW_W - PAD_L - PAD_R;
const PLOT_H = VIEW_H - PAD_T - PAD_B;

interface ChartGeometry {
  compliancePath: string;
  complianceArea: string;
  volumePath: string;
  latest: { x: number; y: number };
  startIter: number;
  endIter: number;
  complianceMin: number;
  complianceMax: number;
}

function buildGeometry(iterations: IterationFrame[]): ChartGeometry | null {
  if (iterations.length === 0) return null;

  const startIter = iterations[0].iteration;
  const endIter = iterations[iterations.length - 1].iteration;
  const iterSpan = Math.max(1, endIter - startIter);

  // Guard compliance <= 0 before taking logs (orders-of-magnitude drop).
  const safe = iterations.map((it) => Math.max(it.compliance, 1e-12));
  let logMin = Infinity;
  let logMax = -Infinity;
  for (const c of safe) {
    const l = Math.log10(c);
    if (l < logMin) logMin = l;
    if (l > logMax) logMax = l;
  }
  const logSpan = Math.max(1e-9, logMax - logMin);

  const xAt = (iter: number): number =>
    PAD_L + ((iter - startIter) / iterSpan) * PLOT_W;
  // Log Y: highest compliance at top, lowest at bottom.
  const yComp = (c: number): number => {
    const t = (Math.log10(c) - logMin) / logSpan;
    return PAD_T + (1 - t) * PLOT_H;
  };
  // Linear Y for volume fraction across fixed 0..1 domain.
  const yVol = (v: number): number =>
    PAD_T + (1 - Math.min(1, Math.max(0, v))) * PLOT_H;

  let compliancePath = "";
  let volumePath = "";
  iterations.forEach((it, i) => {
    const x = xAt(it.iteration);
    const cmd = i === 0 ? "M" : "L";
    compliancePath += `${cmd}${x.toFixed(2)} ${yComp(safe[i]).toFixed(2)} `;
    volumePath += `${cmd}${x.toFixed(2)} ${yVol(it.volume_fraction).toFixed(2)} `;
  });
  compliancePath = compliancePath.trim();
  volumePath = volumePath.trim();

  const firstX = xAt(startIter);
  const lastX = xAt(endIter);
  const baseY = PAD_T + PLOT_H;
  const complianceArea = `${compliancePath} L${lastX.toFixed(2)} ${baseY.toFixed(
    2
  )} L${firstX.toFixed(2)} ${baseY.toFixed(2)} Z`;

  const lastIt = iterations[iterations.length - 1];
  return {
    compliancePath,
    complianceArea,
    volumePath,
    latest: { x: lastX, y: yComp(Math.max(lastIt.compliance, 1e-12)) },
    startIter,
    endIter,
    complianceMin: Math.pow(10, logMin),
    complianceMax: Math.pow(10, logMax),
  };
}

export function ConvergenceChart({ iterations }: ConvergenceChartProps) {
  const geo = useMemo(() => buildGeometry(iterations), [iterations]);

  // Faint gridlines at quartiles of the plot height.
  const gridY = useMemo(
    () => [0.25, 0.5, 0.75].map((t) => PAD_T + t * PLOT_H),
    []
  );
  const baseY = PAD_T + PLOT_H;

  return (
    <div className="convergence">
      <div className="convergence__label">Convergence</div>
      {geo === null ? (
        <div className="convergence__empty">Awaiting first iteration…</div>
      ) : (
        <div className="convergence__plot">
          <svg
            className="convergence__svg"
            viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
            preserveAspectRatio="none"
            role="img"
            aria-label="Compliance convergence over iterations"
          >
            {gridY.map((y) => (
              <line
                key={y}
                className="convergence__grid"
                x1={PAD_L}
                y1={y}
                x2={VIEW_W - PAD_R}
                y2={y}
              />
            ))}
            <line
              className="convergence__base"
              x1={PAD_L}
              y1={baseY}
              x2={VIEW_W - PAD_R}
              y2={baseY}
            />
            <path className="convergence__area" d={geo.complianceArea} />
            <path className="convergence__volume" d={geo.volumePath} />
            <path className="convergence__line" d={geo.compliancePath} />
            <circle
              className="convergence__dot"
              cx={geo.latest.x}
              cy={geo.latest.y}
              r={2.6}
            />
          </svg>
          <div className="convergence__axis">
            <span className="mono convergence__tick">{geo.startIter}</span>
            <span className="mono convergence__range">
              {fmt(geo.complianceMin, 3)} – {fmt(geo.complianceMax, 3)}
            </span>
            <span className="mono convergence__tick">{geo.endIter}</span>
          </div>
        </div>
      )}
    </div>
  );
}
