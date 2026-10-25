export type RunStatus = "pending" | "running" | "completed" | "degraded" | "failed";

export interface ColumnPreview {
  name: string;
  role: string;
  usable: boolean;
  reasons: string[];
}
export interface DataPreview {
  rows: number;
  columns: number;
  detected_columns: ColumnPreview[];
  sample_rows: Record<string, string>[];
  omitted_columns: number;
}
export interface Lesson {
  record_id: string;
  run_id: string;
  dataset_ref: string;
  text: string;
  stored_at: string;
  candidate: { claim: string; variables: string[]; claim_type: string };
  proof: Proof;
}
export interface RetrievedLesson {
  lesson: Lesson;
  similarity: number;
}
export interface RunView {
  run_id: string;
  dataset_id: string | null;
  status: RunStatus;
  file_name: string;
  created_at: string;
  finished_at: string | null;
  error: string | null;
  progress: string;
  preview: DataPreview | null;
  past_lessons: RetrievedLesson[];
}
export type GateOutcome =
  | "supported"
  | "refuted"
  | "negligible"
  | "inconclusive"
  | "not_testable"
  | "fragile";
export type PermutationScheme =
  | "free"
  | "block_differenced"
  | "stratified"
  | "cluster"
  | "paired"
  | "block_sign_flip";
