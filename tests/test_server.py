"""Agent host API tests.

The six endpoints are the contract between Glass Box and the host, and they
have to stay stable even when what sits behind approvals changes. These tests
are that contract written down.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT / "apps" / "host", ROOT / "packages" / "inference"):
    sys.path.insert(0, str(extra))

import nemoclaw  # noqa: E402
from events import parse_log_line  # noqa: E402
from nemoclaw import FakeDriver  # noqa: E402
from server import Host, create_app  # noqa: E402


@pytest.fixture()
def routing_file(tmp_path: Path) -> Path:
    path = tmp_path / "routing.yaml"
    path.write_text(
        "# routing header comment, must survive a rewrite\n"
        'plan: "ultra-id"\n'
        'execute: "super-id"\n'
        'summarize: "nano-id"\n',
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def host(tmp_path: Path, routing_file: Path) -> Host:
    return Host(
        driver=FakeDriver(speed=1000),
        data_dir=tmp_path / "sessions",
        routing_path=routing_file,
        session="test-session",
    )


@pytest.fixture()
def api(host: Host) -> Iterator[TestClient]:
    with TestClient(create_app(host, background=False)) as client:
        yield client


def feed_script(host: Host) -> None:
    """Push the scripted session through the parser, as run_tail would."""
    for _, _, line in nemoclaw.SCRIPT:
        event = parse_log_line(line, host.session)
        if event is not None:
            host.log.append(event)
        if line.startswith("BLOCK"):
            request = nemoclaw._parse_block_line(line)
            if request:
                host.driver._pending[request.id] = request


# -- health ---------------------------------------------------------------


def test_health_reports_the_session_and_driver(api: TestClient) -> None:
    body = api.get("/api/health").json()
    assert body["ok"] is True
    assert body["session"] == "test-session"
    assert body["driver"] == "FakeDriver"


# -- 1. GET /api/events ---------------------------------------------------


def test_events_backfill_is_empty_on_a_fresh_host(api: TestClient) -> None:
    assert api.get("/api/events").json()["events"] == []


def test_events_backfill_returns_the_whole_session(api: TestClient, host: Host) -> None:
    feed_script(host)
    body = api.get("/api/events").json()
    assert len(body["events"]) == len(nemoclaw.SCRIPT)
    assert body["session"] == "test-session"


def test_events_since_filters_to_newer_only(api: TestClient, host: Host) -> None:
    first = host.log.emit("action", "system", "old")
    second = host.log.emit("action", "system", "new")
    second.ts = first.ts + 100

    body = api.get("/api/events", params={"since": first.ts + 1}).json()
    assert [e["summary"] for e in body["events"]] == ["new"]


def test_events_respects_a_limit(api: TestClient, host: Host) -> None:
    for i in range(10):
        host.log.emit("action", "system", f"e{i}")
    body = api.get("/api/events", params={"limit": 3}).json()
    assert [e["summary"] for e in body["events"]] == ["e7", "e8", "e9"]


def test_events_rejects_an_absurd_limit(api: TestClient) -> None:
    assert api.get("/api/events", params={"limit": 999999}).status_code == 422


def test_parsed_log_events_arrive_pending_a_summary(api: TestClient, host: Host) -> None:
    """Glass Box dims these until Nano's one-liner lands."""
    feed_script(host)
    events = api.get("/api/events").json()["events"]
    assert all(e["summary_pending"] for e in events)
    assert {e["kind"] for e in events} >= {"action", "egress_request", "memory_write", "search"}


# -- 2. WS /api/stream ----------------------------------------------------


def test_the_stream_replays_recent_events_on_connect(api: TestClient, host: Host) -> None:
    host.log.emit("action", "calendar", "before you connected")
    with api.websocket_connect("/api/stream") as ws:
        assert ws.receive_json()["summary"] == "before you connected"


def test_the_stream_pushes_new_events_live(api: TestClient, host: Host) -> None:
    with api.websocket_connect("/api/stream") as ws:
        host.log.emit("action", "email", "live one")
        assert ws.receive_json()["summary"] == "live one"


