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
        Robots learn from Egocentric videos, but hours of it are waiting,
        repeats, and the same motion again. Training on all of it is slow
        and expensive.
      </p>

      <h2 className="kicker">What EgoScope does</h2>
      <p className="lede">
        You write what to keep. Every clip is scored on four measurements from
        the footage itself, then we keep a smaller set.
      </p>
      <h2 className="kicker">Where the numbers come from</h2>
      <div className="sources">
        <article>
          <h2>Arm pose</h2>
          <p>
            The capture rig already logs left and right 3D arm positions. Idle,
            speed, and broken tracks come from that stream.
          </p>
        </article>
        <article>
          <h2>A few RGB frames</h2>
          <p>
            We sample eight frames and turn them into a compact visual
            fingerprint. Nearby fingerprints count as near-copies.
          </p>
        </article>
      </div>
      <div className="measures">
        <article>
          <h2>Waiting-around</h2>
          <p>
            How often the arms barely move. If pose speed stays under about
            2&nbsp;cm/s, that part of the clip is idle.
          </p>
        </article>
        <article>
          <h2>Clean motion</h2>
          <p>
            Whether frames decoded, the pose track is complete and finite, and
            whether any arm motion happened at all.
          </p>
        </article>
        <article>
          <h2>Variety of motion</h2>
          <p>
            Whether this clip is a kind of movement we don't already have. We
            group clips by pose stats plus that fingerprint — not by task
            names — and prefer groups that are still rare.
          </p>
        </article>
        <article>
          <h2>Repeats</h2>
          <p>
            Whether this clip's fingerprint sits next to one we already kept.
            High similarity means a near-copy.
          </p>
        </article>
      </div>

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
