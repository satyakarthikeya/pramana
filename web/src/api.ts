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
export interface Proof {
  insight_id: string;
  verdict: "PASS" | "REJECT";
  gate_outcome: string;
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
export interface RunResults {
  run: RunView;
  verified_insights: ResultRow[];
  rejected_claims: ResultRow[];
  candidate_count: number;
  unverified_candidate_count: number;
  exploration: ExplorationSummary | null;
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
export interface ExplorationSummary {
  engine: "scan" | "agent" | "api";
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
  uploadDataset(file: File): Promise<DatasetView> {
    const form = new FormData();
    form.append("file", file);
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
