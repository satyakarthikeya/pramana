import { useId, useState } from "react";
import type { ChartSpec, ColumnOverview, DataOverview, GroupsChart, ScatterChart } from "../api";
import { fmtInt, fmtNum, niceTicks, tickFormatter } from "../format";

const W = 560;
const PAD = { l: 52, r: 12, t: 10, b: 40 };

interface Palette {
  main: string;
  second: string;
}
export const verifiedPalette: Palette = { main: "#0F5C58", second: "#C47A1E" };
export const neutralPalette: Palette = { main: "#6B6458", second: "#9A9488" };

function scale(domain: [number, number], range: [number, number]) {
  const [d0, d1] = domain;
  const span = d1 - d0 || 1;
  return (v: number) => range[0] + ((v - d0) / span) * (range[1] - range[0]);
}

function extent(values: number[]): [number, number] {
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  if (lo === hi) {
    lo -= 1;
    hi += 1;
  }
  const pad = (hi - lo) * 0.04;
  return [lo - pad, hi + pad];
}

function Frame({
  title,
  label,
  takeaway,
  children,
  footer,
  table,
  inset,
}: {
  title: string;
  label: string;
  takeaway?: string;
  children: React.ReactNode;
  footer: string;
  table?: React.ReactNode;
  inset?: boolean;
}) {
  const [showTable, setShowTable] = useState(false);
  return (
    <figure className={`chart${inset ? " inset" : ""}`} style={{ margin: 0 }}>
      <div className="chart-head">
        <span className="chip">{label}</span>
        <figcaption className="chart-title">{title}</figcaption>
      </div>
      {takeaway && <p className="takeaway">{takeaway}</p>}
      {showTable && table ? table : children}
      <div className="chart-foot">
        <span>{footer}</span>
        {table && (
          <button
            type="button"
            className="tbl-toggle"
            aria-pressed={showTable}
            onClick={() => setShowTable((v) => !v)}
          >
            {showTable ? "Chart view" : "Table view"}
          </button>
        )}
      </div>
    </figure>
  );
}

