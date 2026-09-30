"""Agent host HTTP + WebSocket surface.

Glass Box talks to exactly this. The six endpoints in the spec are the
contract, and they stay stable even if what sits behind approvals turns out to
be the slower policy-file path — which is the whole reason the API was defined
before the week-one experiments answered that question.

Glass Box writes only two things: approval decisions and routing.yaml.
Everything else it renders is someone else's state. Keeping it read-mostly is
what lets the frontend be deployed separately and handed to judges as a URL.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# A session left running here reached 33,930 events in a few hours. The page
# size is what the Replay screen fetches at a time; the ceiling is what any
# caller may ask for at once.
REPLAY_PAGE = 2000
REPLAY_MAX_PAGE = 10000

HOST_DIR = Path(__file__).resolve().parent
ROOT = HOST_DIR.parents[1]
for extra in (HOST_DIR, ROOT / "packages" / "inference", ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from events import EventLog, new_session_id, parse_log_line, read_session  # noqa: E402
from nemoclaw import Decision, Scope, build_driver  # noqa: E402
from summarize import Summarizer  # noqa: E402
from watcher import WorkspaceWatcher  # noqa: E402

import client as inference  # noqa: E402
from fixtures import loader as fixture_loader  # noqa: E402
from fixtures.loader import is_demo  # noqa: E402
from jobs.nightly_synthesis import grounding  # noqa: E402
from jobs.nightly_synthesis.grounding import load_state as load_grounding_state  # noqa: E402


class Host:
    """Everything the endpoints need, in one injectable object.

    Constructed by `create_app` so tests can substitute a fake driver and a
    temporary data directory without patching module globals.
    """

    def __init__(
        self,
        driver: Any | None = None,
        data_dir: str | os.PathLike[str] = "data/sessions",
        workspace: str | os.PathLike[str] | None = None,
        routing_path: Path | None = None,
        session: str | None = None,
    ) -> None:
        self.session = session or new_session_id()
        self.log = EventLog(self.session, data_dir=data_dir)
        self.driver = driver if driver is not None else build_driver()
        self.routing = inference.Routing(path=routing_path or inference.ROUTING_PATH)
        self.watcher = WorkspaceWatcher(workspace) if workspace else None
        self.started_at = time.time()
        self._tasks: list[asyncio.Task[Any]] = []

        self.client = self._build_client()
        self.summarizer = Summarizer(self.log, self.client) if self.client else None

    def _build_client(self) -> Any | None:
        """An inference client, or None if the system cannot yet call out.

        Two reasons it may be None, and both are normal right now: no Token
        Factory credentials, or routing.yaml still holding scaffold
        placeholders. Returning None is what keeps the host quiet instead of
        emitting an error for every batch it cannot summarize.
        """
        try:
            for task in inference.TASKS:
                self.routing.model_for(task)
        except (inference.PlaceholderModelError, inference.UnroutedTaskError, FileNotFoundError):
            return None
        try:
            transport = inference.OpenAITransport()
        except RuntimeError:
            return None
        return inference.InferenceClient(
            transport=transport,
            routing=self.routing,
            emit=lambda event: self.log.emit(
                event["kind"], event.get("agent", "system"), event["summary"], event.get("detail")
            ),
        )

    @property
    def inference_ready(self) -> bool:
        return self.client is not None

    # -- memory -----------------------------------------------------------

    @property
    def memory_source(self) -> str:
        return "fixtures" if is_demo() else "supabase"

    def memory_rows(self) -> list[dict[str, Any]]:
        """Seed rows in demo mode, with last night's grounding merged in.

        Outside demo mode this is where the Supabase pgvector read goes. It
        returns empty rather than inventing data, so a misconfigured
        deployment shows an empty memory instead of a fake one.
        """
        if not is_demo():
            return []
        grounded = load_grounding_state()
        return [
            {
                **row,
                "grounding": grounded.get(row["id"])
                or row.get("grounding")
                or {"status": "unverified", "last_checked": None},
            }
            for row in fixture_loader.memory_rows()
        ]

    async def run_grounding(self) -> None:
        """Run the nightly pass once at startup in demo mode.

        In production this is a Nebius Serverless Job on a cron trigger, not
        something the host does. Demo mode runs it so the provenance badges are
        populated the moment a judge opens the page rather than after a
        notional midnight that never comes.
        """
        if not is_demo():
            return
        try:
            await grounding.run(
                client=self.client,
                emit=lambda event: self.log.emit(
                    event["kind"], event.get("agent", "system"), event["summary"], event.get("detail")
                )
            )
        except Exception as exc:  # noqa: BLE001 — a failed pass must not stop the host
            self.log.emit(
                "error", "research", "Grounding pass failed", {"error": f"{type(exc).__name__}: {exc}"}
            )

    # -- background loops -------------------------------------------------

    async def run_tail(self, sandbox_id: str = "") -> None:
        async for line in self.driver.tail(sandbox_id):
            event = parse_log_line(line, self.session)
            if event is not None:
                self.log.append(event)

    async def run_watcher(self) -> None:
        if self.watcher is None:
            return
        await self.watcher.run(
            lambda kind, agent, summary, detail: self.log.emit(kind, agent, summary, detail)
        )

    async def run_egress_poll(self, interval: float = 1.0) -> None:
        """Surfaces approval requests for drivers that cannot push them.

        Deduplicated by request id, so a poll loop does not spam the timeline
        with the same pending card every tick.
        """
        seen: set[str] = set()
        while True:
            try:
                for request in await self.driver.pending_egress():
                    if request.id in seen:
                        continue
                    seen.add(request.id)
                    self.log.emit(
                        "egress_request",
                        request.agent,
                        f"{request.agent} wants to reach {request.host}",
                        request.to_dict(),
                    )
            except Exception as exc:  # noqa: BLE001 — a poll failure must not kill the host
                self.log.emit(
                    "error", "system", "Egress poll failed", {"error": f"{type(exc).__name__}: {exc}"}
                )
            await asyncio.sleep(interval)

    def start_background(self) -> None:
        loop = asyncio.get_event_loop()
        self._tasks = [
            loop.create_task(self.run_tail()),
            loop.create_task(self.run_egress_poll()),
            loop.create_task(self.run_grounding()),
        ]
        if self.summarizer is not None:
            self.summarizer.attach()
            self._tasks.append(loop.create_task(self.summarizer.run()))
        if self.watcher is not None:
            self._tasks.append(loop.create_task(self.run_watcher()))

    async def stop_background(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._tasks = []


def create_app(host: Host | None = None, background: bool = True) -> FastAPI:
    state = host or Host()

    @asynccontextmanager
    async def lifespan(_: FastAPI):  # type: ignore[no-untyped-def]
        if background:
            state.start_background()
        try:
            yield
        finally:
            await state.stop_background()

    app = FastAPI(title="LifeOS agent host", version="0.1.0", lifespan=lifespan)
    app.state.host = state

    # Glass Box runs on the laptop in dev and reaches the VM over Tailscale.
    # Tightened to the deployed origin before the public deployment in week 5.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # -- 0. health --------------------------------------------------------

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "ok": True,
            "session": state.session,
            "uptime_s": round(time.time() - state.started_at, 1),
            "driver": type(state.driver).__name__,
            "demo": os.environ.get("DEMO", "true"),
            "inference_ready": state.inference_ready,
            "events": len(state.log),
        }

    # -- 1. backfill ------------------------------------------------------

    @app.get("/api/events")
    async def events(
        since: float = Query(0.0, description="Unix seconds; returns events strictly newer"),
        limit: int = Query(1000, ge=1, le=5000),
    ) -> dict[str, Any]:
        rows = state.log.since(since)[-limit:]
        return {
            "session": state.session,
            "now": time.time(),
            "events": [e.to_dict() for e in rows],
        }

    # -- 2. live stream ---------------------------------------------------

    @app.websocket("/api/stream")
    async def stream(websocket: WebSocket) -> None:
        await websocket.accept()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)
        loop = asyncio.get_running_loop()

        def on_event(event: Any) -> None:
            # Called from whichever task emitted. Hop back onto the loop
            # thread rather than touching the socket directly.
            loop.call_soon_threadsafe(_offer, event.to_dict())

        def _offer(payload: dict[str, Any]) -> None:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # A slow client must not stall the host. Drop oldest.
                try:
                    queue.get_nowait()
                    queue.put_nowait(payload)
                except asyncio.QueueEmpty:  # pragma: no cover
                    pass

        unsubscribe = state.log.subscribe(on_event)
        try:
            for event in state.log.recent(200):
                await websocket.send_json(event.to_dict())
            while True:
                await websocket.send_json(await queue.get())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            unsubscribe()

    # -- 3. pending approvals ---------------------------------------------

    @app.get("/api/approvals")
    async def approvals() -> dict[str, Any]:
        pending = await state.driver.pending_egress()
        return {"approvals": [r.to_dict() for r in pending]}

    # -- 4. decide an approval --------------------------------------------

    @app.post("/api/approvals/{request_id}")
    async def decide(request_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        raw_decision = str(body.get("decision", "")).lower()
        raw_scope = str(body.get("scope", "once")).lower()
        try:
            decision = Decision(raw_decision)
            scope = Scope(raw_scope)
        except ValueError:
            raise HTTPException(
                422,
                detail="decision must be allow|deny and scope must be once|always",
            ) from None

        try:
            applied = await state.driver.decide_egress(request_id, decision, scope)
        except NotImplementedError as exc:
            raise HTTPException(409, detail=str(exc)) from None

        if not applied:
            raise HTTPException(404, detail=f"no pending approval {request_id!r}")

        state.log.emit(
            "egress_decision",
            "system",
            f"{decision.value} ({scope.value}) for {request_id}",
            {"request_id": request_id, "decision": decision.value, "scope": scope.value},
        )
        return {"ok": True, "request_id": request_id, "decision": decision.value, "scope": scope.value}

    # -- 5. memory --------------------------------------------------------

    @app.get("/api/memory/diff")
    async def memory_diff(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
        rows = [e for e in state.log.recent(2000) if e.kind == "memory_write"]
        return {"changes": [e.to_dict() for e in rows[-limit:]]}

    @app.get("/api/memory")
    async def memory() -> dict[str, Any]:
        """What LifeOS currently believes, with provenance.

        Demo mode reads the seed rows; outside demo mode this reads the
        Supabase pgvector table. The grounding status on each row is written
        by the nightly synthesis job, which re-checks external claims against
        Tavily — that is what the provenance badge renders.
        """
        return {"rows": state.memory_rows(), "source": state.memory_source}

    # -- replay -----------------------------------------------------------

    @app.get("/api/sessions")
    async def sessions() -> dict[str, Any]:
        """Past sessions, newest first.

        Read off disk rather than tracked in memory, so a session recorded
        before the host restarted is still replayable — which is the point of
        writing JSONL at all.
        """
        rows = []
        for path in sorted(state.log.path.parent.glob("*.jsonl")):
            try:
                stat = path.stat()
            except OSError:
                continue
            rows.append(
                {
                    "session": path.stem,
                    "bytes": stat.st_size,
                    "modified": stat.st_mtime,
                    "live": path.stem == state.session,
                }
            )
        rows.sort(key=lambda r: r["modified"], reverse=True)
        return {"sessions": rows}

    @app.get("/api/sessions/{session_id}")
    async def replay(
        session_id: str,
        offset: int = Query(0, ge=0),
        limit: int = Query(REPLAY_PAGE, ge=1, le=REPLAY_MAX_PAGE),
    ) -> dict[str, Any]:
        """One page of a session, oldest first, patches already applied.

        Paged, because sessions get large. A host left running produced a
        13.6 MB / 33,930-event file in a few hours here, and on the VM it runs
        for days; returning the whole thing would hand the judges' browser a
        response it cannot render.
        """
        path = _session_path(state, session_id)

        events = [e.to_dict() for e in read_session(path)]
        total = len(events)
        page = events[offset : offset + limit]
        return {
            "session": session_id,
            "events": page,
            "total": total,
            "offset": offset,
            "limit": limit,
            "started": events[0]["ts"] if events else None,
            "ended": events[-1]["ts"] if events else None,
        }

    # -- 6. routing -------------------------------------------------------

    @app.get("/api/routing")
    async def get_routing() -> dict[str, Any]:
        return {"routing": state.routing.table(), "tasks": list(inference.TASKS)}

    @app.post("/api/routing")
    async def set_routing(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        updates = {k: v for k, v in body.items() if k in inference.TASKS}
        if not updates:
            raise HTTPException(422, detail=f"body must set at least one of {list(inference.TASKS)}")
        if any(not isinstance(v, str) or not v.strip() for v in updates.values()):
            raise HTTPException(422, detail="model ids must be non-empty strings")

        _write_routing(state.routing.path, {k: v.strip() for k, v in updates.items()})
        table = state.routing.table()

        state.log.emit(
            "action",
            "system",
            "Routing changed: " + ", ".join(f"{k}->{v}" for k, v in sorted(updates.items())),
            {"routing": table},
        )
        return {"routing": state.routing.table()}

    # -- sandbox lifecycle (not one of the six, but the host owns it) -----

    @app.get("/api/sandboxes")
    async def sandboxes() -> dict[str, Any]:
        rows = await state.driver.status()
        return {
            "sandboxes": [
                {
                    "id": s.id,
                    "agent": s.agent,
                    "state": s.state.value,
                    "started_at": s.started_at,
                }
                for s in rows
            ]
        }

    @app.post("/api/sandboxes/{agent}/start")
    async def start_sandbox(agent: str) -> dict[str, Any]:
        try:
            info = await state.driver.start(agent)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(400, detail=str(exc)) from None
        state.log.emit("action", info.agent, f"Sandbox {info.id} started", {"sandbox": info.id})
        return {"id": info.id, "agent": info.agent, "state": info.state.value}

    @app.post("/api/sandboxes/{sandbox_id}/stop")
    async def stop_sandbox(sandbox_id: str) -> dict[str, Any]:
        await state.driver.stop(sandbox_id)
        state.log.emit("action", "system", f"Sandbox {sandbox_id} stopped", {"sandbox": sandbox_id})
        return {"ok": True}

    return app


def _allowed_origins() -> list[str]:
    configured = os.environ.get("GLASSBOX_ORIGINS", "").strip()
    if configured:
        return [o.strip() for o in configured.split(",") if o.strip()]
    return ["http://localhost:3000", "http://127.0.0.1:3000"]


def _session_path(state: "Host", session_id: str) -> Path:
    """Resolve a session id to a file, or raise.

    Containment is checked on the *resolved* path rather than by blacklisting
    characters. The previous version rejected '/', '\\' and '..', which let a
    Windows drive-relative id through: Path('data/sessions') / 'C:evil.jsonl'
    evaluates to WindowsPath('C:evil.jsonl'), because pathlib discards the
    left-hand side when the right has a drive. Blacklists keep losing to the
    next bit of path syntax; asking where the path actually landed does not.
    """
    root = state.log.path.parent.resolve()
    try:
        candidate = (root / f"{session_id}.jsonl").resolve()
        candidate.relative_to(root)
    except (ValueError, OSError):
        raise HTTPException(400, detail="bad session id") from None

    if not candidate.is_file():
        raise HTTPException(404, detail=f"no session {session_id!r}")
    return candidate


_ROUTING_LINE = re.compile(r"^(?P<key>[A-Za-z_][\w-]*)(?P<sep>:\s*)(?P<value>\S.*?)(?P<trail>\s*)$")


def _yaml_scalar(value: str) -> str:
    """A double-quoted YAML scalar, escaped.

    The previous version used repr() and then replaced every single quote with
    a double one, which produced `plan: "we"ird"` for any value containing a
    quote — silent corruption of the one file that decides which model every
    agent uses.
    """
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _write_routing(path: Path, updates: dict[str, str]) -> None:
    """Change only the named top-level keys, in place.

    Rewritten as a line edit rather than a regeneration. The previous version
    rebuilt the file from the routing table, which holds only string values —
    so every tier switch silently deleted the `pricing:` block and with it the
    cost meter. The demo beat that flips Super to Ultra was destroying the
    meter it exists to move.

    Only top-level, unindented keys are touched. Nested mappings, comments,
    blank lines and key order all survive untouched, because the safest way to
    not break the rest of the file is to not rewrite the rest of the file.
    """
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(updates)

    for index, line in enumerate(lines):
        if line[:1].isspace():
            continue  # nested — not ours to touch
        match = _ROUTING_LINE.match(line)
        if not match:
            continue
        key = match.group("key")
        if key not in remaining:
            continue
        comment = ""
        raw = match.group("value")
        if " #" in raw:  # keep a trailing comment on the line
            comment = "  " + raw[raw.index(" #") + 1 :].strip()
        lines[index] = f"{key}:{match.group('sep')[1:] or ' '}{_yaml_scalar(remaining.pop(key))}{comment}"

    # A task the file never defined gets appended rather than lost.
    for key, value in remaining.items():
        lines.append(f"{key}: {_yaml_scalar(value)}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


app = create_app() if os.environ.get("LIFEOS_HOST_AUTOSTART", "") else None