export interface SplitRecord {
  method: "random_rows" | "by_time" | "by_entity" | "none";
  seed: number;
  confirmation_fraction: number;
  n_exploration: number;
  n_confirmation: number;
  confirmation_digest: string;
  /** Other runs that already tested on these held-back rows; null if not recorded. */
  prior_looks?: number | null;
  look_budget?: number | null;
}
export type AttackOutcome = "survived" | "broken" | "not_run";
export interface AttackResult {
  attack_id: string;
  name: string;
  outcome: AttackOutcome;
  reason: string;
  original_effect: number | null;
  attacked_effect: number | null;
  n_rows: number | null;
  /** False when the check does not apply to this claim or table (not just too little data). */
  applicable?: boolean;
  details: Record<string, number | string | boolean | null>;
}
/** One scored backtest point of a forecast claim. */
export interface ForecastOrigin {
  origin: string;
  target: string;
  horizon: number;
  actual: number;
  forecast: number;
  baseline: number;
}
/** The backtest behind a forecast claim: past accuracy on periods the method did not see. */
export interface ForecastEvidence {
  method: "trend_seasonal" | "holt_winters";
  baseline: "seasonal_naive" | "naive";
  horizon: number;
  season: number;
  period: string;
  n_origins: number;
  n_blocks: number;
  first_origin: string;
  last_origin: string;
  mase_model: number;
  mase_baseline: number;
  error_reduction: number;
  horizon_reductions: number[];
  reduction_vs_last_value: number | null;
  interval_level: number | null;
  interval_coverage: number | null;
  interval_calibrated: boolean | null;
  origins: ForecastOrigin[];
  disclaimer: string;
}
export interface Proof {
  insight_id: string;
  verdict: "PASS" | "REJECT";
  gate_outcome: GateOutcome;
  bh_family_id: string;
  seed: number | null;
  p_value: number | null;
  q_value: number | null;
  effect_size: number | null;
  effect_metric: string | null;
  test_type: string | null;
  falsification_code: string | null;
  n_hypotheses_in_batch: number | null;
  asserted_direction: string | null;
  observed_direction: string | null;
  failure_reason: string | null;
  reported_effect?: number | null;
  reported_effect_metric?: string | null;
  permutation_scheme?: PermutationScheme | null;
  /** How precisely the rows pin down the effect; shown beside it, never used by the gate. */
  effect_interval?: {
    estimate: number;
    low: number;
    high: number;
    confidence: number;
    method: "row_bootstrap" | "entity_bootstrap" | "period_bootstrap" | "origin_block_bootstrap";
    n_resamples: number;
  } | null;
  /** Smallest effect the rows could have found; only on a tested, non-significant claim. */
  power?: {
    effect_metric: string;
    detectable_effect: number;
    n_effective: number;
    unit: "observations" | "periods" | "entities" | "origin_blocks";
    alpha: number;
    target_power: number;
  } | null;
  split?: SplitRecord | null;
  attacks?: AttackResult[];
  /** Forecast claims only. */
  forecast?: ForecastEvidence | null;
}
export interface ScatterChart {
  kind: "scatter";
  x: string;
  y: string;
  n: number;
  shown: number;
  points: [number, number][];
  fit: [number, number][];
}
export interface GroupSummary {
  label: string;
  n: number;
  minimum: number;
  q1: number;
  median: number;
  q3: number;
  maximum: number;
  points: number[];
}
export interface GroupsChart {
  kind: "groups";
  value: string;
  group: string;
  n: number;
  groups: GroupSummary[];
}
export type ChartSpec = ScatterChart | GroupsChart;
export interface ResultRow {
  insight_id: string;
  claim: string;
  /** Present on runs recorded after the planner landed; older rows fall back to the id. */
  claim_type?: string | null;
  proof: Proof;
  explanation: string | null;
  effect_strength: string | null;
  complete_rows: number | null;
  n_permutations: number | null;
  chart: ChartSpec | null;
}
export interface ColumnOverview {
  name: string;
  kind: "numeric" | "category";
  n: number;
  missing: number;
  mean: number | null;
  median: number | null;
  bins: { x0: number; x1: number; count: number }[];
  top: { label: string; count: number }[];
}
export interface DataOverview {
  rows: number;
  columns: ColumnOverview[];
  correlations: { columns: string[]; values: (number | null)[][] } | null;
}
export interface FollowUp {
  sentence: string;
  claim_type: "correlation" | "group_difference";
  variables: string[];
}
export interface Caveat {
  insight_id: string;
  control: string;
  control_kind: "numeric" | "categorical";
  measure: "spearman_rho" | "rank_eta_squared";
  link_first: number;
  link_second: number;
  before: number;
  after: number;
  n: number;
  text: string;
  follow_ups: FollowUp[];
}
export interface FindingReview {
  insight_id: string;
  status: "flagged" | "none_found" | "not_checked";
  reason: string | null;
  controls_checked: number;
  skipped_near_duplicates: number;
  caveats: Caveat[];
}
export interface Explanation {
  insight_id: string;
  text: string;
  source: "template" | "model";
  fallback_reason: string | null;
}
export interface AdvisoryReport {
  explanations: Explanation[];
  reviews: FindingReview[];
  notes: string[];
}
export interface RunResults {
  run: RunView;
  verified_insights: ResultRow[];
  rejected_claims: ResultRow[];
  candidate_count: number;
  unverified_candidate_count: number;
  exploration: ExplorationSummary | null;
  /** Measured analyses the planner asked for; whole table, held-out scores, never a claim. */
  planned_measured?: MeasuredAnalysis | null;
  advisory?: AdvisoryReport | null;
}
export interface ColumnNote {
  kind: string;
  level: "note" | "check";
  message: string;
  suggestion: string | null;
  evidence: Record<string, number | string>;
}
export interface ColumnBrief {
  name: string;
  role: string;
  usable: boolean;
  label: string | null;
  unit: string | null;
  coding: Record<string, string> | null;
  notes: ColumnNote[];
}
export interface DataBrief {
  headline: string;
  columns_to_check: number;
  recognised: number;
  columns: ColumnBrief[];
}
export interface LedgerEntry {
  entry_id: string;
  kind: "tool" | "python";
  name: string;
  args: Record<string, unknown>;
  ok: boolean;
  summary: string;
  examined: number;
  duration_ms: number;
}
export interface PlanDrop {
  what: "claim" | "measured_request" | "narrative_focus";
  item: string;
  reason_code: string;
  reason: string;
}
export interface PlanRecord {
  model: string;
  shape: string;
  shape_confirmation: { verdict: "confirm" | "flag"; note: string };
  accepted_claims: { claim_type: string; variables: string[]; insight_id: string }[];
  accepted_measured: { task: string; target: string | null }[];
  accepted_focus: string[];
  dropped: PlanDrop[];
  turns: number;
  repaired: boolean;
  input_tokens: number;
  output_tokens: number;
}
export interface ExplorationSummary {
  engine: "scan" | "agent" | "api" | "planner";
  /** Planner runs only: what the plan asked for and what code accepted or dropped. */
  plan?: PlanRecord | null;
  examined: number;
  proposed: number;
  tested: number;
  tool_calls: number;
  python_runs: number;
  turns: number;
  input_tokens: number;
  output_tokens: number;
  entries: LedgerEntry[];
}
export interface SystemStatus {
  analysis_engine: string;
  verification_generator: string;
  model: string | null;
  model_ready: boolean;
  blockers: string[];
  budgets: {
    max_turns: number;
    max_tool_calls: number;
    max_python_runs: number;
    max_total_tokens: number;
    max_hypotheses_examined: number;
  };
  chat_ready: boolean;
  chat_blockers: string[];
  alpha: number;
}
export type AnswerKind =
  | "descriptive"
  | "exploratory"
  | "verified"
  | "rejected"
  | "not_testable"
  | "not_tested"
  | "unanswered";