def test_the_stream_delivers_a_summary_patch_as_a_second_message(
    api: TestClient, host: Host
) -> None:
    with api.websocket_connect("/api/stream") as ws:
        event = host.log.emit("action", "email", "raw line", summary_pending=True)
        assert ws.receive_json()["summary_pending"] is True

        host.log.patch_summary(event.id, "Sent the reply")
        patched = ws.receive_json()
        assert patched["id"] == event.id
        assert patched["summary"] == "Sent the reply"
        assert patched["summary_pending"] is False


def test_a_disconnected_client_is_unsubscribed(api: TestClient, host: Host) -> None:
    with api.websocket_connect("/api/stream"):
        pass
    host.log.emit("action", "system", "after disconnect")
    assert len(host.log) == 1  # no exception raised by a dead subscriber


# -- 3 & 4. approvals -----------------------------------------------------


def test_approvals_are_empty_until_something_is_blocked(api: TestClient) -> None:
    assert api.get("/api/approvals").json()["approvals"] == []


def test_a_blocked_egress_surfaces_as_an_approval_card(api: TestClient, host: Host) -> None:
    feed_script(host)
    approvals = api.get("/api/approvals").json()["approvals"]
    assert len(approvals) == 1
    card = approvals[0]
    assert card["agent"] == "email"
    assert card["host"] == "1ifeos-support.example"
    assert card["reason"] == "not_in_allowlist"


def test_denying_from_the_phone_clears_the_card_and_logs_the_block(
    api: TestClient, host: Host
) -> None:
    """The strongest thirty seconds of the demo video."""
    feed_script(host)
    response = api.post("/api/approvals/req_7a1c", json={"decision": "deny", "scope": "always"})
    assert response.status_code == 200
    assert response.json()["decision"] == "deny"

    assert api.get("/api/approvals").json()["approvals"] == []
    decisions = [e for e in api.get("/api/events").json()["events"] if e["kind"] == "egress_decision"]
    assert len(decisions) == 1
    assert decisions[0]["detail"]["decision"] == "deny"


def test_allowing_is_also_recorded(api: TestClient, host: Host) -> None:
    feed_script(host)
    api.post("/api/approvals/req_7a1c", json={"decision": "allow", "scope": "once"})
    assert host.driver.decisions[0][1].value == "allow"


def test_deciding_an_unknown_approval_is_a_404(api: TestClient) -> None:
    assert api.post("/api/approvals/ghost", json={"decision": "deny"}).status_code == 404


@pytest.mark.parametrize(
    "body",
    [{}, {"decision": "maybe"}, {"decision": "deny", "scope": "forever"}, {"scope": "once"}],
)
def test_a_malformed_decision_is_rejected(api: TestClient, body: dict[str, Any]) -> None:
    assert api.post("/api/approvals/req_7a1c", json=body).status_code == 422


def test_scope_defaults_to_once(api: TestClient, host: Host) -> None:
    feed_script(host)
    body = api.post("/api/approvals/req_7a1c", json={"decision": "deny"}).json()
    assert body["scope"] == "once"


def test_a_scope_the_backend_cannot_honour_is_a_conflict_not_a_silent_allow(
    api: TestClient, host: Host
) -> None:
    """The policy-file fallback cannot express a one-shot allow. Saying so
    beats punching a permanent hole in the policy."""

    async def refuse(*_: Any, **__: Any) -> bool:
        raise NotImplementedError("scope=once cannot be expressed in a policy file")

    host.driver.decide_egress = refuse  # type: ignore[assignment]
    response = api.post("/api/approvals/req_7a1c", json={"decision": "allow", "scope": "once"})
    assert response.status_code == 409
    assert "policy file" in response.json()["detail"]


# -- 5. GET /api/memory/diff ----------------------------------------------


def test_memory_diff_returns_only_memory_writes(api: TestClient, host: Host) -> None:
    feed_script(host)
    changes = api.get("/api/memory/diff").json()["changes"]
    assert changes
    assert {c["kind"] for c in changes} == {"memory_write"}


