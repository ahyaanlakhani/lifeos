"""NemoClaw / OpenShell sandbox driver.

The agent host is the only thing in the system that touches the `nemoclaw`
CLI. If Glass Box ever shells out directly, the frontend can no longer be
deployed separately and the judges' demo URL gets much harder.

**On the shape of this module.** NemoClaw is alpha. Its exact subcommands and
flags come from `nemoclaw --help` and the current docs, not from memory, and
they are a week-one unknown. So every CLI invocation is funnelled through one
method, `NemoClawDriver._run`, and the command strings sit together in
`COMMANDS` where they can be corrected in one place once verified. Nothing
downstream of the `SandboxDriver` protocol knows or cares what the CLI looks
like.

Two unknowns are also abstracted rather than assumed, because the spec says to
define the API before knowing the answer:

- **Egress approvals** may or may not be answerable programmatically. Two
  strategies implement the same interface; `PolicyFileEgress` writes the
  allowlist and restarts the sandbox, which is slower but demoable.
- **Logs** may be streamable or only pollable. `tail` is an async iterator
  either way, so the caller never branches on it.

`FakeDriver` is not a test double bolted on afterwards — it is how demo mode
works. It runs a scripted session with no VM, no NemoClaw and no credentials,
which is what lets Glass Box be built and recorded before any of that exists.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Protocol

AGENTS = ("calendar", "email", "research")


class SandboxState(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class Scope(str, Enum):
    ONCE = "once"
    ALWAYS = "always"


@dataclass
class SandboxInfo:
    id: str
    agent: str
    state: SandboxState
    started_at: float
    workspace: Path | None = None


@dataclass
class EgressRequest:
    """A sandbox asking to reach a host that is not on its allowlist.

    This is the 1:25 beat of the demo video, so it carries enough context to
    render a decision card on a phone without a second round trip.
    """

    id: str
    agent: str
    host: str
    reason: str
    requested_at: float
    sandbox_id: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent": self.agent,
            "host": self.host,
            "reason": self.reason,
            "requested_at": self.requested_at,
            "sandbox_id": self.sandbox_id,
            "detail": self.detail,
        }


class SandboxDriver(Protocol):
    async def start(self, agent: str) -> SandboxInfo: ...
    async def stop(self, sandbox_id: str) -> None: ...
    async def status(self) -> list[SandboxInfo]: ...
    def tail(self, sandbox_id: str) -> AsyncIterator[str]: ...
    async def pending_egress(self) -> list[EgressRequest]: ...
    async def decide_egress(self, request_id: str, decision: Decision, scope: Scope) -> bool: ...


# -- the real driver ------------------------------------------------------

# Every CLI string lives here. VERIFY EACH ONE against `nemoclaw --help`
# before trusting it; these are placeholders in the shape the docs imply, not
# remembered syntax. Correcting them is a week-one task and should touch only
# this dict.
COMMANDS: dict[str, list[str]] = {
    "version": ["--version"],
    "start": ["sandbox", "start", "--name", "{name}", "--policy", "{policy}"],
    "stop": ["sandbox", "stop", "{sandbox_id}"],
    "status": ["sandbox", "list", "--json"],
    "logs_follow": ["sandbox", "logs", "{sandbox_id}", "--follow"],
    "logs_once": ["sandbox", "logs", "{sandbox_id}", "--since", "{since}"],
    "egress_list": ["policy", "requests", "--json"],
    "egress_decide": ["policy", "decide", "{request_id}", "--{decision}", "--scope", "{scope}"],
}

COMMANDS_VERIFIED = False
"""Flip to True only after `nemoclaw --help` has been read and COMMANDS
corrected. `NemoClawDriver` warns on construction while this is False."""


class NemoClawCommandError(RuntimeError):
    def __init__(self, argv: list[str], code: int, stderr: str) -> None:
        super().__init__(f"{shlex.join(argv)} exited {code}: {stderr.strip()[:400]}")
        self.argv = argv
        self.code = code
        self.stderr = stderr


class NemoClawDriver:
    """Shells out to the pinned `nemoclaw` binary."""

    def __init__(
        self,
        binary: str = "nemoclaw",
        policy_dir: str | os.PathLike[str] = "infra/policies",
        workspace_root: str | os.PathLike[str] | None = None,
        egress: "EgressStrategy | None" = None,
    ) -> None:
        self.binary = binary
        self.policy_dir = Path(policy_dir)
        self.workspace_root = Path(workspace_root) if workspace_root else None
        self.egress = egress or InteractiveEgress(self)
        self._sandboxes: dict[str, SandboxInfo] = {}

    # -- process plumbing, all of it, in one place ------------------------

    async def _run(self, key: str, **params: Any) -> str:
        argv = [self.binary] + [part.format(**params) for part in COMMANDS[key]]
        process = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise NemoClawCommandError(argv, process.returncode or -1, stderr.decode(errors="replace"))
        return stdout.decode(errors="replace")

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    async def version(self) -> str:
        """Pin this and never upgrade. Alpha software moving under a six-week
        build is a failure mode with no upside."""
        return (await self._run("version")).strip()

    # -- lifecycle --------------------------------------------------------

    def policy_for(self, agent: str) -> Path:
        path = self.policy_dir / f"{agent}.yaml"
        if not path.exists():
            raise FileNotFoundError(
                f"no egress allowlist for {agent!r} at {path}. "
                "An agent without a policy would run unconstrained, which is the "
                "one thing this project exists to prevent."
            )
        return path

    async def start(self, agent: str) -> SandboxInfo:
        if agent not in AGENTS:
            raise ValueError(f"unknown agent {agent!r}; expected one of {AGENTS}")
        policy = self.policy_for(agent)
        raw = await self._run("start", name=f"lifeos-{agent}", policy=str(policy))
        sandbox_id = _first_id(raw) or f"lifeos-{agent}"
        info = SandboxInfo(
            id=sandbox_id,
            agent=agent,
            state=SandboxState.RUNNING,
            started_at=time.time(),
            workspace=self.workspace_root / sandbox_id if self.workspace_root else None,
        )
        self._sandboxes[sandbox_id] = info
        return info

    async def stop(self, sandbox_id: str) -> None:
        await self._run("stop", sandbox_id=sandbox_id)
        if sandbox_id in self._sandboxes:
            self._sandboxes[sandbox_id].state = SandboxState.STOPPED

    async def status(self) -> list[SandboxInfo]:
        raw = await self._run("status")
        try:
            rows = json.loads(raw)
        except json.JSONDecodeError:
            # An alpha CLI may not honour --json. Fall back to what we tracked
            # rather than losing the status screen entirely.
            return list(self._sandboxes.values())
        return [
            SandboxInfo(
                id=str(row.get("id") or row.get("name", "")),
                agent=str(row.get("agent") or _agent_from_name(row.get("name", ""))),
                state=_state(row.get("state") or row.get("status")),
                started_at=float(row.get("started_at") or time.time()),
            )
            for row in (rows if isinstance(rows, list) else rows.get("sandboxes", []))
        ]

    # -- logs -------------------------------------------------------------

    async def tail(self, sandbox_id: str, poll_interval: float = 0.5) -> AsyncIterator[str]:
        """Stream log lines, falling back to polling.

        Week-one unknown #3. Callers never branch on the answer: this is an
        async iterator either way, and polling every 500 ms is visually
        identical on camera.
        """
        try:
            async for line in self._tail_follow(sandbox_id):
                yield line
            return
        except (NemoClawCommandError, FileNotFoundError, NotImplementedError):
            pass

        since = time.time()
        while True:
            try:
                chunk = await self._run("logs_once", sandbox_id=sandbox_id, since=str(since))
            except NemoClawCommandError:
                return
            since = time.time()
            for line in chunk.splitlines():
                if line.strip():
                    yield line
            await asyncio.sleep(poll_interval)

    async def _tail_follow(self, sandbox_id: str) -> AsyncIterator[str]:
        argv = [self.binary] + [p.format(sandbox_id=sandbox_id) for p in COMMANDS["logs_follow"]]
        process = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        assert process.stdout is not None
        saw_output = False
        while True:
            raw = await process.stdout.readline()
            if not raw:
                break
            saw_output = True
            yield raw.decode(errors="replace").rstrip("\n")
        if not saw_output and process.returncode not in (0, None):
            stderr = (await process.stderr.read()).decode(errors="replace") if process.stderr else ""
            raise NemoClawCommandError(argv, process.returncode or -1, stderr)

    # -- egress -----------------------------------------------------------

    async def pending_egress(self) -> list[EgressRequest]:
        return await self.egress.pending()

    async def decide_egress(self, request_id: str, decision: Decision, scope: Scope) -> bool:
        return await self.egress.decide(request_id, decision, scope)


def _first_id(raw: str) -> str | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw.splitlines()[-1].strip() or None
    if isinstance(data, dict):
        value = data.get("id") or data.get("name")
        return str(value) if value else None
    return None


def _agent_from_name(name: str) -> str:
    return name.removeprefix("lifeos-") or "system"


def _state(value: Any) -> SandboxState:
    try:
        return SandboxState(str(value).lower())
    except ValueError:
        return SandboxState.RUNNING


# -- egress strategies ----------------------------------------------------


class EgressStrategy(Protocol):
    async def pending(self) -> list[EgressRequest]: ...
    async def decide(self, request_id: str, decision: Decision, scope: Scope) -> bool: ...


class InteractiveEgress:
    """Assumes requests can be listed and answered through the CLI.

    The preferred path. Falls back to nothing — if week one shows this is not
    possible, swap the driver's strategy for `PolicyFileEgress`; the host's
    six endpoints do not change.
    """

    def __init__(self, driver: NemoClawDriver) -> None:
        self.driver = driver

    async def pending(self) -> list[EgressRequest]:
        raw = await self.driver._run("egress_list")
        try:
            rows = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if isinstance(rows, dict):
            rows = rows.get("requests", [])
        return [
            EgressRequest(
                id=str(row.get("id", "")),
                agent=str(row.get("agent") or _agent_from_name(row.get("sandbox", ""))),
                host=str(row.get("host") or row.get("domain", "")),
                reason=str(row.get("reason", "")),
                requested_at=float(row.get("requested_at") or time.time()),
                sandbox_id=str(row.get("sandbox", "")),
                detail=row,
            )
            for row in rows
        ]

    async def decide(self, request_id: str, decision: Decision, scope: Scope) -> bool:
        await self.driver._run(
            "egress_decide",
            request_id=request_id,
            decision=decision.value,
            scope=scope.value,
        )
        return True


class PolicyFileEgress:
    """Fallback for when approvals turn out to be interactive-only.

    Writes the decision into the agent's allowlist and restarts its sandbox.
    Slower, and the sandbox loses its in-flight work, but it is demoable and —
    the reason this exists — it keeps the six REST endpoints identical, so
    nothing above it has to change.

    A `deny` needs no file write at all: the request is already blocked by
    default. Only an `allow` with scope `always` edits the policy.
    """

    def __init__(self, driver: NemoClawDriver, policy_dir: str | os.PathLike[str] | None = None) -> None:
        self.driver = driver
        self.policy_dir = Path(policy_dir) if policy_dir else driver.policy_dir
        self._pending: dict[str, EgressRequest] = {}

    def observe(self, request: EgressRequest) -> None:
        """Called by the log parser when it sees a blocked-egress line, since
        this mode cannot ask the CLI for a list."""
        self._pending[request.id] = request

    async def pending(self) -> list[EgressRequest]:
        return sorted(self._pending.values(), key=lambda r: r.requested_at)

    async def decide(self, request_id: str, decision: Decision, scope: Scope) -> bool:
        request = self._pending.pop(request_id, None)
        if request is None:
            return False
        if decision is Decision.DENY:
            return True  # already blocked; nothing to write
        if scope is Scope.ONCE:
            # Cannot express a one-shot exception in a static allowlist.
            # Honest failure beats a permanent hole punched in the policy.
            raise NotImplementedError(
                "scope=once cannot be expressed in a policy file. "
                "Use scope=always, or deny."
            )
        self._append_allow(request.agent, request.host)
        for sandbox in await self.driver.status():
            if sandbox.agent == request.agent:
                await self.driver.stop(sandbox.id)
                await self.driver.start(request.agent)
                break
        return True

    def _append_allow(self, agent: str, host: str) -> None:
        path = self.policy_dir / f"{agent}.yaml"
        text = path.read_text(encoding="utf-8")
        if f"- {host}" in text:
            return
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if line.strip() == "allow:":
                indent = " " * (len(line) - len(line.lstrip()) + 2)
                lines.insert(index + 1, f"{indent}- {host}    # added via Glass Box approval")
                break
        else:
            raise ValueError(f"{path} has no `allow:` block to extend")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# -- the fake driver, which is how demo mode works ------------------------

SCRIPT: list[tuple[float, str, str]] = [
    # (delay seconds, agent, raw log line)
    (0.0, "calendar", "INFO  agent=calendar sandbox=up policy=infra/policies/calendar.yaml"),
    (0.4, "calendar", "INFO  agent=calendar tool=list_events range=7d result=9_events"),
    (0.5, "calendar", "WARN  agent=calendar conflict evt_0006 overlaps evt_0007 on Friday"),
    (0.6, "calendar", "INFO  agent=calendar memory_write key=conflict/friday"),
    (0.5, "email", "INFO  agent=email sandbox=up policy=infra/policies/email.yaml"),
    (0.4, "email", "INFO  agent=email tool=list_threads unread=5"),
    (0.5, "email", "INFO  agent=email classify thr_0006 label=noise action=none"),
    (0.5, "email", "WARN  agent=email thr_0007 contains instructions addressed to the agent; ignoring"),
    (
        0.6,
        "email",
        "BLOCK agent=email egress host=1ifeos-support.example reason=not_in_allowlist "
        "request=req_7a1c detail=forward_last_20_messages",
    ),
    (0.8, "research", "INFO  agent=research sandbox=up policy=infra/policies/research.yaml"),
    (0.5, "research", "INFO  agent=research tool=tavily_search query=\"Meridian Labs vendor comparison deployment timelines\""),
    (0.6, "research", "INFO  agent=research tool=tavily_search results=2 top=meridianlabs.example"),
    (0.5, "research", "INFO  agent=research memory_write key=meridian/procurement"),
    (0.6, "email", "INFO  agent=email draft thr_0003 status=awaiting_approval"),
]


class FakeDriver:
    """A scripted sandbox session with no VM and no NemoClaw.

    This is how `DEMO=true` produces a live-looking timeline, and how Glass Box
    gets built before the VM exists. The script deliberately includes the
    prompt-injection email being declined and the resulting egress block, which
    is the governance beat of the demo video.
    """

    def __init__(self, speed: float = 1.0, loop_script: bool = False) -> None:
        self.speed = speed
        self.loop_script = loop_script
        self.started: list[str] = []
        self.stopped: list[str] = []
        self.decisions: list[tuple[str, Decision, Scope]] = []
        self._sandboxes: dict[str, SandboxInfo] = {}
        self._pending: dict[str, EgressRequest] = {}

    async def start(self, agent: str) -> SandboxInfo:
        if agent not in AGENTS:
            raise ValueError(f"unknown agent {agent!r}; expected one of {AGENTS}")
        self.started.append(agent)
        info = SandboxInfo(
            id=f"fake-{agent}",
            agent=agent,
            state=SandboxState.RUNNING,
            started_at=time.time(),
        )
        self._sandboxes[info.id] = info
        return info

    async def stop(self, sandbox_id: str) -> None:
        self.stopped.append(sandbox_id)
        if sandbox_id in self._sandboxes:
            self._sandboxes[sandbox_id].state = SandboxState.STOPPED

    async def status(self) -> list[SandboxInfo]:
        return list(self._sandboxes.values())

    async def tail(self, sandbox_id: str = "") -> AsyncIterator[str]:
        while True:
            for delay, agent, line in SCRIPT:
                if sandbox_id and not sandbox_id.endswith(agent):
                    continue
                await asyncio.sleep(delay / self.speed if self.speed else 0)
                if line.startswith("BLOCK"):
                    request = _parse_block_line(line)
                    if request:
                        self._pending[request.id] = request
                yield line
            if not self.loop_script:
                return
            # A pause between cycles, so a looping demo reads as a system
            # going quiet and picking up again rather than as spam.
            await asyncio.sleep(8 / self.speed if self.speed else 0)

    async def pending_egress(self) -> list[EgressRequest]:
        return sorted(self._pending.values(), key=lambda r: r.requested_at)

    async def decide_egress(self, request_id: str, decision: Decision, scope: Scope) -> bool:
        if request_id not in self._pending:
            return False
        del self._pending[request_id]
        self.decisions.append((request_id, decision, scope))
        return True


def _parse_block_line(line: str) -> EgressRequest | None:
    fields = dict(
        part.split("=", 1) for part in shlex.split(line) if "=" in part and not part.startswith("=")
    )
    request_id = fields.get("request")
    if not request_id:
        return None
    return EgressRequest(
        id=request_id,
        agent=fields.get("agent", "system"),
        host=fields.get("host", ""),
        reason=fields.get("reason", ""),
        requested_at=time.time(),
        sandbox_id=fields.get("sandbox", ""),
        detail=fields,
    )


def build_driver(demo: bool | None = None, **kwargs: Any) -> SandboxDriver:
    """Pick a driver. Demo mode, or no nemoclaw on PATH, gets the fake one.

    Falling back on a missing binary is deliberate: developing Glass Box on a
    laptop must not require the VM.
    """
    if demo is None:
        demo = os.environ.get("DEMO", "true").strip().lower() not in {"0", "false", "no", "off", ""}
    if demo:
        fake_kwargs = {k: v for k, v in kwargs.items() if k in {"speed", "loop_script"}}
        # DEMO_LOOP keeps the scripted session running, so a timeline being
        # recorded does not go quiet halfway through a take.
        fake_kwargs.setdefault(
            "loop_script",
            os.environ.get("DEMO_LOOP", "").strip().lower() in {"1", "true", "yes", "on"},
        )
        return FakeDriver(**fake_kwargs)
    driver = NemoClawDriver(**{k: v for k, v in kwargs.items() if k not in {"speed", "loop_script"}})
    if not driver.available():
        raise RuntimeError(
            "DEMO is off but the nemoclaw binary is not on PATH. "
            "Refusing to fall back to the fake driver outside demo mode — "
            "a fake sandbox pretending to be a real one is the worst outcome here."
        )
    return driver
