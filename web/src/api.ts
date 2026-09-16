export type PriorityLevel = "low" | "medium" | "high";

export type Requirement = {
  requirement_id: string;
  text: string;
  status: "direct" | "proxy" | "missing_information" | "unsupported" | "prohibited";
  signal?: string | null;
  field?: string | null;
  missing?: string | null;
  limitation?: string | null;
  unsupported_concept?: string | null;
  source?: "explicit" | "assumed" | "default" | null;
};

export type Scope = {
  scope_version: string;
  request_id: string;
  original_request: string;
  request_type: string;
  objective: { description: string };
  budget: {
    unit: "episodes" | "episode_fraction" | null;
    value: number | null;
    source: string | null;
    compare_with?: number | null;
  };
  hard_constraints: Array<{
    requirement_id: string;
    concept: string;
    field: string;
    operator: string;
    value: number;
    source: string;
    signal?: string | null;
  }>;
  soft_priorities: {
    quality: PriorityLevel;
    coverage: PriorityLevel;
    redundancy_reduction: PriorityLevel;
  };
  comparisons: string[];
  run_options: { random_seed: number; number_of_regions: number };
  assumptions: string[];
  requested_outputs: string[];
  strategy_profiles: string[];
};

export type ScopeProposal = {
  proposed_scope: Scope;
  requirements: Requirement[];
  can_execute: boolean;
  blocking_reasons: string[];
};

export type CanvasEpisode = {
  id: string;
  x: number;
  y: number;
  region: number;
  rank: number;
  quality: number;
  coverage_gain: number | null;
  redundancy: number | null;
  value: number | null;
  nearest: string;
  stationary: number;
  reason: string;
  kept: boolean;
};

export type RunRecord = {
  run_id: string;
  status: string;
  analysis: {
    confirmed_scope: Scope;
    feasibility: {
      feasible: boolean;
      reason: string | null;
      n_universe: number;
      n_eligible: number;
      requested_k: number | null;
      constraint_steps: Array<Record<string, unknown>>;
    };
    recommendation: {
      method: string | null;
      profile: string;
      reason: string;
      confidence: string;
      tie?: boolean;
    };
    primary_metrics: Record<string, number | Record<string, number>>;
    method_rows: Array<Record<string, unknown>>;
    selected_ids: string[];
    k: number;
    unsupported: string[];
    proxies: string[];
    tradeoff: string;
    canvas_episodes: CanvasEpisode[];
    extra: Record<string, unknown>;
  };
  brief: string;
};

export type Example = {
  id: string;
  label: string;
  request: string;
  request_type: string;
};

export async function fetchExamples(): Promise<Example[]> {
  const res = await fetch("/api/examples");
  if (!res.ok) throw new Error("examples");
  const data = (await res.json()) as { examples: Example[] };
  return data.examples;
}

export async function scopeRequest(request: string): Promise<ScopeProposal> {
  const res = await fetch("/api/scope", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error((detail as { detail?: string }).detail || "scope failed");
  }
  return res.json() as Promise<ScopeProposal>;
}

export async function createRun(confirmed: Scope): Promise<{ run_id: string }> {
  const res = await fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmed_scope: confirmed, feature_source: "bundled_demo" }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error((detail as { detail?: string }).detail || "run failed");
  }
  return res.json() as Promise<{ run_id: string }>;
}

export async function fetchRun(runId: string): Promise<RunRecord> {
  const res = await fetch(`/api/runs/${runId}`);
  if (!res.ok) throw new Error("run not found");
  return res.json() as Promise<RunRecord>;
}