function Scatter({
  chart,
  palette,
  inset,
}: {
  chart: ScatterChart;
  palette: Palette;
  inset?: boolean;
}) {
  const H = 300;
  const xs = chart.points.map((p) => p[0]);
  const ys = chart.points.map((p) => p[1]);
  const xd = extent(xs);
  const yd = extent(ys);
  const sx = scale(xd, [PAD.l, W - PAD.r]);
  const sy = scale(yd, [H - PAD.b, PAD.t]);
  const xt = niceTicks(xd[0], xd[1], 5);
  const yt = niceTicks(yd[0], yd[1], 5);
  const fx = tickFormatter(xt);
  const fy = tickFormatter(yt);
  const desc = `Scatter of ${chart.y} against ${chart.x}, ${fmtInt(chart.n)} rows`;
  return (
    <Frame
      inset={inset}
      label="SCATTER + FIT"
      title={`${chart.y} by ${chart.x}`}
      takeaway="Each point is one row. The line is a least-squares fit, drawn to show the direction only. It is not part of the test."
      footer={
        chart.shown < chart.n
          ? `n = ${fmtInt(chart.n)} rows, ${fmtInt(chart.shown)} points drawn`
          : `n = ${fmtInt(chart.n)} rows`
      }
      table={
        <table className="data-table">
          <thead>
            <tr>
              <th>{chart.x}</th>
              <th>{chart.y}</th>
            </tr>
          </thead>
          <tbody>
            {chart.points.slice(0, 12).map(([a, b], i) => (
              <tr key={i}>
                <td>{fmtNum(a)}</td>
                <td>{fmtNum(b)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={desc}>
        {yt.map((t) => (
          <g key={`y${t}`}>
            <line x1={PAD.l} x2={W - PAD.r} y1={sy(t)} y2={sy(t)} stroke="#E4DDD1" />
            <text x={PAD.l - 8} y={sy(t) + 4} textAnchor="end">
              {fy(t)}
            </text>
          </g>
        ))}
        {xt.map((t) => (
          <text key={`x${t}`} x={sx(t)} y={H - PAD.b + 16} textAnchor="middle">
            {fx(t)}
          </text>
        ))}
        <line x1={PAD.l} x2={W - PAD.r} y1={H - PAD.b} y2={H - PAD.b} stroke="#BFB5A5" />
        {chart.points.map(([a, b], i) => (
          <circle key={i} cx={sx(a)} cy={sy(b)} r={3} fill={palette.main} fillOpacity={0.45} />
        ))}
        {chart.fit.length === 2 && (
          <line
            x1={sx(chart.fit[0][0])}
            y1={sy(chart.fit[0][1])}
            x2={sx(chart.fit[1][0])}
            y2={sy(chart.fit[1][1])}
            stroke="#1F1C17"
            strokeWidth={1.75}
          />
        )}
        <text className="axis-title" x={(PAD.l + W - PAD.r) / 2} y={H - 6} textAnchor="middle">
          {chart.x}
        </text>
        <text
          className="axis-title"
          transform={`translate(12 ${(PAD.t + H - PAD.b) / 2}) rotate(-90)`}
          textAnchor="middle"
        >
          {chart.y}
        </text>
      </svg>
    </Frame>
  );
}

function Groups({
  chart,
  palette,
  inset,
}: {
  chart: GroupsChart;
  palette: Palette;
  inset?: boolean;
}) {
  const rowH = 52;
  const H = PAD.t + chart.groups.length * rowH + PAD.b;
  const all = chart.groups.flatMap((g) => [g.minimum, g.maximum]);
  const xd = extent(all);
  const sx = scale(xd, [PAD.l + 36, W - PAD.r]);
  const xt = niceTicks(xd[0], xd[1], 5);
  const fx = tickFormatter(xt);
  const desc = `Spread of ${chart.value} across ${chart.groups.length} ${chart.group} groups`;
  return (
    <Frame
      inset={inset}
      label="GROUP COMPARISON"
      title={`${chart.value} by ${chart.group}`}
      takeaway="Box shows the middle half of each group with its median. Dots are individual rows."
      footer={`n = ${fmtInt(chart.n)} rows in ${chart.groups.length} groups`}
      table={
        <table className="data-table">
          <thead>
            <tr>
              <th>{chart.group}</th>
              <th>n</th>
              <th>q1</th>
              <th>median</th>
              <th>q3</th>
            </tr>
          </thead>
          <tbody>
            {chart.groups.map((g) => (
              <tr key={g.label}>
                <td>{g.label}</td>
                <td>{fmtInt(g.n)}</td>
                <td>{fmtNum(g.q1)}</td>
                <td>{fmtNum(g.median)}</td>
                <td>{fmtNum(g.q3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={desc}>
        {xt.map((t) => (
          <g key={t}>
            <line x1={sx(t)} x2={sx(t)} y1={PAD.t} y2={H - PAD.b} stroke="#E4DDD1" />
            <text x={sx(t)} y={H - PAD.b + 16} textAnchor="middle">
              {fx(t)}
            </text>
          </g>
        ))}
        {chart.groups.map((g, i) => {
          const cy = PAD.t + i * rowH + rowH / 2;
          const color = i === 0 ? palette.main : i === 1 ? palette.second : "#6B6458";
          return (
            <g key={g.label}>
              <text x={PAD.l + 28} y={cy + 4} textAnchor="end" style={{ fill: "#4A443A" }}>
                {g.label.length > 8 ? `${g.label.slice(0, 7)}…` : g.label}
              </text>
              {g.points.map((v, k) => (
                <circle
                  key={k}
                  cx={sx(v)}
                  cy={cy + (((k * 37) % 17) - 8) * 1.1}
                  r={2.4}
                  fill={color}
                  fillOpacity={0.4}
                />
              ))}
              <line
                x1={sx(g.minimum)}
                x2={sx(g.maximum)}
                y1={cy}
                y2={cy}
                stroke={color}
                strokeWidth={1}
              />
              <rect
                x={sx(g.q1)}
                y={cy - 10}
                width={Math.max(2, sx(g.q3) - sx(g.q1))}
                height={20}
                fill="none"
                stroke={color}
                strokeWidth={1.75}
                rx={3}
              />
              <line x1={sx(g.median)} x2={sx(g.median)} y1={cy - 10} y2={cy + 10} stroke="#1F1C17" strokeWidth={2.5} />
            </g>
          );
        })}
        <text className="axis-title" x={(PAD.l + 36 + W - PAD.r) / 2} y={H - 6} textAnchor="middle">
          {chart.value}
        </text>
      </svg>
    </Frame>
  );
}

export function ClaimChart({
  chart,
  verified,
  inset,
}: {
  chart: ChartSpec;
  verified: boolean;
  inset?: boolean;
}) {
  const palette = verified ? verifiedPalette : neutralPalette;
  return chart.kind === "scatter" ? (
    <Scatter chart={chart} palette={palette} inset={inset} />
  ) : (
    <Groups chart={chart} palette={palette} inset={inset} />
  );
}

function Histogram({ column }: { column: ColumnOverview }) {
  const H = 64;
  const max = Math.max(...column.bins.map((b) => b.count), 1);
  const w = 280;
  const bw = w / column.bins.length;
  return (
    <svg viewBox={`0 0 ${w} ${H}`} role="img" aria-label={`Distribution of ${column.name}`}>
      {column.bins.map((b, i) => (
        <rect
          key={i}
          x={i * bw + 1}
          y={H - (b.count / max) * (H - 4)}
          width={bw - 2}
          height={(b.count / max) * (H - 4)}
          rx={2}
          fill="#0F5C58"
          fillOpacity={0.75}
        />
      ))}
      <line x1={0} x2={w} y1={H} y2={H} stroke="#BFB5A5" />
    </svg>
  );
}

function CategoryBars({ column }: { column: ColumnOverview }) {
  const max = Math.max(...column.top.map((t) => t.count), 1);
  return (
    <div style={{ display: "grid", gap: 4 }}>
      {column.top.map((t) => (
        <div
          key={t.label}
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 96px) minmax(24px, 1fr) auto",
            gap: 8,
            alignItems: "center",
          }}
        >
          <span className="meta mono" style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
            {t.label}
          </span>
          <span
            style={{
              height: 10,
              borderRadius: 999,
              background: "#0F5C58",
              opacity: 0.75,
              width: `${Math.max(2, (t.count / max) * 100)}%`,
            }}
          />
          <span className="meta mono" style={{ textAlign: "right" }}>
            {fmtInt(t.count)}
          </span>
        </div>
      ))}
    </div>
  );
}

const DIVERGING = ["#B3411B", "#E3A58E", "#F3EFE8", "#7FB8AE", "#0F5C58"];

function heat(value: number | null): string {
  if (value === null) return "#EAE4DA";
  const idx = Math.min(4, Math.max(0, Math.round(((value + 1) / 2) * 4)));
  return DIVERGING[idx];
}

function Heatmap({ matrix }: { matrix: NonNullable<DataOverview["correlations"]> }) {
  const n = matrix.columns.length;
  const cell = Math.min(44, Math.floor(420 / n));
  const lab = 96;
  const size = lab + n * cell;
  return (
    <svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Rank correlations between numeric columns">
      {matrix.columns.map((name, i) => (
        <g key={name}>
          <text x={lab - 6} y={lab + i * cell + cell / 2 + 4} textAnchor="end">
            {name.length > 11 ? `${name.slice(0, 10)}…` : name}
          </text>
          <text
            transform={`translate(${lab + i * cell + cell / 2 + 4} ${lab - 6}) rotate(-90)`}
            textAnchor="start"
          >
            {name.length > 11 ? `${name.slice(0, 10)}…` : name}
          </text>
        </g>
      ))}
      {matrix.values.map((row, r) =>
        row.map((v, c) => (
          <g key={`${r}-${c}`}>
            <rect
              x={lab + c * cell}
              y={lab + r * cell}
              width={cell - 2}
              height={cell - 2}
              rx={4}
              fill={heat(v)}
            />
            {cell >= 30 && (
              <text
                x={lab + c * cell + (cell - 2) / 2}
                y={lab + r * cell + (cell - 2) / 2 + 4}
                textAnchor="middle"
                style={{ fill: v !== null && Math.abs(v) > 0.6 ? "#FBF9F5" : "#1F1C17" }}
              >
                {v === null ? "–" : v.toFixed(2)}
              </text>
            )}
          </g>
        )),
      )}
    </svg>
  );
}

export function Overview({ overview }: { overview: DataOverview }) {
  const id = useId();
  return (
    <div className="overview" aria-labelledby={id}>
      <div className="chart">
        <div className="chart-head">
          <span className="chip">YOUR DATA</span>
          <span className="chart-title" id={id}>
            What each analysable column looks like
          </span>
        </div>
        <p className="takeaway">
          Descriptive only. These pictures describe your table and are not tested claims.
        </p>
        <div>
          {overview.columns.map((c) => (
            <div className="col-row" key={c.name}>
              <div>
                <div className="nm">{c.name}</div>
                <div className="meta">
                  {c.kind === "numeric"
                    ? `median ${fmtNum(c.median ?? 0)} · n ${fmtInt(c.n)}`
                    : `${c.top.length} most common · n ${fmtInt(c.n)}`}
                  {c.missing > 0 ? ` · ${fmtInt(c.missing)} missing` : ""}
                </div>
              </div>
              {c.kind === "numeric" ? <Histogram column={c} /> : <CategoryBars column={c} />}
            </div>
          ))}
        </div>
      </div>
      {overview.correlations && (
        <div className="chart">
          <div className="chart-head">
            <span className="chip">CORRELATIONS</span>
            <span className="chart-title">How the numeric columns move together</span>
          </div>
          <p className="takeaway">
            Spearman rank correlation between every pair, for orientation. Only pairs that were
            proposed and tested can become findings.
          </p>
          <Heatmap matrix={overview.correlations} />
          <div className="chart-foot">
            <span>n = {fmtInt(overview.rows)} rows</span>
            <span>-1 (opposite) to +1 (together)</span>
          </div>
        </div>
      )}
    </div>
  );
}