export interface Evidence {
  entry_id: string;
  tool: string;
  args: Record<string, unknown>;
  output: Record<string, unknown> | null;
}
export interface ClaimDisclosure {
  test_number: number;
  earlier_chat_tests: number;
  earlier_run_tests: number;
  family_size: number;
  asked_after_seeing_results: boolean;
  corrected_for_earlier_tests: boolean;
}
export interface ClaimOutcome {
  label: "verified" | "rejected" | "not_testable";
  row: ResultRow;
  disclosure: ClaimDisclosure;
}
export interface ChatWork {
  turns: number;
  tool_calls: number;
  examined: number;
  input_tokens: number;
  output_tokens: number;
}
export interface ChatAnswer {
  kind: AnswerKind;
  text: string;
  evidence: Evidence[];
  tested: ClaimOutcome | null;
  notes: string[];
  work: ChatWork;
}
export interface ChatExchange {
  message_id: string;
  dataset_id: string;
  created_at: string;
  question: string;
  answer: ChatAnswer;
}
export interface LedgerRecord {
  test_number: number;
  message_id: string;
  created_at: string;
  question: string;
  claim: string;
  label: "verified" | "rejected" | "not_testable";
  q_value: number | null;
  effect_size: number | null;
  effect_metric: string | null;
  n: number | null;
}
export interface ChatLedger {
  chat_tests: number;
  run_tests: number;
  limit: number;
  records: LedgerRecord[];
}
export type Scalar = number | string | boolean | null;
export type ExactChart =
  | { kind: "line"; x_label: string; y_label: string; points: [string, number][]; marks: string[] }
  | {
      kind: "bar";
      x_label: string;
      y_label: string;
      value_format: "number" | "percent";
      bars: { label: string; value: number; n: number | null }[];
    }
  | {
      kind: "waterfall";
      y_label: string;
      start_label: string;
      end_label: string;
      start: number;
      end: number;
      steps: { label: string; value: number }[];
    }
  | { kind: "pareto"; y_label: string; bars: { label: string; value: number; cumulative_share: number }[] }
  | { kind: "heat_strip"; label: string; cells: { label: string; index: number }[] }
  | {
      kind: "forecast";
      x_label: string;
      y_label: string;
      interval_level: number;
      actual: [string, number][];
      forecast: [string, number][];
      lower: [string, number][];
      upper: [string, number][];
    };
export interface ReportSummary {
  source: "template" | "model";
  lines: { item_id: string; text: string }[];
  fallback_reason: string | null;
  pending: boolean;
}
export interface ExactItem {
  id: string;
  kind: string;
  level: "exact";
  status: "ok" | "not_run";
  title: string;
  sentence: string;
  reason: string | null;
  formula: string;
  columns: string[];
  filters: string[];
  n_rows: number;
  values: Record<string, Scalar>;
  table: Record<string, Scalar>[];
  chart: ExactChart | null;
  section?: string;
  importance?: number;
  also?: string[];
}
export interface StorySection {
  key: string;
  title: string;
  item_ids: string[];
}
export interface WatchQuestion {
  text: string;
  item_id: string;
}
export interface Story {
  lead_ids: string[];
  sections: StorySection[];
  questions: WatchQuestion[];
}
export interface SectorMatch {
  sector: string;
  label: string;
  score: number;
  roles: Record<string, string>;
  reasons: string[];
}
export interface ShapeProfile {
  shape: "cross_section" | "time_series" | "panel" | "transactions";
  time_column: string | null;
  entity_column: string | null;
  period: string | null;
  n_periods: number;
  full_cycles: number;
  reasons: string[];
}
export interface ComputedAnalysis {
  version: number;
  sector: SectorMatch;
  shape: ShapeProfile;
  scope_note: string;
  items: ExactItem[];
  summary: ReportSummary | null;
  story?: Story | null;
}
export type MeasuredKind =
  | "driver_regression"
  | "driver_classification"
  | "adjusted_association"
  | "segments"
  | "anomalies"
  | "forecast"
  | "threshold"
  | "components";
