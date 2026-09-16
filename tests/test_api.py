"""API smoke tests."""

from fastapi.testclient import TestClient

from egoscope.app import app

client = TestClient(app)


def test_examples_and_scope_run() -> None:
    examples = client.get("/api/examples")
    assert examples.status_code == 200
    names = [row["id"] for row in examples.json()["examples"]]
    assert "unsupported_drawer" in names
    assert "balanced_30" in names

    empty = client.post("/api/scope", json={"request": "  "})
    assert empty.status_code == 400

    scoped = client.post(
        "/api/scope",
        json={"request": "Keep 30% while balancing quality, visual-motion coverage, and redundancy."},
    )
    assert scoped.status_code == 200
    body = scoped.json()
    assert body["can_execute"] is True
    created = client.post(
        "/api/runs",
        json={"confirmed_scope": body["proposed_scope"], "feature_source": "bundled_demo"},
    )
    assert created.status_code == 200
    run_id = created.json()["run_id"]
    fetched = client.get(f"/api/runs/{run_id}")
    assert fetched.status_code == 200
    analysis = fetched.json()["analysis"]
    assert analysis["k"] == 24
    assert "Curation Decision Brief" in fetched.json()["brief"]


def test_unsupported_drawer_api() -> None:
    scoped = client.post("/api/scope", json={"request": "Select drawer-opening demonstrations."})
    body = scoped.json()
    assert body["can_execute"] is False
    created = client.post("/api/runs", json={"confirmed_scope": body["proposed_scope"]})
    assert created.status_code == 200
    fetched = client.get(f"/api/runs/{created.json()['run_id']}")
    assert fetched.json()["analysis"]["recommendation"]["method"] is None
