# EgoScope

**Keep the clips that teach the robot.**

EgoScope turns a natural-language curation request into a confirmed, measurable scope, then ranks first-person clips so you can train on a smaller, better set.

Robots learn from egocentric video, but most of it is waiting around, near-copies, and the same motion again. Training on all of it is slow. Training on the wrong clips teaches the wrong habits.

## What it does

You write what to keep. EgoScope checks whether that request can be measured from the footage, then scores every clip and returns a keep-set, a comparison, and a brief.

Each clip is scored on four measurements from the recording itself:

| Measurement | What it captures |
| --- | --- |
| Waiting-around | How much of the clip the camera is sitting still (pose speed) |
| Clean motion | Missing frames, broken pose tracks, and whether any motion happened |
| Variety of motion | Whether this clip is a kind of movement you do not already have |
| Repeats | Whether this clip looks like one you already kept |

The selector, **EgoSelect**, does not score once and sort. After every pick it rescores the remaining candidates against the set already kept.

Supported request types:

- Keep a fraction or a count of clips
- Find a smallest set that still covers the motion range
- Compare two keep amounts or two picking methods
- See which clips get picked across strategies
- Describe the dataset

Requests that need object names, task labels, or robot success are refused. The demo cannot recognize drawers, kitchens, or whether a policy would succeed.

## Repository layout

```
egoscope/         FastAPI service and run pipeline
egoselect/        Greedy ranking, features, metrics, baselines
requirements/     Request parser, signal registry, feasibility, compiler
analysis/         Method comparison, recommendation rules, decision brief
configs/          Example requests, strategy profiles, signal registry
web/              React + Vite UI (Ask → Check → Results, plus a behavior map)
scripts/          Local API, CLI scoping, selection, experiments
outputs/          Bundled 80-clip feature table and demo payload
tests/            Parser, API, golden, and end-to-end tests
```

Generated run artifacts land in `outputs/runs/` (gitignored). EgoVerse checkouts and raw episode caches belong in `third_party/` and `data/` and are not vendored.

## Quick start

Requires Python 3.10+ and Node 18+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd web
npm install
cd ..
```

### Web app

Start the API, then the UI. Vite proxies `/api` to the backend.

```bash
python scripts/serve.py          # http://127.0.0.1:8000
cd web && npm run dev            # http://127.0.0.1:5173
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Try a request such as:

> Keep 30%, skip idle clips, and cover as many kinds of motion as we can.

The UI walks **Ask → Check → Results**. Confirm the parsed scope before a run. **Watch the map** shows the same 80 bundled clips as a behavior canvas.

### CLI

Parse a request into a proposed scope:

```bash
python scripts/scope_request.py "Keep 30% while balancing quality, visual-motion coverage, and redundancy."
```

Confirm a scope and run EgoSelect plus baselines:

```bash
python scripts/run_scoped_selection.py "Keep 20 episodes and exclude trajectories with more than 25% stationary behavior."
```

Rank the bundled table, sweep methods and budgets, or export the static explorer payload:

```bash
python scripts/run_selection.py
python scripts/run_experiment.py
python scripts/export_demo.py
```

Print a saved run's decision brief:

```bash
python scripts/generate_brief.py <run_id>
```

## Tests

```bash
source .venv/bin/activate
pytest
```

The end-to-end tests run against the bundled 80-episode feature table at `outputs/episode_features.parquet`.

## Bundled demo

This checkout includes an 80-clip feature table so the app and tests run without downloading EgoVerse. Coverage here is unsupervised visual-motion regions, not named robot skills.

Optional: an OpenAI-compatible parser can propose JSON from a request. That proposal is still schema- and registry-validated; fixture matches and heuristics work with no LLM.

## License

No license file is included yet. All rights reserved unless you add one.
