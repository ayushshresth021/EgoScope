import { BehaviorCanvas } from "../components/BehaviorCanvas";
import { StepBar } from "../components/StepBar";
import type { RunRecord } from "../api";
import {
  asPercent,
  asScore,
  confidenceLabel,
  methodLabel,
  plainTradeoff,
  recommendationCopy,
} from "../copy";

export function ResultsPage({
  run,
  onRestart,
}: {
  run: RunRecord;
  onRestart: () => void;
}) {
  const analysis = run.analysis;
  const rec = analysis.recommendation;
  const n = analysis.feasibility.n_universe;
  const story = recommendationCopy(rec, analysis.k, n);
  const regions = new Set(analysis.canvas_episodes.map((e) => e.region)).size;
  return (
    <section className="page results-page">
      <StepBar current="results" />
      <p className="kicker">The keep-set</p>
      <div className="banner">
        <h1>{story.title}</h1>
        <p className="lede">{story.body}</p>
        {story.checks.length ? (
          <ol className="checks">
            {story.checks.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ol>
        ) : null}
        <p className="note">
          {confidenceLabel(rec.confidence)}. These numbers come from those
          checks. They do not name tasks or objects, and they do not test
          whether a robot would succeed.
        </p>
      </div>
      <div className="metrics">
        <div>
          <span>Variety kept</span>
          <b>{asPercent(analysis.primary_metrics.behavioral_region_coverage)}</b>
          <em className="hint">Share of motion types still present</em>
        </div>
        <div>
          <span>Clip quality</span>
          <b>{asScore(analysis.primary_metrics.average_quality)}</b>
          <em className="hint">Higher is cleaner motion</em>
        </div>
        <div>
          <span>Repeated motion</span>
          <b>{asScore(analysis.primary_metrics.nn_redundancy)}</b>
          <em className="hint">Lower means less duplication</em>
        </div>
        <div>
          <span>Clips that qualify</span>
          <b>
            {analysis.feasibility.n_eligible}/{n}
          </b>
          <em className="hint">Passed the idle and budget rules</em>
        </div>
        <div>
          <span>Train on</span>
          <b>{analysis.k}</b>
          <em className="hint">Clips in the keep-set</em>
        </div>
      </div>
      {analysis.method_rows.length ? (
        <>
          <h2>What happens if we pick another way</h2>
          <table className="matrix">
            <thead>
              <tr>
                <th>How we picked</th>
                <th>Variety</th>
                <th>Quality</th>
                <th>Repeats</th>
              </tr>
            </thead>
            <tbody>
              {analysis.method_rows.map((row) => (
                <tr key={String(row.method)}>
                  <td>{methodLabel(String(row.method))}</td>
                  <td>{asPercent(row.behavioral_region_coverage)}</td>
                  <td>{asScore(row.average_quality)}</td>
                  <td>{asScore(row.nn_redundancy)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}
      <h2>The clip map</h2>
      <p className="note">
        Each dot is one clip. Dark means keep. Fade means drop. Nearby dots
        are similar motion.
      </p>
      <BehaviorCanvas episodes={analysis.canvas_episodes} nRegions={regions || 6} />
      {analysis.tradeoff ? (
        <p className="tradeoff">{plainTradeoff(analysis.tradeoff)}</p>
      ) : null}
      {analysis.unsupported.length ? (
        <div>
          <h2>We did not try to do this</h2>
          <ul>
            {analysis.unsupported.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="actions">
        <button type="button" className="primary" onClick={onRestart}>
          Start another request
        </button>
      </div>
    </section>
  );
}
