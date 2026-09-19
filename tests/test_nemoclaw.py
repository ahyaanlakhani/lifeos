"""Sandbox driver tests.

The real CLI is alpha and not installed here, so these cover the parts that do
not depend on its syntax: the driver contract, the fake driver that demo mode
runs on, the policy-file fallback for approvals, and the refusal to pretend.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "host"))

import nemoclaw  # noqa: E402
from nemoclaw import (  # noqa: E402
    AGENTS,
    Decision,
    EgressRequest,
    FakeDriver,
    NemoClawDriver,
    PolicyFileEgress,
    SandboxState,
    Scope,
    build_driver,
)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


async def drain(iterator: Any, limit: int = 100) -> list[str]:
    out: list[str] = []
    async for item in iterator:
        out.append(item)
        if len(out) >= limit:
            break
    return out


# -- the fake driver, which is how demo mode works ------------------------


def test_fake_driver_starts_only_the_three_ported_agents() -> None:
    driver = FakeDriver()
    for agent in AGENTS:
        info = run(driver.start(agent))
        assert info.state is SandboxState.RUNNING

    with pytest.raises(ValueError, match="crm"):
        run(driver.start("crm"))


def test_fake_driver_replays_the_scripted_session() -> None:
    driver = FakeDriver(speed=1000)
    lines = run(drain(driver.tail()))
    assert len(lines) == len(nemoclaw.SCRIPT)
    assert any("tavily_search" in line for line in lines)


def test_the_script_covers_every_beat_the_demo_needs() -> None:
    """If a beat drops out of the script the video loses it silently."""
    text = "\n".join(line for _, _, line in nemoclaw.SCRIPT)
    assert "conflict" in text                      # calendar finds the clash
    assert "tavily_search" in text                 # Tavily runtime call
    assert "instructions addressed to the agent" in text  # injection declined
    assert "BLOCK" in text                         # egress blocked
    assert "memory_write" in text                  # memory changes
    assert "awaiting_approval" in text             # nothing sent unasked


def test_a_blocked_line_becomes_a_pending_approval() -> None:
    driver = FakeDriver(speed=1000)
    run(drain(driver.tail()))
    pending = run(driver.pending_egress())
    assert len(pending) == 1
    assert pending[0].host == "1ifeos-support.example"
    assert pending[0].agent == "email"
    assert pending[0].id == "req_7a1c"


def test_deciding_an_approval_clears_it_and_records_the_decision() -> None:
    driver = FakeDriver(speed=1000)
    run(drain(driver.tail()))
    assert run(driver.decide_egress("req_7a1c", Decision.DENY, Scope.ALWAYS)) is True
    assert run(driver.pending_egress()) == []
    assert driver.decisions == [("req_7a1c", Decision.DENY, Scope.ALWAYS)]


def test_deciding_an_unknown_approval_reports_failure_rather_than_pretending() -> None:
    assert run(FakeDriver().decide_egress("nope", Decision.ALLOW, Scope.ONCE)) is False


def test_stopping_marks_the_sandbox_stopped() -> None:
    driver = FakeDriver()
    info = run(driver.start("calendar"))
    run(driver.stop(info.id))
    assert run(driver.status())[0].state is SandboxState.STOPPED


# -- driver selection -----------------------------------------------------


def test_demo_mode_gets_the_fake_driver() -> None:
    assert isinstance(build_driver(demo=True), FakeDriver)


def test_the_demo_flag_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEMO", raising=False)
    assert isinstance(build_driver(), FakeDriver)


def test_outside_demo_mode_a_missing_binary_refuses_to_fall_back() -> None:
    """A fake sandbox pretending to be a real one is the worst outcome here."""
    with pytest.raises(RuntimeError, match="Refusing to fall back"):
        build_driver(demo=False, binary="definitely-not-installed-nemoclaw")


# -- the real driver's non-CLI logic --------------------------------------


def test_the_command_table_is_marked_unverified() -> None:
    """Flip COMMANDS_VERIFIED only after reading `nemoclaw --help`. This test
    is a reminder that fails loudly the day someone flips it carelessly."""
    assert nemoclaw.COMMANDS_VERIFIED is False, (
        "COMMANDS_VERIFIED is True — update this test and confirm every entry "
        "in COMMANDS was checked against the real CLI."
    )


def test_an_agent_without_a_policy_cannot_be_started() -> None:
    """An agent with no allowlist would run unconstrained, which is the one
    thing this project exists to prevent."""
    driver = NemoClawDriver(policy_dir=ROOT / "infra" / "policies")
    with pytest.raises(FileNotFoundError, match="crm"):
        driver.policy_for("crm")


def test_every_ported_agent_has_a_policy_on_disk() -> None:
    driver = NemoClawDriver(policy_dir=ROOT / "infra" / "policies")
    for agent in AGENTS:
        assert driver.policy_for(agent).exists()


def allowlist(agent: str) -> list[str]:
    """The parsed allow list, not the file text — a host named in a comment is
    documentation, not permission."""
    yaml = pytest.importorskip("yaml")
    policy = yaml.safe_load((ROOT / "infra" / "policies" / f"{agent}.yaml").read_text(encoding="utf-8"))
    return list(policy["egress"]["allow"])


def test_the_calendar_agent_cannot_reach_tavily() -> None:
    """The point made on camera at 1:25. A regression here is invisible in the
    UI and fatal to the demo's argument."""
    assert "api.tavily.com" not in allowlist("calendar")
    assert "api.tavily.com" in allowlist("research")


def test_the_research_agent_cannot_reach_the_inbox_or_calendar() -> None:
    """Research reads the web, not your mail. Minimal allowlists are the
    substance behind the governance claim."""
    assert not [host for host in allowlist("research") if "googleapis.com" in host]


