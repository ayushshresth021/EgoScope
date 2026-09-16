export const TAGLINE = "Keep the clips that teach the robot";

export const STEPS = [
  { id: "request", label: "Ask" },
  { id: "scope", label: "Check" },
  { id: "results", label: "Results" },
] as const;

export type FlowStep = (typeof STEPS)[number]["id"];

export const METHOD_LABEL: Record<string, string> = {
  EgoSelect: "These three checks",
  "Dedup-only": "Remove duplicates",
  "Diversity-only": "Spread across motions",
  Random: "Random sample",
};

export const METHOD_HINT: Record<string, string> = {
  EgoSelect: "Score each clip for clean motion, new behavior, and repeats",
  "Dedup-only": "Drops clips that look like ones we already kept",
  "Diversity-only": "Picks clips from as many motion types as possible",
  Random: "Picks clips by chance, as a baseline",
};

const REQUEST_TYPE_LABEL: Record<string, string> = {
  select_subset: "Build a smaller training set",
  find_minimum_subset: "Find the smallest set that still covers the motion range",
  compare_budgets: "Compare two keep amounts",
  compare_methods: "Compare picking methods",
  test_strategy: "See which clips get picked no matter the strategy",
  diagnose_dataset: "Describe the dataset",
  unsupported_or_unknown: "This request is beyond what we can measure",
};

export function requestTypeLabel(type: string): string {
  return REQUEST_TYPE_LABEL[type] ?? type.replaceAll("_", " ");
}

export function methodLabel(name: string | null | undefined): string {
  if (!name) return "No method";
  return METHOD_LABEL[name] ?? name;
}

export function statusLabel(
  status: "direct" | "proxy" | "missing_information" | "unsupported" | "prohibited",
): string {
  if (status === "direct") return "Yes";
  if (status === "proxy") return "Close stand-in";
  if (status === "missing_information") return "Need more detail";
  if (status === "prohibited") return "Not allowed";
  return "Can't";
}

const SIGNAL_LABEL: Record<string, string> = {
  episode_budget: "Keep this share of clips",
  visual_motion_coverage: "Variety of motion",
  reduce_redundancy: "Fewer near-copies",
  general_quality: "Clean motion",
  avoid_idle: "Skip waiting-around",
};

export function signalLabel(signal: string | null | undefined): string {
  if (!signal) return "—";
  return SIGNAL_LABEL[signal] ?? signal.replaceAll("_", " ");
}

export function confidenceLabel(value: string): string {
  if (value === "high") return "Clear";
  if (value === "moderate") return "Reasonably sure";
  return "Unsure";
}

function meanRow(value: unknown): { mean: number; min: number; max: number } | null {
  if (typeof value === "object" && value && "mean" in value) {
    return value as { mean: number; min: number; max: number };
  }
  return null;
}

export function asPercent(value: unknown): string {
  if (typeof value === "number" && !Number.isNaN(value)) {
    const ratio = value >= 0 && value <= 1 ? value : value / 100;
    return `${Math.round(ratio * 100)}%`;
  }
  const row = meanRow(value);
  if (row) {
    return `${Math.round(row.mean * 100)}% (${Math.round(row.min * 100)}–${Math.round(row.max * 100)}%)`;
  }
  return "—";
}

export function asScore(value: unknown, digits = 2): string {
  if (typeof value === "number" && !Number.isNaN(value)) return value.toFixed(digits);
  const row = meanRow(value);
  if (row) {
    return `${row.mean.toFixed(digits)} (${row.min.toFixed(digits)}–${row.max.toFixed(digits)})`;
  }
  return "—";
}

const REASON_MAP: Record<string, string> = {
  "Underrepresented behavior": "This kind of motion is still rare in the keep set",
  "Behavior already represented": "We already kept this kind of motion",
  "High quality": "The motion looks clean",
  "High redundancy": "This looks like a clip we already kept",
  "Low redundancy": "This does not look like clips we already kept",
};

export function plainReasons(reason: string): string[] {
  return reason
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      if (REASON_MAP[part]) return REASON_MAP[part];
      const idle = part.match(/^(\d+)% stationary$/);
      if (idle) return `${idle[1]}% of the clip is waiting around`;
      return part;
    });
}

export function recommendationCopy(
  rec: {
    method: string | null;
    profile: string;
    reason: string;
    confidence: string;
    tie?: boolean;
  },
  k: number,
  n: number,
): { title: string; body: string; checks: string[] } {
  const checks = [
    "Clean motion — does the clip look usable?",
    "New behavior — does it add a motion type we don't already have?",
    "Repeats — does it look like a clip we already kept?",
  ];
  if (!rec.method) {
    if (/unsupported/i.test(rec.reason)) {
      return {
        title: "We cannot pick clips for this request",
        body: "It asks for something we cannot measure yet — a named task, an object, or whether a robot would succeed.",
        checks: [],
      };
    }
    return {
      title: "We could not pick a training set",
      body: rec.reason,
      checks: [],
    };
  }
  if (rec.tie) {
    return {
      title: `Keep ${k} of ${n} clips`,
      body: "The three checks did not separate this set from a simpler alternative. Treat this as a starting point, not a final call.",
      checks,
    };
  }
  if (rec.profile === "coverage_first") {
    return {
      title: `Keep ${k} of ${n} clips`,
      body: `We scored every clip on the checks below, then kept the ${k} that add the most kinds of motion still missing.`,
      checks,
    };
  }
  if (rec.profile === "dedup_first") {
    return {
      title: `Keep ${k} of ${n} clips`,
      body: `We scored every clip on the checks below, then kept the ${k} that look least like clips we already kept.`,
      checks,
    };
  }
  if (rec.profile === "quality_first") {
    return {
      title: `Keep ${k} of ${n} clips`,
      body: `We scored every clip on the checks below, then kept the ${k} where the motion looks cleanest.`,
      checks,
    };
  }
  return {
    title: `Keep ${k} of ${n} clips`,
    body: `We scored every clip on the three checks below, then kept the top ${k}.`,
    checks,
  };
}

export function plainTradeoff(text: string): string {
  if (text.includes("Dedup-only produces lower redundancy")) {
    return "Removing near-copies cuts repeats more. Ranking on the three checks keeps more variety and cleaner motion.";
  }
  if (text.startsWith("Increasing the budget")) {
    return text
      .replace("episodes", "clips")
      .replace("coverage", "variety")
      .replace("redundancy", "repeats");
  }
  if (text.includes("selected under every tested")) {
    return text.replace("episodes", "clips");
  }
  if (text === "See measured method table.") {
    return "See the comparison table above.";
  }
  return text
    .replaceAll("EgoSelect", "the three-check ranking")
    .replaceAll("Dedup-only", "removing near-copies");
}

export function profileLabel(profile: string): string {
  if (profile === "coverage_first") return "Favor covering more kinds of motion";
  if (profile === "dedup_first") return "Favor less repetition";
  if (profile === "quality_first") return "Favor cleaner clips";
  return "Balance quality, variety, and repeats";
}
