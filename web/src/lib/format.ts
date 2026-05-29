// Number formatting shared across readouts. Engineering-friendly: 4 sig figs,
// scientific notation only for very large / very small magnitudes.

export function fmt(value: number | null | undefined, digits = 4): string {
  if (value == null || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  if (abs !== 0 && (abs >= 1e5 || abs < 1e-3)) {
    return value.toExponential(2);
  }
  return Number(value.toPrecision(digits)).toString();
}

export function pct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}
