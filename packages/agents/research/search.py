"""Tavily search.

Two callers, and the second is the interesting one:

1. The Research agent, which needs live web search to do its job.
2. The nightly memory-grounding pass, which re-checks every remembered claim
   about the outside world against a live search and marks it confirmed, stale
   or contradicted. That makes the Tavily call load-bearing rather than
   incidental — a remembered fact that has quietly gone wrong is exactly the
   failure a personal assistant accumulates over months.

Every call emits an event, so searches appear in the Glass Box timeline
alongside everything else. That is also the evidence of a runtime call.

`api.tavily.com` is on the Research agent's egress allowlist and deliberately
not on anyone else's — the sandbox would block it, which is the point.

In demo mode the recorded responses in `fixtures/tavily.json` are served
instead, so the whole system runs with no TAVILY_API_KEY at all.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fixtures import loader as fixtures  # noqa: E402

TAVILY_URL = "https://api.tavily.com/search"

# VERIFY against Tavily's current docs before the first live call. The auth
# convention has changed across versions: older clients put `api_key` in the
# JSON body, newer ones send a bearer header. Both are sent by default, which
# is harmless if one is ignored and saves a confusing debugging session.
SEND_KEY_IN_BODY = True
SEND_KEY_AS_BEARER = True
AUTH_VERIFIED = False


class TavilyError(RuntimeError):
    pass


EmitFn = Callable[[dict[str, Any]], None]


def _noop(_: dict[str, Any]) -> None:
    """Default sink, replaced by the agent host with the real event log."""


async def search(
    query: str,
    depth: str = "basic",
    max_results: int = 5,
    emit: EmitFn | None = None,
    agent: str = "research",
    demo: bool | None = None,
) -> list[dict[str, Any]]:
    """Search, and emit an event whichever path was taken.

    The event is emitted for demo-mode hits too. A timeline that silently omits
    searches when the data is synthetic would be lying about what ran, and the
    "no silent work" rule does not have a demo exemption.
    """
    emit = emit or _noop
    use_demo = fixtures.is_demo() if demo is None else demo

    if use_demo:
        recorded = fixtures.tavily_response(query)
        results = recorded.get("results", [])[:max_results]
        emit(
            {
                "kind": "search",
                "agent": agent,
                "summary": f"Searched: {query}",
                "detail": {
                    "query": query,
                    "depth": depth,
                    "results": len(results),
                    "source": "fixture",
                },
            }
        )
        return results

    key = os.environ.get("TAVILY_API_KEY", "")
    if not key:
        raise TavilyError(
            "TAVILY_API_KEY is not set and DEMO is off. Set the key, or run in "
            "demo mode, which serves recorded responses."
        )

    import httpx  # imported lazily so demo mode needs no HTTP client

    payload: dict[str, Any] = {
        "query": query,
        "search_depth": depth,
        "max_results": max_results,
    }
    if SEND_KEY_IN_BODY:
        payload["api_key"] = key
    headers = {"Authorization": f"Bearer {key}"} if SEND_KEY_AS_BEARER else {}

    try:
        async with httpx.AsyncClient(timeout=20.0) as http:
            response = await http.post(TAVILY_URL, json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
    except Exception as exc:
        emit(
            {
                "kind": "error",
                "agent": agent,
                "summary": f"Search failed: {query}",
                "detail": {"query": query, "error": f"{type(exc).__name__}: {exc}"},
            }
        )
        raise TavilyError(f"Tavily request failed: {exc}") from exc

    results = body.get("results", [])[:max_results]
    emit(
        {
            "kind": "search",
            "agent": agent,
            "summary": f"Searched: {query}",
            "detail": {
                "query": query,
                "depth": depth,
                "results": len(results),
                "source": "tavily",
            },
        }
    )
    return results


def as_tool() -> dict[str, Any]:
    """The Agent SDK tool definition, translated by packages/inference/tools.py."""
    return {
        "name": "web_search",
        "description": (
            "Search the web for current information. Use when the answer depends "
            "on something that may have changed since training."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for"},
                "depth": {"type": "string", "enum": ["basic", "advanced"]},
            },
            "required": ["query"],
        },
    }
