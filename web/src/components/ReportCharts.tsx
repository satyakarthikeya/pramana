import { useState } from "react";
import type { ExactChart, ExactItem } from "../api";
import { fmtInt, fmtNum, niceTicks, tickFormatter } from "../format";

const W = 560;
const H = 220;
const PAD = { l: 56, r: 12, t: 12, b: 44 };
const TEAL = "#0F5C58";
const AMBER = "#C47A1E";
const GREY = "#BFB5A5";
const SEQUENTIAL = ["#E3EFEC", "#B5D6CF", "#7FB8AE", "#3F8C84", "#0F5C58"];

function yScale(lo: number, hi: number) {
  const ticks = niceTicks(lo, hi, 4);
  const d0 = Math.min(lo, ticks[0]);
  const d1 = Math.max(hi, ticks[ticks.length - 1]);
  const span = d1 - d0 || 1;
  const y = (v: number) => PAD.t + (1 - (v - d0) / span) * (H - PAD.t - PAD.b);
  return { y, ticks, fmt: tickFormatter(ticks) };
}

function Axes({ ticks, y, fmt, label }: { ticks: number[]; y: (v: number) => number; fmt: (v: number) => string; label: string }) {
  return (
    <g className="axis">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} stroke="#E4DDD1" />
          <text x={PAD.l - 6} y={y(t) + 4} textAnchor="end">
            {fmt(t)}
          </text>
        </g>
      ))}
      <text transform={`translate(12 ${H / 2}) rotate(-90)`} textAnchor="middle">
        {label}
      </text>
    </g>
  );
}

function every(n: number): number {
  return Math.max(1, Math.ceil(n / 8));
}

function Line({ chart }: { chart: Extract<ExactChart, { kind: "line" }> }) {
  const values = chart.points.map((p) => p[1]);
  const { y, ticks, fmt } = yScale(Math.min(...values, 0), Math.max(...values));
  const step = (W - PAD.l - PAD.r) / Math.max(1, chart.points.length - 1);
  const x = (i: number) => PAD.l + i * step;
  const marks = new Set(chart.marks);
  const path = chart.points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p[1])}`).join(" ");
  const k = every(chart.points.length);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${chart.y_label} by ${chart.x_label}, ${chart.points.length} points`}>
      <Axes ticks={ticks} y={y} fmt={fmt} label={chart.y_label} />
      <path d={path} fill="none" stroke={TEAL} strokeWidth={2} />
      {chart.points.map((p, i) => (
        <g key={p[0]}>
          {marks.has(p[0]) ? (
            <rect x={x(i) - 5} y={y(p[1]) - 5} width={10} height={10} fill={AMBER} />
          ) : (
            chart.points.length <= 40 && <circle cx={x(i)} cy={y(p[1])} r={3} fill={TEAL} />
          )}
          {i % k === 0 && (
            <text className="axis" x={x(i)} y={H - PAD.b + 16} textAnchor="middle">
              {p[0]}
            </text>
          )}
        </g>
      ))}
    </svg>
  );
}

function Bars({ chart }: { chart: Extract<ExactChart, { kind: "bar" }> }) {
  const pct = chart.value_format === "percent";
  const max = Math.max(...chart.bars.map((b) => b.value), 0) || 1;
  return (
    <div className="hbars" role="img" aria-label={`${chart.y_label} by ${chart.x_label}`}>
      {chart.bars.map((b) => (
        <div className="hbar" key={b.label}>
          <span className="mono hbar-label">{b.label}</span>
          <span className="hbar-track">
            <span className="hbar-fill" style={{ width: `${Math.max(1, (b.value / max) * 100)}%` }} />
          </span>
          <span className="mono hbar-value">
            {pct ? `${(b.value * 100).toFixed(1)}%` : fmtNum(b.value)}
            {b.n !== null && b.n !== undefined ? ` · n ${fmtInt(b.n)}` : ""}
          </span>
        </div>
      ))}
    </div>
  );
}

