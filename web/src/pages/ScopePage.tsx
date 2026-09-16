import type { PriorityLevel, Scope, ScopeProposal } from "../api";
import { StepBar } from "../components/StepBar";
import { requestTypeLabel, signalLabel, statusLabel } from "../copy";

const PRIORITIES: PriorityLevel[] = ["low", "medium", "high"];
const BASELINES = [
  { id: "random", label: "Random sample" },
  { id: "dedup_only", label: "Remove duplicates" },
  { id: "diversity_only", label: "Spread across motions" },
];

export function ScopePage({
  proposal,
  scope,
  onChange,
  onConfirm,
  busy,
  error,
  onBack,
}: {
  proposal: ScopeProposal;
  scope: Scope;
  onChange: (scope: Scope) => void;
  onConfirm: () => void;
  busy: boolean;
  error: string | null;
  onBack: () => void;
}) {
  const hasBudget = scope.budget.value != null;
  const budgetUnit = scope.budget.unit ?? "episode_fraction";
  const budgetValue = !hasBudget
    ? ""
    : budgetUnit === "episode_fraction"
      ? Math.round((scope.budget.value ?? 0) * 100)
      : (scope.budget.value ?? 20);

  function setBudget(next: number) {
    onChange({
      ...scope,
      budget: {
        ...scope.budget,
        unit: budgetUnit,
        value: budgetUnit === "episode_fraction" ? next / 100 : next,
        source: "explicit",
      },
    });
  }

  function setPriority(key: keyof Scope["soft_priorities"], value: PriorityLevel) {
    onChange({
      ...scope,
      soft_priorities: { ...scope.soft_priorities, [key]: value },
    });
  }

  function toggleBaseline(id: string) {
    const has = scope.comparisons.includes(id);
    onChange({
      ...scope,
      comparisons: has
        ? scope.comparisons.filter((c) => c !== id)
        : [...scope.comparisons, id],
    });
  }

  function setIdleThreshold(value: number) {
    const existing = scope.hard_constraints.find((c) => c.field === "stationary_ratio");
    const constraint = {
      requirement_id: existing?.requirement_id ?? "R-idle",
      concept: "maximum_stationary_ratio",
      field: "stationary_ratio",
      operator: "less_than_or_equal",
      value,
      source: "explicit",
      signal: "avoid_idle",
    };
    const rest = scope.hard_constraints.filter((c) => c.field !== "stationary_ratio");
    onChange({ ...scope, hard_constraints: [...rest, constraint] });
  }

  const idle = scope.hard_constraints.find((c) => c.field === "stationary_ratio");

  return (
    <section className="page scope-page">
      <StepBar current="scope" />
      <p className="kicker">Check the plan</p>
      <h1>Here is what we can actually do with your request.</h1>
      <p className="lede">
        Nothing is picked yet. Confirm the plan, or change the rules first.
        Orange means we can measure it. Red means we cannot.
      </p>

      <div className="cards">
        <article>
          <h2>What you asked</h2>
          <p>{requestTypeLabel(scope.request_type)}</p>
          <p className="note">{scope.original_request}</p>
        </article>
        <article>
          <h2>How much to keep</h2>
          <div className="inline">
            <select
              value={budgetUnit}
              onChange={(ev) =>
                onChange({
                  ...scope,
                  budget: {
                    ...scope.budget,
                    unit: ev.target.value as "episodes" | "episode_fraction",
                    source: "explicit",
                  },
                })
              }
            >
              <option value="episode_fraction">Percent of clips</option>
              <option value="episodes">Number of clips</option>
            </select>
            <input
              type="number"
              min={1}
              max={budgetUnit === "episode_fraction" ? 100 : 80}
              value={budgetValue}
              onChange={(ev) => setBudget(Number(ev.target.value))}
            />
          </div>
          <p className="note">
            {budgetUnit === "episode_fraction"
              ? "A smaller percent means a cheaper training run."
              : "Count of clips we will keep, after the idle rule."}
          </p>
        </article>
        <article>
          <h2>Skip waiting-around clips</h2>
          <label>
            Drop a clip if it sits still more than this share
            <input
              type="number"
              step={0.01}
              min={0}
              max={1}
              value={idle?.value ?? ""}
              placeholder="optional, e.g. 0.25"
              onChange={(ev) => {
                const raw = ev.target.value;
                if (!raw) {
                  onChange({
                    ...scope,
                    hard_constraints: scope.hard_constraints.filter(
                      (c) => c.field !== "stationary_ratio",
                    ),
                  });
                  return;
                }
                setIdleThreshold(Number(raw));
              }}
            />
          </label>
          <p className="note">
            0.25 means drop clips that are idle more than a quarter of the time.
          </p>
        </article>
        <article>
          <h2>What to favor</h2>
          {(
            [
              ["quality", "Clean motion"],
              ["coverage", "Variety of motion"],
              ["redundancy_reduction", "Fewer repeats"],
            ] as const
          ).map(([key, label]) => (
            <label key={key}>
              {label}
              <select
                value={scope.soft_priorities[key]}
                onChange={(ev) =>
                  setPriority(key, ev.target.value as PriorityLevel)
                }
              >
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </article>
        <article>
          <h2>Compare against</h2>
          {BASELINES.map((b) => (
            <label key={b.id} className="check">
              <input
                type="checkbox"
                checked={scope.comparisons.includes(b.id)}
                onChange={() => toggleBaseline(b.id)}
              />
              {b.label}
            </label>
          ))}
          <p className="note">
            The ranked keep-set is always included. These are simpler ways to
            pick the same number of clips.
          </p>
        </article>
      </div>

      <h2>Can we do each part of your request?</h2>
      <table className="matrix">
        <thead>
          <tr>
            <th>You asked</th>
            <th>Can we?</th>
            <th>How</th>
            <th>Note</th>
          </tr>
        </thead>
        <tbody>
          {proposal.requirements.map((req) => (
            <tr key={req.requirement_id} className={req.status}>
              <td>{req.text}</td>
              <td>
                <span className={`tag ${req.status}`}>{statusLabel(req.status)}</span>
              </td>
              <td>{signalLabel(req.signal)}</td>
              <td>{req.limitation ?? req.missing ?? req.unsupported_concept ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {scope.assumptions.length ? (
        <>
          <h2>What we are assuming</h2>
          <ul>
            {scope.assumptions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      ) : null}

      {proposal.requirements.some(
        (r) => r.status === "unsupported" || r.status === "prohibited",
      ) ? (
        <>
          <h2>We will not try to do this</h2>
          <ul>
            {proposal.requirements
              .filter((r) => r.status === "unsupported" || r.status === "prohibited")
              .map((r) => (
                <li key={r.requirement_id}>
                  {r.text} — {r.limitation ?? r.unsupported_concept}
                </li>
              ))}
          </ul>
          <p className="note">
            These stay in the record so you can see the limit. They do not
            change which clips are kept.
          </p>
        </>
      ) : null}

      {proposal.blocking_reasons.length ? (
        <ul className="error-list">
          {proposal.blocking_reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
      <div className="actions">
        <button type="button" onClick={onBack}>
          Edit request
        </button>
        <button
          type="button"
          className="primary"
          disabled={busy}
          onClick={onConfirm}
        >
          {busy ? "Picking clips…" : "Pick the clips"}
        </button>
      </div>
    </section>
  );
}
