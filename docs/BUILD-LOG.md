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
- Sessions 2 and 3 (Token Factory client, tool-schema translation) built
  offline, ahead of having a key. Every transport is injectable, so the whole
  adapter is testable without touching Nebius — which is the point, given the
  spec's warning about burning credits on week-two debug loops.
- `routing.yaml` model ids are still placeholders. The client raises
  `PlaceholderModelError` on any id containing "TODO" rather than letting it
  become a confusing 404 from the API.
- Wrote a fallback YAML parser so a missing PyYAML on the VM cannot stop model
  routing. First version had two bugs the tests caught: it only handled one
  level of nesting, and it skipped comment-stripping on any line containing a
  quote — which is every line in the shipped routing file. Rewrote it
  indent-aware with a quote-respecting comment stripper.
- Fixture authoring bug also caught by a test: 2026-10-02 is a Friday, not a
  Thursday, so "quarterly planning on Friday" was landing on a Saturday. Moved
  the anchor to Thursday 2026-10-01 and the whole demo week now reads right.
  Worth noting for the feedback section: the value of the week-shift rebasing
  was that it made the error *visible* rather than subtly wrong.
- Cost meter reports null, not 0.00, when a model's rate is unknown. A meter
  reading zero looks like a working meter reporting a free call.
- Sessions 4, 5 and 6 (nemoclaw wrapper, event stream, API) built against a
  driver interface rather than the real CLI, because the CLI surface is a
  week-one unknown and guessing at alpha flags is how a week gets lost. Every
  command string sits in one `COMMANDS` dict marked unverified, and a test
  asserts it is still marked unverified so flipping that flag is deliberate.
- The two other week-one unknowns are abstracted the same way. `InteractiveEgress`
  and `PolicyFileEgress` implement one interface, so the six REST endpoints are
  identical whichever answer week one gives. Log tailing falls back from follow
  to a 500 ms poll inside the same async iterator, so no caller branches on it.
- `FakeDriver` is not a test double bolted on afterwards — it is how demo mode
  works. It replays a scripted session covering every beat of the video: the
  calendar conflict, the Tavily search, the injection email being declined, the
  blocked egress, and a draft left awaiting approval. Glass Box can now be built
  and recorded before the VM exists.
- PolicyFileEgress refuses `scope=once` rather than faking it: a static
  allowlist cannot express a one-shot exception, and silently making it
  permanent would be a hole punched in the policy by the UI.
- Deps added, all spec-sanctioned: fastapi, uvicorn, httpx, pyyaml.
- Glass Box built: Timeline, Approvals, Memory and Routing, plus the live
  WebSocket stream with backfill and reconnect. Next.js 15, no CSS framework —
  hand-written tokens, because the design criterion is a quarter of the score
  and a default component library reads as a default component library.
- Three bugs that only a real browser found, none of which the test suite could
  have caught:
  1. `uvicorn` had no WebSocket library installed. FastAPI's TestClient
     implements WebSockets in-process, so every WS test passed while a real
     browser got a 404 on the upgrade. Installed `websockets`.
  2. `backdrop-filter` on the sticky header made it the containing block for
     its `position: fixed` children, so the mobile bottom nav was pinned inside
     the header instead of the viewport. Invisible on desktop; broken on the
     one screen the demo depends on.
  3. The timeline's filter row reused the `.actions` class, which stacks
     vertically on mobile — seven full-height buttons in a column.
- Also flipped the approval buttons: `Deny` now sits nearest the thumb on
  mobile. The safe decision should be the easy one; "allow always" deserves a
  deliberate stretch.
- Tavily is in, in both places the spec wants it: the Research agent's search
  tool, and the nightly grounding pass that re-checks remembered claims and
  marks them confirmed / stale / contradicted. That second use is what makes
  the call load-bearing rather than a bolt-on, and all three verdicts are
  visible in demo mode.
- The grounding judge routes to `plan` (Ultra) and parses a chatty verdict
  down to one word, falling back to `unverified`. An unparsed verdict must
  never read as `confirmed`.
