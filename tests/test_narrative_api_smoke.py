"""Integration smoke tests for the deployed narrative_api service.

These tests hit the **live** service over Tailscale, exercising every endpoint
against the real ``cypherclaw.narrative`` engine — not a Mock(). They are the
guard against the failure mode documented in
``sdp/postmortem-narrative-api-engine-mismatch.md``: every unit test passed
because every unit test mocked the engine, so the wrapper was free to call
fictional methods. These tests fail if the wrapper-engine surface contract
drifts.

Run requirements:
    - cypherclaw must be reachable on Tailscale (100.74.35.114:8765 default)
    - ``CYPHERCLAW_NARRATIVE_AUTH_TOKEN`` env var set to a valid bearer token
    - ``CYPHERCLAW_NARRATIVE_BASE_URL`` env var (optional; default Tailscale URL)

Skipped automatically if the service isn't reachable (so CI doesn't break
when running outside the tailnet). Run explicitly:

    pytest tests/test_narrative_api_smoke.py -v --no-header

Or from CI on a tailnet runner:

    CYPHERCLAW_NARRATIVE_AUTH_TOKEN=... pytest -m smoke tests/
"""
from __future__ import annotations

import os
import time

import httpx
import pytest


BASE_URL = os.environ.get("CYPHERCLAW_NARRATIVE_BASE_URL", "http://100.74.35.114:8765")
TOKEN = os.environ.get("CYPHERCLAW_NARRATIVE_AUTH_TOKEN", "")


pytestmark = pytest.mark.smoke


@pytest.fixture(scope="module")
def client():
    """A short-timeout client for everything except /beats/next."""
    if not TOKEN:
        pytest.skip("CYPHERCLAW_NARRATIVE_AUTH_TOKEN not set — skipping live smoke tests")
    headers = {"X-Narrative-Auth": TOKEN}
    with httpx.Client(base_url=BASE_URL, headers=headers, timeout=10.0) as cli:
        # Sanity-check reachability up front.
        try:
            r = cli.get("/health", timeout=3.0)
        except httpx.HTTPError:
            pytest.skip(f"narrative_api not reachable at {BASE_URL} — skipping live smoke tests")
        if r.status_code != 200:
            pytest.skip(f"narrative_api returned {r.status_code} on /health — skipping")
        yield cli


# --- Health -----------------------------------------------------------------


def test_health_reports_engine_importable(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")  # ok ideal, degraded acceptable
    # The whole point of the post-mortem rewrite: the engine MUST be importable.
    assert body["narrative_engine_importable"] is True
    assert body["world_db_reachable"] is True


# --- Auth -------------------------------------------------------------------


def test_unauth_request_is_rejected():
    """Belt-and-suspenders: prove auth is on without using the fixture's
    pre-authed client."""
    if not TOKEN:
        pytest.skip("CYPHERCLAW_NARRATIVE_AUTH_TOKEN not set")
    r = httpx.get(f"{BASE_URL}/world/entities", timeout=5.0)
    assert r.status_code == 401


# --- Real engine: events -----------------------------------------------------


def test_events_round_trip_through_real_engine(client):
    """Append an event, then read it back. Confirms WorldState.append_event +
    get_recent_events both work end-to-end."""
    marker = f"smoke-test-{int(time.time())}"
    create = client.post("/events", json={
        "type": "smoke_test",
        "domain": "shared",
        "payload": {"description": marker, "test": True},
    })
    assert create.status_code == 201, create.text
    event_id = create.json()["id"]
    assert event_id

    listing = client.get("/events", params={"limit": 5})
    assert listing.status_code == 200
    events = listing.json()["events"]
    assert any(e["id"] == event_id for e in events), \
        "appended event did not appear in /events listing — engine surface drifted"


# --- Real engine: entities ---------------------------------------------------


def test_entities_create_and_fetch(client):
    """Create + GET-by-id round trip through WorldState.upsert_entity / get_entity."""
    name = f"smoke-entity-{int(time.time())}"
    create = client.post("/world/entities", json={
        "type": "concept",
        "name": name,
        "domain": "shared",
        "properties": {"created_by": "narrative_api_smoke", "tag": name},
    })
    assert create.status_code == 201, create.text
    entity_id = create.json()["id"]
    assert entity_id

    fetched = client.get(f"/world/entities/{entity_id}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["id"] == entity_id
    assert body["name"] == name
    # Confirm the wrapper's domain surfacing is working.
    assert body["domain"] == "shared"


def test_entities_listing_filters_by_domain(client):
    """Domain filter must filter on a real WorldState query, not crash."""
    r = client.get("/world/entities", params={"domain": "shared", "limit": 3})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body.get("entities"), list)
    for ent in body["entities"]:
        assert ent.get("domain") in ("shared", None)  # None acceptable for legacy rows


# --- Real engine: memory -----------------------------------------------------


def test_memory_search_calls_retrieve_similar_beats(client):
    """Confirms NarrativeMemoryAdapter.search → retrieve_similar_beats round trip.

    Pre-rewrite this returned 502 ("NarrativeMemory exposes no semantic_search,
    search, or query method"); post-rewrite it returns ranked hits.
    """
    r = client.post("/memory/search", json={
        "query": "the wanderer searches",
        "k": 3,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "results" in body
    # Order must be similarity-descending; even an empty list is a valid response.
    if body["results"]:
        scores = [hit["similarity"] for hit in body["results"]]
        assert scores == sorted(scores, reverse=True)


# --- Real engine: beats ------------------------------------------------------


@pytest.mark.timeout(120)
def test_beats_next_runs_real_engine(client):
    """``next_beat()`` calls ollama for prose generation. Slow (10-60s), so
    this test gets a generous budget. Marked as the engine's slowest path —
    skip with ``-k 'not beats_next'`` if running tests on a sleepy box."""
    long_client = httpx.Client(
        base_url=BASE_URL,
        headers={"X-Narrative-Auth": TOKEN},
        timeout=90.0,
    )
    try:
        r = long_client.post("/beats/next", json={
            "cycle_number": 999,
            "domain_filter": "shared",
        })
    finally:
        long_client.close()
    # Either a generated beat (200) or a known engine state error (502/503).
    # Anything else means a regression in the wrapper-engine adapter layer.
    assert r.status_code in (200, 502, 503), r.text
    if r.status_code == 200:
        beat = r.json()
        # StoryBeat must serialize through Pydantic — at minimum it has an id
        # and a description-ish field.
        assert beat.get("id") or beat.get("beat_id"), beat