def test_the_email_agent_has_send_scope_only_and_no_calendar_access() -> None:
    hosts = allowlist("email")
    assert "gmail.googleapis.com" in hosts
    assert "www.googleapis.com" not in hosts


@pytest.mark.parametrize("agent", AGENTS)
def test_every_policy_denies_by_default(agent: str) -> None:
    yaml = pytest.importorskip("yaml")
    policy = yaml.safe_load((ROOT / "infra" / "policies" / f"{agent}.yaml").read_text(encoding="utf-8"))
    assert policy["egress"]["deny_by_default"] is True


@pytest.mark.parametrize("agent", AGENTS)
def test_every_agent_can_reach_inference_and_memory_and_nothing_stray(agent: str) -> None:
    hosts = allowlist(agent)
    assert any("nebius" in h for h in hosts), "no Token Factory host — the agent cannot think"
    assert any("supabase" in h for h in hosts), "no memory store"
    assert len(hosts) <= 5, f"{agent} allowlist is growing: {hosts}"


def test_status_falls_back_to_tracked_state_when_json_is_unavailable() -> None:
    """An alpha CLI may not honour --json. Losing the status screen over that
    would be a bad trade."""
    driver = NemoClawDriver()
    driver._sandboxes["x"] = nemoclaw.SandboxInfo("x", "calendar", SandboxState.RUNNING, 0.0)

    async def fake_run(key: str, **_: Any) -> str:
        return "not json at all"

    driver._run = fake_run  # type: ignore[assignment]
    assert [s.id for s in run(driver.status())] == ["x"]


def test_status_parses_a_json_listing() -> None:
    driver = NemoClawDriver()

    async def fake_run(key: str, **_: Any) -> str:
        return '[{"name": "lifeos-email", "status": "running", "started_at": 1.0}]'

    driver._run = fake_run  # type: ignore[assignment]
    info = run(driver.status())[0]
    assert info.agent == "email"
    assert info.state is SandboxState.RUNNING


# -- the policy-file fallback for approvals -------------------------------


@pytest.fixture()
def policy_dir(tmp_path: Path) -> Path:
    (tmp_path / "research.yaml").write_text(
        "agent: research\negress:\n  allow:\n    - api.tavily.com\n  deny_by_default: true\n",
        encoding="utf-8",
    )
    return tmp_path


def request_for(host: str = "api.example") -> EgressRequest:
    return EgressRequest(id="r1", agent="research", host=host, reason="test", requested_at=1.0)


def test_policy_fallback_denying_needs_no_file_write(policy_dir: Path) -> None:
    driver = NemoClawDriver(policy_dir=policy_dir)
    egress = PolicyFileEgress(driver, policy_dir)
    egress.observe(request_for())

    before = (policy_dir / "research.yaml").read_text(encoding="utf-8")
    assert run(egress.decide("r1", Decision.DENY, Scope.ALWAYS)) is True
    assert (policy_dir / "research.yaml").read_text(encoding="utf-8") == before
    assert run(egress.pending()) == []


def test_policy_fallback_allowing_always_extends_the_allowlist(policy_dir: Path) -> None:
    driver = NemoClawDriver(policy_dir=policy_dir)

    async def noop_status() -> list[Any]:
        return []

    driver.status = noop_status  # type: ignore[assignment]
    egress = PolicyFileEgress(driver, policy_dir)
    egress.observe(request_for("api.newthing.example"))

    assert run(egress.decide("r1", Decision.ALLOW, Scope.ALWAYS)) is True
    text = (policy_dir / "research.yaml").read_text(encoding="utf-8")
    assert "- api.newthing.example" in text
    assert "Glass Box approval" in text
    assert text.index("- api.tavily.com") != text.index("- api.newthing.example")


def test_policy_fallback_refuses_a_one_shot_allow_it_cannot_express(policy_dir: Path) -> None:
    """Honest failure beats a permanent hole punched in the policy because the
    UI offered a scope the backend cannot honour."""
    egress = PolicyFileEgress(NemoClawDriver(policy_dir=policy_dir), policy_dir)
    egress.observe(request_for())
    with pytest.raises(NotImplementedError, match="scope=once"):
        run(egress.decide("r1", Decision.ALLOW, Scope.ONCE))


def test_policy_fallback_on_an_unknown_request_returns_false(policy_dir: Path) -> None:
    egress = PolicyFileEgress(NemoClawDriver(policy_dir=policy_dir), policy_dir)
    assert run(egress.decide("ghost", Decision.DENY, Scope.ONCE)) is False


def test_policy_fallback_is_idempotent_on_a_host_already_allowed(policy_dir: Path) -> None:
    driver = NemoClawDriver(policy_dir=policy_dir)

    async def noop_status() -> list[Any]:
        return []

    driver.status = noop_status  # type: ignore[assignment]
    egress = PolicyFileEgress(driver, policy_dir)
    egress.observe(request_for("api.tavily.com"))
    run(egress.decide("r1", Decision.ALLOW, Scope.ALWAYS))
    assert (policy_dir / "research.yaml").read_text(encoding="utf-8").count("api.tavily.com") == 1


def test_policy_fallback_fails_loudly_on_a_malformed_policy(tmp_path: Path) -> None:
    (tmp_path / "research.yaml").write_text("agent: research\n", encoding="utf-8")
    egress = PolicyFileEgress(NemoClawDriver(policy_dir=tmp_path), tmp_path)
    egress.observe(request_for())
    with pytest.raises(ValueError, match="allow"):
        run(egress.decide("r1", Decision.ALLOW, Scope.ALWAYS))