def test_memory_diff_respects_a_limit(api: TestClient, host: Host) -> None:
    for i in range(5):
        host.log.emit("memory_write", "system", f"w{i}")
    assert len(api.get("/api/memory/diff", params={"limit": 2}).json()["changes"]) == 2


# -- 6. routing -----------------------------------------------------------


def test_routing_is_readable(api: TestClient) -> None:
    body = api.get("/api/routing").json()
    assert body["routing"]["execute"] == "super-id"
    assert body["tasks"] == ["plan", "execute", "summarize"]


def test_flipping_super_to_ultra_takes_effect_immediately(
    api: TestClient, routing_file: Path
) -> None:
    """The 2:30 beat: switch tiers mid-task and the cost meter moves."""
    body = api.post("/api/routing", json={"execute": "ultra-id"}).json()
    assert body["routing"]["execute"] == "ultra-id"
    assert api.get("/api/routing").json()["routing"]["execute"] == "ultra-id"
    assert 'execute: "ultra-id"' in routing_file.read_text(encoding="utf-8")


def test_a_routing_change_leaves_the_other_tasks_alone(api: TestClient) -> None:
    api.post("/api/routing", json={"execute": "ultra-id"})
    routing = api.get("/api/routing").json()["routing"]
    assert routing["plan"] == "ultra-id"
    assert routing["summarize"] == "nano-id"


def test_a_routing_change_is_logged_as_an_event(api: TestClient) -> None:
    api.post("/api/routing", json={"execute": "ultra-id"})
    summaries = [e["summary"] for e in api.get("/api/events").json()["events"]]
    assert any("Routing changed" in s for s in summaries)


def test_the_routing_file_stays_human_readable_after_a_rewrite(
    api: TestClient, routing_file: Path
) -> None:
    api.post("/api/routing", json={"summarize": "nano-2"})
    text = routing_file.read_text(encoding="utf-8")
    assert text.startswith("# routing header comment")


@pytest.mark.parametrize("body", [{}, {"nonsense": "x"}, {"execute": ""}, {"execute": 7}])
def test_a_malformed_routing_change_is_rejected(api: TestClient, body: dict[str, Any]) -> None:
    assert api.post("/api/routing", json=body).status_code == 422


# -- sandbox lifecycle ----------------------------------------------------


def test_a_sandbox_can_be_started_and_stopped_over_the_api(api: TestClient) -> None:
    started = api.post("/api/sandboxes/calendar/start").json()
    assert started["state"] == "running"

    assert [s["agent"] for s in api.get("/api/sandboxes").json()["sandboxes"]] == ["calendar"]

    api.post(f"/api/sandboxes/{started['id']}/stop")
    assert api.get("/api/sandboxes").json()["sandboxes"][0]["state"] == "stopped"


def test_an_out_of_scope_agent_cannot_be_started(api: TestClient) -> None:
    """CRM, Networking, Internship and Content are pre-existing and out of
    scope. The host should not quietly accept them."""
    response = api.post("/api/sandboxes/crm/start")
    assert response.status_code == 400
    assert "crm" in response.json()["detail"]


# -- 5b. GET /api/memory --------------------------------------------------


