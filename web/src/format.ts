/** Show a probability as given; never turn it into "significant" language. */
export function fmtP(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "n/a";
  if (value < 0.001) return "< 0.001";
  return value.toFixed(3);
}

export function fmtEffect(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "n/a";
  return value.toFixed(2);
}

export function fmtNum(value: number): string {
  if (!Number.isFinite(value)) return "n/a";
  const abs = Math.abs(value);
  if (abs !== 0 && (abs >= 10000 || abs < 0.01)) return value.toExponential(1);
  if (abs >= 100) return value.toFixed(0);
  if (abs >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

/** Format axis ticks with just enough decimals for their spacing. */
export function tickFormatter(ticks: number[]): (value: number) => string {
  const step = ticks.length > 1 ? Math.abs(ticks[1] - ticks[0]) : 1;
  const decimals = step >= 1 ? 0 : Math.min(4, Math.ceil(-Math.log10(step)));
  return (value) => value.toLocaleString("en-US", { maximumFractionDigits: decimals, minimumFractionDigits: decimals });
}

export function fmtInt(value: number | null): string {
  return value === null ? "n/a" : value.toLocaleString("en-US");
}

const METRIC_SYMBOL: Record<string, string> = {
  spearman_rho: "rho",
  kendall_tau_b: "tau-b",
  cliffs_delta: "delta",
  epsilon_squared: "eps2",
  cramers_v: "V",
  relative_change: "change",
  mase_reduction: "error reduction",
};

export function metricSymbol(metric: string | null): string {
  return metric ? (METRIC_SYMBOL[metric] ?? metric) : "effect";
}

export function claimTypeLabel(kind: string): string {
  return kind.replace(/_/g, " ").toUpperCase();
}

export function niceTicks(lo: number, hi: number, count = 5): number[] {
  if (!(hi > lo)) return [lo];
  const raw = (hi - lo) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
  const ticks: number[] = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi + step * 1e-9; t += step) {
    ticks.push(Number(t.toPrecision(12)));
  }
  return ticks;
}

export function elapsed(from: string, to?: string | null): string {
  const seconds = Math.max(0, Math.round(((to ? Date.parse(to) : Date.now()) - Date.parse(from)) / 1000));
  const m = String(Math.floor(seconds / 60)).padStart(2, "0");
  const s = String(seconds % 60).padStart(2, "0");
  return `${m}:${s}`;
}
