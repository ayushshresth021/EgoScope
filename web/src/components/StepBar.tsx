import { STEPS, type FlowStep } from "../copy";

export function StepBar({ current }: { current: FlowStep }) {
  const active = STEPS.findIndex((step) => step.id === current);
  return (
    <ol className="steps" aria-label="Decision steps">
      {STEPS.map((step, index) => {
        const state = index < active ? "done" : index === active ? "now" : "";
        return (
          <li key={step.id} className={state}>
            <span className="steps-n">{String(index + 1).padStart(2, "0")}</span>
            <span>{step.label}</span>
          </li>
        );
      })}
    </ol>
  );
}