function Waterfall({ chart }: { chart: Extract<ExactChart, { kind: "waterfall" }> }) {
  let running = chart.start;
  const bars = [
    { label: chart.start_label, from: 0, to: chart.start, total: true },
    ...chart.steps.map((s) => {
      const from = running;
      running += s.value;
      return { label: s.label, from, to: running, total: false };
    }),
    { label: chart.end_label, from: 0, to: chart.end, total: true },
  ];
  const lo = Math.min(...bars.map((b) => Math.min(b.from, b.to)));
  const hi = Math.max(...bars.map((b) => Math.max(b.from, b.to)));
  const { y, ticks, fmt } = yScale(Math.min(lo, 0), hi);
  const slot = (W - PAD.l - PAD.r) / bars.length;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Change in ${chart.y_label} by segment, from ${chart.start_label} to ${chart.end_label}`}>
      <Axes ticks={ticks} y={y} fmt={fmt} label={chart.y_label} />
      {bars.map((b, i) => {
        const top = y(Math.max(b.from, b.to));
        const height = Math.max(1, Math.abs(y(b.from) - y(b.to)));
        const fill = b.total ? GREY : b.to >= b.from ? TEAL : AMBER;
        return (
          <g key={`${b.label}-${i}`}>
            <rect x={PAD.l + i * slot + 6} y={top} width={slot - 12} height={height} rx={2} fill={fill} />
            <text className="axis" x={PAD.l + i * slot + slot / 2} y={H - PAD.b + 16} textAnchor="middle">
              {b.label.length > 10 ? `${b.label.slice(0, 9)}…` : b.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function Pareto({ chart }: { chart: Extract<ExactChart, { kind: "pareto" }> }) {
  const max = Math.max(...chart.bars.map((b) => b.value), 0) || 1;
  const { y, ticks, fmt } = yScale(0, max);
  const slot = (W - PAD.l - PAD.r) / chart.bars.length;
  const share = (s: number) => PAD.t + (1 - s) * (H - PAD.t - PAD.b);
  const path = chart.bars
    .map((b, i) => `${i ? "L" : "M"}${PAD.l + i * slot + slot / 2},${share(b.cumulative_share)}`)
    .join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${chart.y_label} by segment, largest first, with cumulative share`}>
      <Axes ticks={ticks} y={y} fmt={fmt} label={chart.y_label} />
      {chart.bars.map((b, i) => (
        <g key={b.label}>
          <rect x={PAD.l + i * slot + 6} y={y(b.value)} width={slot - 12} height={Math.max(1, y(0) - y(b.value))} rx={2} fill={TEAL} fillOpacity={0.8} />
          <text className="axis" x={PAD.l + i * slot + slot / 2} y={H - PAD.b + 16} textAnchor="middle">
            {b.label.length > 10 ? `${b.label.slice(0, 9)}…` : b.label}
          </text>
        </g>
      ))}
      <path d={path} fill="none" stroke={AMBER} strokeWidth={2} strokeDasharray="5 3" />
      <text className="axis" x={W - PAD.r} y={share(1) - 2} textAnchor="end">
        cumulative share 100%
      </text>
    </svg>
  );
}

function HeatStripView({ chart }: { chart: Extract<ExactChart, { kind: "heat_strip" }> }) {
  const lo = Math.min(...chart.cells.map((c) => c.index));
  const hi = Math.max(...chart.cells.map((c) => c.index));
  const shade = (v: number) => SEQUENTIAL[Math.round(((v - lo) / (hi - lo || 1)) * 4)];
  return (
    <div className="heat-strip" role="img" aria-label={`Seasonal index of ${chart.label} by period of the year`}>
      {chart.cells.map((c) => (
        <div className="heat-cell" key={c.label} title={`${c.label}: ${c.index.toFixed(2)}`}>
          <span className="heat-swatch" style={{ background: shade(c.index) }} />
          <span className="mono">{c.label.slice(0, 3)}</span>
          <span className="mono">{c.index.toFixed(2)}</span>
        </div>
      ))}
    </div>
  );
}

function rows(chart: ExactChart): [string, string][] {
  switch (chart.kind) {
    case "line":
      return chart.points.map(([x, v]) => [x, fmtNum(v)]);
    case "bar":
      return chart.bars.map((b) => [b.label, chart.value_format === "percent" ? `${(b.value * 100).toFixed(1)}%` : fmtNum(b.value)]);
    case "waterfall":
      return [[chart.start_label, fmtNum(chart.start)], ...chart.steps.map((s): [string, string] => [s.label, fmtNum(s.value)]), [chart.end_label, fmtNum(chart.end)]];
    case "pareto":
      return chart.bars.map((b) => [b.label, `${fmtNum(b.value)} · ${(b.cumulative_share * 100).toFixed(1)}% cumulative`]);
    case "heat_strip":
      return chart.cells.map((c) => [c.label, c.index.toFixed(2)]);
  }
}

/** The figure's chart, drawn from the series code computed, with a table view. */
export function ExactChartView({ item }: { item: ExactItem }) {
  const [table, setTable] = useState(false);
  const chart = item.chart;
  if (!chart) return null;
  return (
    <figure className="chart inset" style={{ margin: "12px 0 0" }}>
      {table ? (
        <table className="data-table">
          <tbody>
            {rows(chart).map(([k, v]) => (
              <tr key={k}>
                <td>{k}</td>
                <td>{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : chart.kind === "line" ? (
        <Line chart={chart} />
      ) : chart.kind === "bar" ? (
        <Bars chart={chart} />
      ) : chart.kind === "waterfall" ? (
        <Waterfall chart={chart} />
      ) : chart.kind === "pareto" ? (
        <Pareto chart={chart} />
      ) : (
        <HeatStripView chart={chart} />
      )}
      <div className="chart-foot">
        <span>n = {fmtInt(item.n_rows)} rows</span>
        <button type="button" className="tbl-toggle" aria-pressed={table} onClick={() => setTable((v) => !v)}>
          {table ? "Chart view" : "Table view"}
        </button>
      </div>
    </figure>
  );
}
