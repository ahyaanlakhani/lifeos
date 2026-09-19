"""Tavily search and the nightly memory-grounding pass.

Offline: demo mode serves recorded responses, so nothing here reaches the
network or spends a credit.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jobs.nightly_synthesis import grounding  # noqa: E402
from packages.agents.research import search as tavily  # noqa: E402


def run(coro: Any) -> Any:
    return asyncio.run(coro)


@pytest.fixture()
def events() -> list[dict[str, Any]]:
    return []


# -- search ---------------------------------------------------------------


def test_demo_search_serves_a_recorded_response(events: list[dict[str, Any]]) -> None:
    results = run(tavily.search("Meridian Labs Series B March 2026", emit=events.append, demo=True))
    assert results[0]["url"].endswith("meridian-labs-series-b")


def test_every_search_emits_an_event_even_in_demo_mode(events: list[dict[str, Any]]) -> None:
    """A timeline that silently omits searches when the data is synthetic would
    be lying about what ran. "No silent work" has no demo exemption."""
    run(tavily.search("anything at all", emit=events.append, demo=True))
    assert events[0]["kind"] == "search"
    assert events[0]["agent"] == "research"
    assert events[0]["detail"]["source"] == "fixture"


def test_a_search_with_no_fixture_returns_the_miss_record(events: list[dict[str, Any]]) -> None:
    results = run(tavily.search("never recorded", emit=events.append, demo=True))
    assert results[0]["score"] == 0.0


def test_max_results_is_respected(events: list[dict[str, Any]]) -> None:
    results = run(
        tavily.search(
            "Meridian Labs vendor comparison deployment timelines",
            max_results=1,
            emit=events.append,
            demo=True,
        )
    )
    assert len(results) == 1


def test_a_live_search_without_a_key_refuses_rather_than_falling_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Silently serving fixtures outside demo mode would make a broken
    deployment look like a working one."""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(tavily.TavilyError, match="TAVILY_API_KEY"):
        run(tavily.search("x", demo=False))


def test_the_auth_convention_is_marked_unverified() -> None:
    """Tavily's auth header has changed across versions. Confirm against the
    current docs before the first live call, then flip this."""
    assert tavily.AUTH_VERIFIED is False


def test_the_tool_definition_translates_for_token_factory() -> None:
    sys.path.insert(0, str(ROOT / "packages" / "inference"))
    from tools import to_openai_tool

    converted = to_openai_tool(tavily.as_tool())
    assert converted["function"]["name"] == "web_search"
    assert "query" in converted["function"]["parameters"]["properties"]


# -- grounding ------------------------------------------------------------


def test_a_row_with_no_external_claim_is_left_unverified() -> None:
    record = run(grounding.ground_row({"id": "m1", "text": "I like tea", "external_claim": None}))
    assert record["status"] == "unverified"
    assert record["last_checked"] is None


def test_the_three_verdicts_all_come_out_of_the_seed_data(tmp_path: Path) -> None:
    """confirmed, stale and contradicted all need to appear, or the provenance
    badge looks like a single-state decoration."""
    results = run(grounding.run(state_path=tmp_path / "g.json", demo=True))
    statuses = {r["status"] for r in results.values()}
    assert statuses == {"confirmed", "stale", "contradicted"}


def test_grounding_writes_state_that_can_be_read_back(tmp_path: Path) -> None:
    path = tmp_path / "g.json"
    written = run(grounding.run(state_path=path, demo=True))
    assert grounding.load_state(path) == json.loads(path.read_text(encoding="utf-8"))
    assert set(grounding.load_state(path)) == set(written)


def test_missing_state_grounds_nothing_rather_than_failing(tmp_path: Path) -> None:
    """A stale badge is worth less than a working page."""
    assert grounding.load_state(tmp_path / "absent.json") == {}


def test_corrupt_state_is_tolerated(tmp_path: Path) -> None:
    path = tmp_path / "g.json"
    path.write_text("{ not json", encoding="utf-8")
    assert grounding.load_state(path) == {}


