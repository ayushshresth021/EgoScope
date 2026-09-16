import { useMemo, useState } from "react";
import type { CanvasEpisode } from "../api";
import { asScore, plainReasons } from "../copy";

const VW = 1040;
const VH = 420;
const PAD = 36;

function project(
  episodes: CanvasEpisode[],
): (x: number, y: number) => { cx: number; cy: number } {
  const xs = episodes.map((e) => e.x);
  const ys = episodes.map((e) => e.y);
  const xmin = Math.min(...xs);
  const xmax = Math.max(...xs);
  const ymin = Math.min(...ys);
  const ymax = Math.max(...ys);
  const dx = xmax - xmin || 1;
  const dy = ymax - ymin || 1;
  return (x, y) => ({
    cx: PAD + ((x - xmin) / dx) * (VW - 2 * PAD),
    cy: PAD + (1 - (y - ymin) / dy) * (VH - 2 * PAD),
  });
}

export function BehaviorCanvas({
  episodes,
  nRegions,
}: {
  episodes: CanvasEpisode[];
  nRegions: number;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const toXY = useMemo(
    () => (episodes.length ? project(episodes) : null),
    [episodes],
  );
  if (!episodes.length || !toXY) {
    return <p className="note">No clip map for this run.</p>;
  }
  const selected = episodes.find((e) => e.id === selectedId);
  const n = episodes.length;
  const k = episodes.filter((e) => e.kept).length;
  const reasons = selected ? plainReasons(selected.reason) : [];
  return (
    <div className="canvas-wrap">
      <div className="field">
        <svg viewBox={`0 0 ${VW} ${VH}`} role="img" aria-label="Map of clips. Nearby dots are similar motion.">
          <text className="axis" x={PAD} y={VH - 12}>
            similar →
          </text>
          <text className="axis" x={VW - 90} y={PAD - 10}>
            similar →
          </text>
          <text className="axis" x={PAD} y={18}>
            {n} clips · {nRegions} motion types · keep {k}
          </text>
          {episodes.map((ep) => {
            const { cx, cy } = toXY(ep.x, ep.y);
            const active = selectedId === ep.id;
            return (
              <circle
                key={ep.id}
                className={["ep", ep.kept ? "kept" : "drop", active ? "active" : ""].join(" ")}
                cx={cx}
                cy={cy}
                r={active ? 7.5 : 6}
                onClick={() => setSelectedId((cur) => (cur === ep.id ? null : ep.id))}
              />
            );
          })}
        </svg>
      </div>
      <aside className="inspector">
        {selected ? (
          <>
            <p className="kicker">This clip</p>
            <p className={selected.kept ? "verdict" : "verdict drop"}>
              {selected.kept ? "KEEP" : "DROP"}
            </p>
            <dl className="stats">
              <div>
                <dt>Rank</dt>
                <dd>{selected.rank}</dd>
              </div>
              <div>
                <dt>Clean motion</dt>
                <dd>{asScore(selected.quality)}</dd>
              </div>
              <div>
                <dt>New behavior</dt>
                <dd>{asScore(selected.coverage_gain)}</dd>
              </div>
              <div>
                <dt>Already seen</dt>
                <dd>{asScore(selected.redundancy)}</dd>
              </div>
            </dl>
            {reasons.length ? (
              <ul className="why">
                {reasons.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            ) : null}
          </>
        ) : (
          <p className="note">
            Click a clip. Nearby dots are similar motion — not named tasks or
            objects.
          </p>
        )}
      </aside>
    </div>
  );
}
