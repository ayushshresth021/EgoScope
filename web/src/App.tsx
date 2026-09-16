import { useState } from "react";
import ExplorerApp from "./ExplorerApp";
import {
  createRun,
  fetchRun,
  scopeRequest,
  type RunRecord,
  type Scope,
  type ScopeProposal,
} from "./api";
import { RequestPage } from "./pages/RequestPage";
import { ResultsPage } from "./pages/ResultsPage";
import { ScopePage } from "./pages/ScopePage";
import { TAGLINE } from "./copy";
import "./App.css";
import "./EgoScope.css";

type Screen = "request" | "scope" | "results" | "explorer";

export default function App() {
  const [screen, setScreen] = useState<Screen>("request");
  const [request, setRequest] = useState(
    "Keep 30%, avoid idle-heavy episodes, and prioritize broad behavior.",
  );
  const [proposal, setProposal] = useState<ScopeProposal | null>(null);
  const [scope, setScope] = useState<Scope | null>(null);
  const [run, setRun] = useState<RunRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onScope() {
    setBusy(true);
    setError(null);
    try {
      const next = await scopeRequest(request);
      setProposal(next);
      setScope(next.proposed_scope);
      setScreen("scope");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scope failed");
    } finally {
      setBusy(false);
    }
  }

  async function onConfirm() {
    if (!scope) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createRun(scope);
      const record = await fetchRun(created.run_id);
      setRun(record);
      setScreen("results");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Run failed");
    } finally {
      setBusy(false);
    }
  }

  function restart() {
    setProposal(null);
    setScope(null);
    setRun(null);
    setError(null);
    setScreen("request");
  }

  return (
    <div className="egoscope">
      <nav className="nav">
        <div className="nav-brand">
          <strong>EgoScope</strong>
          <small>{TAGLINE}</small>
        </div>
        <button
          type="button"
          className={screen !== "explorer" ? "on" : ""}
          onClick={() => {
            if (run) setScreen("results");
            else if (proposal && scope) setScreen("scope");
            else setScreen("request");
          }}
        >
          Try a request
        </button>
        <button type="button" className={screen === "explorer" ? "on" : ""} onClick={() => setScreen("explorer")}>
          Watch the map
        </button>
      </nav>
      {screen === "explorer" ? (
        <ExplorerApp />
      ) : screen === "request" ? (
        <RequestPage
          request={request}
          onChange={setRequest}
          onScope={onScope}
          busy={busy}
          error={error}
        />
      ) : screen === "scope" && proposal && scope ? (
        <ScopePage
          proposal={proposal}
          scope={scope}
          onChange={setScope}
          onConfirm={onConfirm}
          busy={busy}
          error={error}
          onBack={() => setScreen("request")}
        />
      ) : screen === "results" && run ? (
        <ResultsPage run={run} onRestart={restart} />
      ) : (
        <RequestPage
          request={request}
          onChange={setRequest}
          onScope={onScope}
          busy={busy}
          error={error}
        />
      )}
    </div>
  );
}
