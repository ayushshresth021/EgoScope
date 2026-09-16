import { useEffect, useState } from "react";
import { fetchExamples, type Example } from "../api";
import { StepBar } from "../components/StepBar";

export function RequestPage({
  request,
  onChange,
  onScope,
  busy,
  error,
}: {
  request: string;
  onChange: (value: string) => void;
  onScope: () => void;
  busy: boolean;
  error: string | null;
}) {
  const [examples, setExamples] = useState<Example[]>([]);
  useEffect(() => {
    fetchExamples()
      .then(setExamples)
      .catch(() => setExamples([]));
  }, []);

  return (
    <section className="page request-page">
      <StepBar current="request" />
      <p className="kicker">The problem</p>
      <h1>Most of this video should not be trained on.</h1>
      <p className="lede">
        Robots learn from first-person footage, but hours of it are waiting,
        repeats, and the same motion again. Training on all of it is slow
        and expensive. Training on the wrong clips teaches the robot the
        wrong habits.
      </p>

      <h2 className="kicker">What EgoScope does</h2>
      <p className="lede">
        You write what to keep. Every clip is scored on four measurements from
        the footage itself, then we keep a smaller set.
      </p>
      <div className="measures">
        <article>
          <h2>Waiting-around</h2>
          <p>
            How much of the clip the camera is sitting still. We read this from
            pose speed — if it barely moves, the clip is idle.
          </p>
        </article>
        <article>
          <h2>Clean motion</h2>
          <p>
            Whether the recording looks usable. We score missing frames, broken
            pose tracks, and whether any motion happened at all.
          </p>
        </article>
        <article>
          <h2>Variety of motion</h2>
          <p>
            Whether this clip is a kind of movement we don't already have. We
            group clips by how they look and move — not by task names — and
            prefer groups that are still rare.
          </p>
        </article>
        <article>
          <h2>Repeats</h2>
          <p>
            Whether this clip looks like one we already kept. We compare each
            clip to its nearest neighbor; high similarity means a near-copy.
          </p>
        </article>
      </div>
      <ol className="how">
        <li>
          <strong>Ask</strong>
          <span>Say how much to keep, and what to avoid.</span>
        </li>
        <li>
          <strong>Check</strong>
          <span>See which of those four apply to your request.</span>
        </li>
        <li>
          <strong>Choose</strong>
          <span>Get a keep-set, a comparison, and a why.</span>
        </li>
      </ol>

      <div className="work">
        <p className="kicker">Try it</p>
        <h2>What should we keep from this demo set?</h2>
        <p className="note">
          This demo uses 80 bundled clips. We cannot recognize objects, tasks,
          or whether a robot would succeed.
        </p>
        <label htmlFor="request">Your request</label>
        <textarea
          id="request"
          value={request}
          onChange={(ev) => onChange(ev.target.value)}
          rows={5}
          placeholder="Keep 30%, skip idle clips, and cover as many kinds of motion as we can."
        />
        <p className="examples-label">Start from an example</p>
        <div className="examples">
          {examples.map((ex) => (
            <button
              key={ex.id}
              type="button"
              className={request === ex.request ? "chip on" : "chip"}
              onClick={() => onChange(ex.request)}
            >
              {ex.label}
            </button>
          ))}
        </div>
        {error ? <p className="error">{error}</p> : null}
        <button
          type="button"
          className="primary"
          disabled={busy || !request.trim()}
          onClick={onScope}
        >
          {busy ? "Checking…" : "Check this request"}
        </button>
      </div>
    </section>
  );
}