def test_grounding_records_the_sources_it_used(tmp_path: Path) -> None:
    results = run(grounding.run(state_path=tmp_path / "g.json", demo=True))
    for record in results.values():
        assert record["sources"], "a badge with no source is not provenance"


def test_a_failing_row_does_not_lose_the_whole_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, events: list[dict[str, Any]]
) -> None:
    calls = {"n": 0}

    async def flaky(query: str, **kwargs: Any) -> list[dict[str, Any]]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("network hiccup")
        return [{"url": "https://x.example", "content": "fine"}]

    monkeypatch.setattr(tavily, "search", flaky)
    results = run(grounding.run(state_path=tmp_path / "g.json", emit=events.append, demo=True))

    assert len(results) == 3
    assert any(e["kind"] == "error" for e in events)
    assert sum(1 for r in results.values() if "check failed" in (r.get("note") or "")) == 1


def test_grounding_emits_one_summary_event_for_the_run(
    tmp_path: Path, events: list[dict[str, Any]]
) -> None:
    run(grounding.run(state_path=tmp_path / "g.json", emit=events.append, demo=True))
    summaries = [e for e in events if e["kind"] == "memory_write"]
    assert len(summaries) == 1
    assert summaries[0]["detail"]["checked"] == 3


# -- the model judge ------------------------------------------------------


class FakeClient:
    def __init__(self, verdict: str) -> None:
        self.verdict = verdict
        self.tasks: list[str] = []

    async def complete(self, task: str, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        self.tasks.append(task)

        class Choice:
            message = {"content": self.verdict}

        class Response:
            choices = [Choice()]

        return Response()


def test_the_judge_runs_on_the_planning_tier() -> None:
    """Long-horizon reasoning, nightly, off the hot path — exactly what Ultra
    is for, and cheap enough because it is not in the request path."""
    client = FakeClient("confirmed")
    run(grounding.ground_row(
        {"id": "m", "text": "x", "external_claim": "Meridian Labs Series B March 2026"},
        client=client,
        demo=True,
    ))
    assert client.tasks == ["plan"]


@pytest.mark.parametrize(
    ("verdict", "expected"),
    [
        ("confirmed", "confirmed"),
        ("  STALE  ", "stale"),
        ("contradicted", "contradicted"),
        ("The results say this is contradicted, because...", "contradicted"),
        ("I'm not sure about this one", "unverified"),
        ("", "unverified"),
    ],
)
def test_a_chatty_verdict_is_still_parsed(verdict: str, expected: str) -> None:
    """Models add a sentence even when told not to. Anything unrecognised
    falls back to unverified — an unparsed verdict must never read as
    confirmed."""
    record = run(grounding.ground_row(
        {"id": "m", "text": "x", "external_claim": "Meridian Labs Series B March 2026"},
        client=FakeClient(verdict),
        demo=True,
    ))
    assert record["status"] == expected


def test_without_a_client_outside_demo_mode_nothing_is_claimed_as_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The search can succeed and the verdict still be unknown. Saying
    "unverified" is the only honest answer with nothing to judge with."""

    async def fake_search(query: str, **kwargs: Any) -> list[dict[str, Any]]:
        return [{"url": "https://x.example", "content": "something"}]

    monkeypatch.setattr(tavily, "search", fake_search)
    record = run(grounding.ground_row(
        {"id": "m", "text": "x", "external_claim": "q"},
        client=None,
        demo=False,
    ))
    assert record["status"] == "unverified"
    assert "no inference client" in record["note"]


def test_grounding_outside_demo_mode_without_a_key_fails_loudly_per_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, events: list[dict[str, Any]]
) -> None:
    """Rather than silently serving fixtures, which would make a broken
    deployment look like a working one."""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    results = run(grounding.run(state_path=tmp_path / "g.json", emit=events.append, demo=False))
    assert all(r["status"] == "unverified" for r in results.values())
    assert all("check failed" in r["note"] for r in results.values())
    assert any(e["kind"] == "error" for e in events)
