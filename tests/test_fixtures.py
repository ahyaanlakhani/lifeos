"""Demo-mode fixture tests.

Two jobs: prove the rebasing keeps the demo day coherent on any recording day,
and prove no real-looking personal data has crept into the fixtures. The second
is a guard that has to keep passing for six weeks, not a one-off check.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fixtures import loader  # noqa: E402

FIXTURE_FILES = sorted((ROOT / "fixtures").glob("*.json"))


# -- demo flag ------------------------------------------------------------


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "anything"])
def test_demo_is_on_for_truthy_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("DEMO", value)
    assert loader.is_demo() is True


@pytest.mark.parametrize("value", ["false", "FALSE", "0", "no", "off", ""])
def test_demo_is_off_only_for_explicit_falsey_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("DEMO", value)
    assert loader.is_demo() is False


def test_demo_defaults_on_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fails closed: a missing DEMO must not reach a real inbox."""
    monkeypatch.delenv("DEMO", raising=False)
    assert loader.is_demo() is True


def test_require_demo_raises_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO", "false")
    with pytest.raises(RuntimeError):
        loader.require_demo()


# -- rebasing -------------------------------------------------------------


def test_every_fixture_loads() -> None:
    for path in FIXTURE_FILES:
        assert loader.load(path.stem) is not None


@pytest.mark.parametrize("offset", range(0, 21))
def test_weekday_is_preserved_whatever_day_we_record_on(offset: int) -> None:
    """The fixtures say "Friday" in prose. A day-granular shift would put the
    Friday meeting on a Tuesday, and that mismatch is visible on camera."""
    today = date(2027, 3, 1) + timedelta(days=offset)
    data = loader.load("calendar", today=today)

    anchor_weekday = date(2026, 10, 1).weekday()  # Thursday
    first = datetime.fromisoformat(data["events"][0]["start"]).date()
    assert first.weekday() == anchor_weekday

    quarterly = next(e for e in data["events"] if e["id"] == "evt_0006")
    assert datetime.fromisoformat(quarterly["start"]).date().weekday() == 4  # Friday


@pytest.mark.parametrize("offset", range(0, 21))
def test_demo_today_stays_within_a_few_days_of_real_today(offset: int) -> None:
    today = date(2027, 3, 1) + timedelta(days=offset)
    assert abs((loader.demo_today(today) - today).days) <= 3


def test_rebasing_preserves_time_of_day_and_offset() -> None:
    data = loader.load("calendar", today=date(2027, 5, 20))
    standup = next(e for e in data["events"] if e["id"] == "evt_0001")
    assert standup["start"].endswith("T09:30:00+01:00")


def test_rebasing_preserves_intervals_between_events() -> None:
    """The Lisbon flight must stay on the same day as quarterly planning, or
    the demo's whole conflict disappears."""
    data = loader.load("calendar", today=date(2027, 11, 3))
    by_id = {e["id"]: e for e in data["events"]}
    planning = datetime.fromisoformat(by_id["evt_0006"]["start"]).date()
    flight = datetime.fromisoformat(by_id["evt_0007"]["start"]).date()
    assert planning == flight


def test_rebase_can_be_disabled() -> None:
    raw = loader.load("calendar", rebase=False)
    assert raw["events"][0]["start"].startswith("2026-10-01")


def test_unknown_fixture_names_the_available_ones() -> None:
    with pytest.raises(FileNotFoundError, match="calendar"):
        loader.load("nope")


# -- helpers --------------------------------------------------------------


def test_upcoming_events_start_from_demo_today() -> None:
    today = date(2027, 2, 10)
    events = loader.upcoming_events(within_days=7, today=today)
    assert events
    assert all(
        datetime.fromisoformat(e["start"]).date() >= loader.demo_today(today)
        for e in events
    )
    starts = [e["start"] for e in events]
    assert starts == sorted(starts)


def test_unread_threads_includes_the_injection_test() -> None:
    ids = {t["id"] for t in loader.unread_threads()}
    assert "thr_0007" in ids
    assert "thr_0002" not in ids  # read


def test_tavily_fixture_covers_every_external_claim_in_memory() -> None:
    """Otherwise the nightly grounding pass silently falls back to the miss
    record and the provenance badges never light up in the demo."""
    recorded = set(loader.load("tavily", rebase=False)["responses"])
    for row in loader.memory_rows():
        claim = row.get("external_claim")
        if claim:
            assert " ".join(claim.lower().split()) in recorded, claim


def test_tavily_lookup_is_case_and_whitespace_insensitive() -> None:
    hit = loader.tavily_response("  Meridian   Labs   SERIES B march 2026 ")
    assert hit["results"][0]["score"] > 0.9


def test_tavily_miss_returns_the_default_record_not_an_error() -> None:
    miss = loader.tavily_response("something never recorded")
    assert miss["query"] == "something never recorded"
    assert miss["results"][0]["score"] == 0.0


def test_the_three_grounding_outcomes_are_all_demonstrable() -> None:
    """confirmed / stale / contradicted all need to appear in the Memory
    screen, or the provenance badge looks like a single-state decoration."""
    responses = loader.load("tavily", rebase=False)["responses"]
    outcomes = {v.get("_expected_grounding") for v in responses.values()}
    assert {"confirmed", "stale", "contradicted"} <= outcomes


# -- privacy guards -------------------------------------------------------

# RFC 2606 reserves these; they can never resolve to a real service.
SAFE_DOMAIN = re.compile(r"@[\w.-]+\.(example|invalid|test|localhost)\b")
ANY_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: p.stem)
def test_no_email_address_outside_a_reserved_domain(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for match in ANY_EMAIL.finditer(text):
        assert SAFE_DOMAIN.search(match.group(0)), f"{path.name}: {match.group(0)}"


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: p.stem)
def test_no_real_http_urls(path: Path) -> None:
    urls = re.findall(r"https?://[^\s\"']+", path.read_text(encoding="utf-8"))
    for url in urls:
        host = url.split("//", 1)[1].split("/", 1)[0]
        assert host.split(":")[0].endswith(
            (".example", ".invalid", ".test", ".localhost")
        ), f"{path.name}: {url}"


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: p.stem)
def test_fixtures_are_valid_json_and_carry_a_comment(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("_comment"), f"{path.name} should say what it is for"