export type MeasuredStatus = "ok" | "not_run" | "no_lift" | "withheld";
export interface Exclusion {
  column: string;
  reason: string;
}
export interface MeasuredItem {
  id: string;
  kind: MeasuredKind;
  level: "measured";
  status: MeasuredStatus;
  title: string;
  sentence: string;
  reason: string | null;
  target: string | null;
  features: string[];
  model_family: string | null;
  models_tried: number;
  split: string;
  baseline: string | null;
  metric: string | null;
  baseline_score: number | null;
  model_score: number | null;
  lift: number | null;
  spread: number | null;
  n_rows: number;
  values: Record<string, Scalar>;
  table: Record<string, Scalar>[];
  chart: ExactChart | null;
  leakage: Exclusion[];
}
export interface MeasuredAnalysis {
  version: number;
  seed: number;
  n_rows: number;
  sampled_rows: number | null;
  items: MeasuredItem[];
  excluded: Exclusion[];
  seconds: number;
}
export interface DatasetView {
  dataset_id: string;
  name: string;
  created_at: string;
  size_bytes: number;
  usable_columns: number;
  preview: DataPreview;
  overview: DataOverview | null;
  brief: DataBrief | null;
  computed: ComputedAnalysis | null;
  measured?: MeasuredAnalysis | null;
  measured_pending?: boolean;
  measured_failed_version?: number;
}
export interface DatasetSummary {
  dataset_id: string;
  name: string;
  created_at: string;
  rows: number;
  columns: number;
  run_count: number;
  last_status: RunStatus | null;
}

async function failure(response: Response): Promise<Error> {
  let message = `Request failed (${response.status}).`;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") message = body.detail;
  } catch {
    /* keep the generic message */
  }
  return new Error(message);
}

async function json<T>(response: Response): Promise<T> {
  if (response.status === 401 && !response.url.includes("/api/auth/")) {
    window.dispatchEvent(new Event("pramana-signed-out"));
  }
  if (!response.ok) throw await failure(response);
  return (await response.json()) as T;
}

export interface UserView {
  user_id: string;
  email: string;
}
export interface AuthStatus {
  has_accounts: boolean;
  signup_open: boolean;
}

function post(url: string, body: unknown): Promise<Response> {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const api = {
  me(): Promise<UserView | null> {
    return fetch("/api/auth/me").then((r) => (r.ok ? (r.json() as Promise<UserView>) : null));
  },
  authStatus(): Promise<AuthStatus> {
    return fetch("/api/auth/status").then((r) => json<AuthStatus>(r));
  },
  signup(email: string, password: string): Promise<UserView> {
    return post("/api/auth/signup", { email, password }).then((r) => json<UserView>(r));
  },
  login(email: string, password: string): Promise<UserView> {
    return post("/api/auth/login", { email, password }).then((r) => json<UserView>(r));
  },
  logout(): Promise<void> {
    return fetch("/api/auth/logout", { method: "POST" }).then(() => undefined);
  },
  uploadDataset(file: File, name: string): Promise<DatasetView> {
    const form = new FormData();
    form.append("file", file);
    if (name.trim()) form.append("name", name.trim());
    return fetch("/api/datasets", { method: "POST", body: form }).then((r) => json<DatasetView>(r));
  },
  datasets(): Promise<DatasetSummary[]> {
    return fetch("/api/datasets").then((r) => json<DatasetSummary[]>(r));
  },
  dataset(id: string): Promise<DatasetView> {
    return fetch(`/api/datasets/${id}`).then((r) => json<DatasetView>(r));
  },
  datasetRuns(id: string): Promise<RunView[]> {
    return fetch(`/api/datasets/${id}/runs`).then((r) => json<RunView[]>(r));
  },
  analyse(id: string, question: string): Promise<RunView> {
    const form = new FormData();
    if (question.trim()) form.append("user_query", question.trim());
    return fetch(`/api/datasets/${id}/runs`, { method: "POST", body: form }).then((r) =>
      json<RunView>(r),
    );
  },
  run(id: string): Promise<RunView> {
    return fetch(`/api/runs/${id}`).then((r) => json<RunView>(r));
  },
  results(id: string): Promise<RunResults> {
    return fetch(`/api/runs/${id}/results`).then((r) => json<RunResults>(r));
  },
  chat(id: string): Promise<ChatExchange[]> {
    return fetch(`/api/datasets/${id}/chat`).then((r) => json<ChatExchange[]>(r));
  },
  ask(id: string, question: string): Promise<ChatExchange> {
    return post(`/api/datasets/${id}/chat`, { question }).then((r) => json<ChatExchange>(r));
  },
  chatLedger(id: string): Promise<ChatLedger> {
    return fetch(`/api/datasets/${id}/chat/tests`).then((r) => json<ChatLedger>(r));
  },
  system(): Promise<SystemStatus> {
    return fetch("/api/system").then((r) => json<SystemStatus>(r));
  },
  memory(): Promise<Lesson[]> {
    return fetch("/api/memory?limit=100").then((r) => json<Lesson[]>(r));
  },
  exportUrl(id: string, format: "json" | "csv"): string {
    return `/api/runs/${id}/export/${format}`;
  },
};
