# Build log

A few lines a day: what broke, what the workaround was, what surprised me.
This writes the submission's feedback section for free — and feedback written
from a running log reads specific rather than generic, which is visible.

## 2026-09-19 — day 2, Week 1

- Repo scaffolded from the spec: layout, CLAUDE.md, MIT LICENSE, .env.example,
  .gitignore, LEGACY.md, routing.yaml (placeholder model ids), per-agent egress
  policies, demo-mode fixture stubs.
- Kept separate from the existing `life-os-v1` repo. The four unported agents
  stay where they are; this repo is the hackathon build.
- Not yet done: nothing has touched Nebius. Step 1 of the runbook (prove a
  Token Factory call returns a 200) is the next action and blocks everything.
- Session 5 (event model) done ahead of order, because it is the only item on
  the session list that needs no Nebius credentials and no VM. `apps/host/events.py`:
  Event dataclass, 5000-entry ring buffer, append-only JSONL under
  `data/sessions/`, subscribe/fan-out for the WebSocket, and replay. 17 tests
  pass offline.
- Two deviations from the spec's sketch of the Event dataclass, both forced by
  the spec's own requirements:
  1. Added `id`. The spec says to emit an event immediately with the raw log
     line and patch in Nano's summary a beat later — patching needs an address.
  2. Added `summary_pending`, so Glass Box can dim an unsummarized line and
     make the fill-in read as deliberate rather than laggy.
  Summary patches are appended as their own JSONL line rather than rewriting
  the file, keeping replay a forward-only read of an append-only log.
- Toolchain gap: `uv` and `pnpm` are not installed on the laptop yet; `gh` is
  not either. pytest was installed with plain pip as a stopgap. Fix before
  session 2.