def test_memory_serves_the_seed_rows_in_demo_mode(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO", "true")
    body = api.get("/api/memory").json()
    assert body["source"] == "fixtures"
    assert len(body["rows"]) >= 10


def test_every_memory_row_carries_a_grounding_status(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Memory screen renders a badge per row, so a row without a status
    would render as a hole rather than as `unverified`."""
    monkeypatch.setenv("DEMO", "true")
    for row in api.get("/api/memory").json()["rows"]:
        assert row["grounding"]["status"]


def test_memory_outside_demo_mode_returns_empty_rather_than_fixtures(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A misconfigured deployment must show an empty memory, never a fake one
    that looks like real recall."""
    monkeypatch.setenv("DEMO", "false")
    body = api.get("/api/memory").json()
    assert body["source"] == "supabase"
    assert body["rows"] == []


# -- inference readiness --------------------------------------------------


def test_the_host_declines_to_build_a_client_while_ids_are_placeholders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise every summarization batch would emit an error, and the
    timeline would fill with noise about a key that was never set."""
    monkeypatch.setenv("NEBIUS_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("NEBIUS_API_KEY", "not-a-real-key")
    placeholder = tmp_path / "routing.yaml"
    placeholder.write_text(
        'plan: "TODO/ultra"\nexecute: "TODO/super"\nsummarize: "TODO/nano"\n', encoding="utf-8"
    )

    host = Host(
        driver=FakeDriver(speed=1000),
        data_dir=tmp_path / "s",
        routing_path=placeholder,
        session="x",
    )
    assert host.inference_ready is False
    assert host.summarizer is None


def test_the_host_declines_to_build_a_client_with_no_credentials(
    tmp_path: Path, routing_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NEBIUS_BASE_URL", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    host = Host(
        driver=FakeDriver(speed=1000), data_dir=tmp_path / "s", routing_path=routing_file, session="x"
    )
    assert host.inference_ready is False


def test_the_host_builds_a_client_once_both_are_in_place(
    tmp_path: Path, routing_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEBIUS_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("NEBIUS_API_KEY", "not-a-real-key")
    host = Host(
        driver=FakeDriver(speed=1000), data_dir=tmp_path / "s", routing_path=routing_file, session="x"
    )
    assert host.inference_ready is True
    assert host.summarizer is not None


def test_health_reports_whether_inference_is_ready(api: TestClient) -> None:
    assert api.get("/api/health").json()["inference_ready"] in (True, False)


# -- replay ---------------------------------------------------------------


def test_sessions_lists_the_live_one(api: TestClient, host: Host) -> None:
    host.log.emit("action", "system", "something")
    rows = api.get("/api/sessions").json()["sessions"]
    assert [r["session"] for r in rows] == ["test-session"]
    assert rows[0]["live"] is True


def test_sessions_are_newest_first(api: TestClient, host: Host, tmp_path: Path) -> None:
    import os, time

    host.log.emit("action", "system", "live")
    older = host.log.path.parent / "20200101-000000-aaaaaa.jsonl"
    older.write_text("", encoding="utf-8")
    os.utime(older, (0, 0))

    rows = api.get("/api/sessions").json()["sessions"]
    assert rows[0]["session"] == "test-session"
    assert rows[-1]["session"] == "20200101-000000-aaaaaa"


def test_a_past_session_replays_from_disk(api: TestClient, host: Host) -> None:
    """Read off disk, not from memory, so a session recorded before a restart
    is still replayable — which is the point of writing JSONL at all."""
    a = host.log.emit("action", "calendar", "raw line", summary_pending=True)
    host.log.emit("search", "research", "searched")
    host.log.patch_summary(a.id, "Checked the week")

    body = api.get("/api/sessions/test-session").json()
    assert [e["summary"] for e in body["events"]] == ["Checked the week", "searched"]
    assert body["events"][0]["summary_pending"] is False
    assert body["started"] <= body["ended"]


def test_an_unknown_session_is_a_404(api: TestClient) -> None:
    assert api.get("/api/sessions/nope").status_code == 404


@pytest.mark.parametrize("bad", ["../secrets", "a/b", "..%2F..%2Fetc"])
def test_a_traversal_attempt_is_rejected(api: TestClient, bad: str) -> None:
    """The session id lands in a filesystem path. It does not get to contain
    a path."""
    assert api.get(f"/api/sessions/{bad}").status_code in (400, 404)


def test_an_empty_session_replays_as_empty(api: TestClient, host: Host) -> None:
    (host.log.path.parent / "empty-one.jsonl").write_text("", encoding="utf-8")
    body = api.get("/api/sessions/empty-one").json()
    assert body["events"] == []
    assert body["started"] is None
