"""The demo-mode audit, as a test rather than a week-five ritual.

The spec schedules a demo-mode audit across every surface for week five, on a
clean machine, with no credentials. Doing it once by hand at the end is how it
gets skipped. This runs it on every commit.

The contract being enforced: `DEMO=true` must produce a fully working system
with zero real credentials, and no surface may quietly require one.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "apps" / "host", ROOT / "packages" / "inference"):
    sys.path.insert(0, str(extra))

from nemoclaw import FakeDriver  # noqa: E402
from server import Host, create_app  # noqa: E402

# Everything in .env.example that is a real secret. None may be needed.
CREDENTIALS = (
    "NEBIUS_API_KEY",
    "NEBIUS_BASE_URL",
    "TAVILY_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
)


@pytest.fixture()
def clean_machine(monkeypatch: pytest.MonkeyPatch) -> None:
    """A judge's machine: demo mode on, not one credential set."""
    for name in CREDENTIALS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEMO", "true")


@pytest.fixture()
def api(clean_machine: None, tmp_path: Path) -> Iterator[TestClient]:
    host = Host(
        driver=FakeDriver(speed=1000),
        data_dir=tmp_path / "sessions",
        session="audit",
    )
    with TestClient(create_app(host, background=False)) as client:
        yield client


# -- every surface answers ------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/health",
        "/api/events",
        "/api/approvals",
        "/api/memory",
        "/api/memory/diff",
        "/api/routing",
        "/api/sandboxes",
    ],
)
def test_every_get_endpoint_works_with_no_credentials(api: TestClient, path: str) -> None:
    assert api.get(path).status_code == 200


def test_the_live_stream_connects_with_no_credentials(api: TestClient) -> None:
    with api.websocket_connect("/api/stream"):
        pass


def test_a_sandbox_starts_with_no_credentials(api: TestClient) -> None:
    assert api.post("/api/sandboxes/calendar/start").json()["state"] == "running"


def test_the_health_endpoint_admits_it_is_in_demo_mode(api: TestClient) -> None:
    """Judges should be able to tell. Hiding it would be the wrong kind of
    polish."""
    body = api.get("/api/health").json()
    assert body["demo"] == "true"
    assert body["driver"] == "FakeDriver"


# -- the data behind it ---------------------------------------------------


def test_fixtures_load_with_no_credentials(clean_machine: None) -> None:
    from fixtures import loader

    assert loader.unread_threads()
    assert loader.upcoming_events()
    assert loader.memory_rows()
    assert loader.contacts()


def test_search_works_with_no_tavily_key(clean_machine: None) -> None:
    from packages.agents.research import search as tavily

    results = asyncio.run(tavily.search("Meridian Labs Series B March 2026"))
    assert results


def test_the_grounding_pass_runs_with_no_credentials(
    clean_machine: None, tmp_path: Path
) -> None:
    from jobs.nightly_synthesis import grounding

    results = asyncio.run(grounding.run(state_path=tmp_path / "g.json"))
    assert {r["status"] for r in results.values()} == {"confirmed", "stale", "contradicted"}


def test_the_driver_choice_needs_no_credentials(clean_machine: None) -> None:
    from nemoclaw import build_driver

    assert isinstance(build_driver(), FakeDriver)


# -- nothing leaks --------------------------------------------------------


def test_no_endpoint_response_mentions_a_credential_name(api: TestClient) -> None:
    """A stack trace or an echoed config would be the obvious way for a key
    name — or worse, a value — to reach a judge's browser."""
    for path in ("/api/health", "/api/events", "/api/memory", "/api/routing"):
        body = api.get(path).text
        for name in ("NEBIUS_API_KEY", "SUPABASE_SERVICE_KEY", "TAVILY_API_KEY"):
            assert name not in body


def test_env_example_holds_no_values(clean_machine: None) -> None:
    """Only names. A value committed here is a value in the git history
    forever, and the repo is public."""
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, value = line.partition("=")
        assert value.strip() in ("", "true", "false", "http://lifeos-vm:8000"), (
            f"{name} has a value in .env.example: {value!r}"
        )


def test_no_real_env_file_is_tracked() -> None:
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert ".env" not in tracked
    assert not [p for p in tracked if p.endswith("/.env")]


SECRET_SHAPES = (
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),          # OpenAI-style
    re.compile(r"\btvly-[A-Za-z0-9]{16,}"),        # Tavily
    re.compile(r"\beyJ[A-Za-z0-9_-]{30,}"),        # JWT, e.g. a Supabase key
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),         # GitHub
)


def test_no_tracked_text_file_looks_like_it_holds_a_key() -> None:
    """A standing guard. The repo is public and a key committed in week two and
    removed in week three is still in the history."""
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()

    for relative in tracked:
        path = ROOT / relative
        if path.suffix.lower() not in {
            ".py", ".ts", ".tsx", ".json", ".yaml", ".yml", ".md", ".css", ".sh", ".toml", ".example"
        }:
            continue
        if relative.startswith("tests/"):
            continue  # this file names the shapes on purpose
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for shape in SECRET_SHAPES:
            assert not shape.search(text), f"{relative} contains something shaped like a key"
