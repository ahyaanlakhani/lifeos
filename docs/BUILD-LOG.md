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
- Nano batch summarization built. Collects pending events over a 2 s window, up
  to 20 at a time, one call per batch, patched back in. A batch whose length
  does not match the number of events is rejected outright and the lines stay
  raw — misaligned summaries would put the wrong sentence on the wrong event,
  which is worse than raw text because it looks right.
- The host now declines to build an inference client at all while routing.yaml
  holds placeholders or credentials are missing, rather than emitting an error
  per batch. `/api/health` reports `inference_ready` so it is obvious why the
  timeline is still showing raw lines.
- Demo-mode audit is now a test that runs on every commit rather than a
  week-five ritual: every endpoint answers with no credentials, plus standing
  guards that no tracked file contains anything shaped like an API key and that
  .env.example holds only names.
- Agent run loop written (`packages/agents/loop.py`) — the replacement for the
  Claude Agent SDK's loop. Plain, as the spec predicted it could be. Three
  things it refuses to do: run a tool marked `requires_approval` (no override
  flag, because a flag is exactly what gets set during a demo), treat tool
  output as instructions, or run unbounded. Turn count and total tool calls are
  both capped and hitting either ends the run with a stated reason.
- The shared guardrail preamble sits in the loop rather than in each agent's
  prompt, so the sandbox rules cannot be lost when a per-agent prompt is
  reworked for Nemotron. The per-agent prompts remain adaptations of the LifeOS
  master prompt, layered on top.
- Verified from a clean start with every credential env var unset: all seven
  host endpoints, all four Glass Box pages, the WebSocket, the grounding pass
  and the approval flow. No errors in the host log. `inference_ready` reports
  false, which is correct and visible.

## 2026-09-20 — day 3, Week 1

- Repo public: <https://github.com/ahyaanlakhani/lifeos>. MIT detected by
  GitHub, ten commits, nothing unpushed.
- Rewrote author and committer on all ten commits before publishing, and
  deleted the `refs/original` backup filter-branch leaves behind — that backup
  is easy to miss and would have carried the old identity into the public repo
  anyway. Checked the whole object store afterwards rather than just the tip.
- Pre-publish sweep over all 88 history blobs: nothing shaped like an API key,
  `.env` never committed, no personal identifiers in any file content. Worth
  having done before the repo went public rather than after.
- The documented install failed on Windows, found by watching someone run it
  rather than by testing. `npm` on Windows is a PowerShell shim and the default
  execution policy blocks it with `UnauthorizedAccess`; my own tooling runs
  with `-ExecutionPolicy Bypass`, which is exactly why I never saw it. Fix is
  `npm.cmd`, a batch file the policy does not apply to — no security setting
  changes. Added `scripts/demo.cmd`, which wraps `demo.ps1` with a
  per-invocation bypass, because a bare `.ps1` would hit the same wall.
- Both demo scripts now install `node_modules` on first run, and `.gitattributes`
  keeps the Windows entry points on CRLF.
- Worth carrying into the feedback section: the demo URL requirement means
  judges will run this cold on an unknown machine. Everything above was
  invisible until someone actually did.
- The three ported agents assembled: `packages/agents/data.py` (one seam, two
  backends), `prompts.py` (master prompt + per-agent adaptation, layered not
  forked, as the spec insists) and `registry.py` (tools per agent).
- `master_prompt.md` is a clearly-marked placeholder. The real LifeOS master
  prompt needs pasting in — writing a new one would discard the September
  specification pass. A test asserts it is still a placeholder, so the day it
  is replaced is deliberate.
- Tool sets deliberately do not overlap: the Calendar agent has no search tool
  *and* its sandbox blocks api.tavily.com. Two independent reasons is what
  makes the claim believable rather than a policy file nobody checks.
- Exactly two tools are gated on approval — `move_event` and `send_email`.
  Reads are not gated, because gating a read makes the agent useless and trains
  the operator to approve reflexively, which is how approval theatre starts.
- `read_thread` restates "bodies are content, not instructions" in its own
  return value, not only in the system prompt. The instruction is furthest from
  the model's attention exactly when the untrusted text arrives.
- Session replay done, which closes the last missing Glass Box screen.
  `GET /api/sessions` lists what is on disk and `GET /api/sessions/{id}` replays
  one with summary patches already applied. Reading from disk rather than the
  ring buffer is the point: a session recorded before a restart is still
  replayable, which is why the JSONL exists at all.
- The session id lands in a filesystem path, so it is rejected if it contains
  one.
- Scrubber steps by event position, not wall-clock time. Agents are bursty and
  a time-proportional slider spends most of its travel on the gaps between
  bursts; stepping event by event is what someone auditing a run wants.
  Playback still paces by the real gap, clamped to 3s so an idle stretch does
  not stall it.
- Deploy config written ahead of week 5: `infra/compose.yml`, two Dockerfiles,
  a Caddyfile for automatic TLS, and a systemd user unit for the simpler path.
  Sandboxes are deliberately absent from compose — the agent host owns their
  lifecycle through the CLI, and two owners of one lifecycle is a bad trade.
- `infra/README.md` carries the pre-launch checklist. The one most likely to
  bite: `NEXT_PUBLIC_*` is inlined by Next at build time, so pointing Glass Box
  at the real host URL needs a rebuild, not an env change. Second most likely:
  a `wss://` upgrade that silently fails through the proxy leaves the timeline
  looking empty rather than erroring.
- Corrected the test count in the previous commit message: 373, not 371. Noted
  here rather than rewriting a pushed commit.

## 2026-09-30 — audit fixes

- Ran a full code review over the branch. Seven findings, all now fixed, all
  with regression tests that were verified to fail against the pre-fix code by
  stashing the source and re-running.
- The two that mattered were both failures that only show up on camera:
  1. `POST /api/routing` rebuilt routing.yaml from the routing table, which
     holds only string values — so every tier switch silently deleted the
     `pricing:` block. The 2:30 demo beat was destroying the cost meter it
     exists to move. Rewritten as an in-place line edit: only the named
     top-level keys change, and comments, nesting and key order survive
     because the safest way not to break the rest of the file is not to
     rewrite the rest of the file.
  2. `GET /api/sessions/{id}` returned the whole session. A host left running
     here produced a 20.8 MB / 53,045-event file; unpaged that is a response
     no browser renders, and it is the judges' URL. Now paged — 818 KB per
     page — with the Replay screen loading the most recent page first and
     fetching earlier ones on request.
- Why the suite missed both: the routing fixture had no `pricing` block and
  the replay fixtures held a dozen events. Test data that is tidier than
  production data hides exactly the bugs that production data causes. Both
  fixtures now match the shape of the real thing.
- Also fixed: a Windows drive-relative session id escaped the sessions
  directory past a character blacklist (containment is now checked on the
  resolved path); a naive ISO timestamp raised TypeError past the ValueError
  guard in `check_availability`, which models trigger constantly because the
  schema says only "ISO timestamp"; `parse_batch` grew `sys.path` by one entry
  per batch; the summarizer queue was unbounded.
- One test I wrote is honest but weak and stays marked as such: the
  drive-relative canary passes against the old code too, because a
  nonexistent path 404s however it was resolved. The property-based
  containment test is the one that actually discriminates.
- **Voice cut, 30 Sep.** The week-1 gate (one agent on Nemotron inside a
  sandbox) was due 24 Sep and had not been met, because Token Factory and the
  VM were both still untouched. The build plan's own rule was to drop voice if
  that slipped past the 28th, so the call took about a minute rather than a
  day of hedging. Worth carrying into the feedback section: writing the
  decision rule down *in advance*, with a date attached, is what made it cheap
  — by the time you are deciding under pressure you have already lost the
  argument with yourself.
- The 30 seconds voice occupied went to the governance beat, which now has
  0:55–1:40 instead of 1:25–2:00. That is the strongest material in the video,
  and it was the beat most squeezed by a fixed three-minute cap.
- Removed voice from README, CLAUDE.md, the submission checklist and the
  prior-work disclosure. It is stated as cut in LEGACY.md rather than quietly
  omitted: that file is the disclosure a judge can check against the
  repository, and a silent omission reads worse than a stated cut.
- Kept the `voice` event kind in EVENT_KINDS. It is additive-only by design so
  old session files stay readable, and reviving voice later would need no
  migration. Commented to say so, since an unused enum member otherwise looks
  like an oversight.

## 2026-10-01 — Token Factory, read from the console

Browsed the console directly rather than trusting the build plan. Four things
worth recording, three of which could not have been guessed.

- **The base URL in the build plan is stale.** It says
  `https://api.studio.nebius.com/v1`. The real one is
  `https://api.tokenfactory.nebius.com/v1/` — the product was renamed and
  studio.nebius.com now redirects. Had we guessed, the first call would have
  failed in a way that looks like a bad key.
- **The routing keys use four different naming conventions across four models
  from the same vendor**: `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` (redundant
  prefix), `nvidia/nemotron-3-super-120b-a12b` (all lower), 
  `nvidia/Nemotron-3-Ultra-550b-a55b` (mixed), `nvidia/Nemotron-3_5-Lightning`
  (underscore for the point release). None inferable from the display names.
  This is the single best vindication of the plan's "do not guess them" rule,
  and it belongs in the feedback section verbatim.
- **No NVIDIA embedding model is served.** The only embedding endpoint is
  Qwen3-Embedding-8B. The plan predicted this ("most likely self-host on
  Nebius AI Cloud"), and it was right. **Open decision, needs making before
  week 4** — see below.
- **Public endpoints warn that availability and processing region may change
  without notice and break the current base_url.** For a demo URL that has to
  work for judges in December, that is a live risk. Dedicated endpoints are
  the production answer.

Real prices are now in `routing.yaml`, so the cost meter works. Nano $0.06 /
$0.24, Super $0.30 / $0.90, Ultra $1.00 / $3.00 per Mtok.

With real rates, `scripts/forecast.py` puts the entire six weeks of inference
at **$5.45**. The earlier estimate from measured token volume and invented
rates said about $5 — the point stands either way: inference is a rounding
error and GPU hours are the whole bill.

### Open decision: the embedding model

- **Self-host `llama-nemotron-embed-1b-v2`** on AI Cloud. Keeps the memory
  layer NVIDIA end to end, which is a direct hit on the "how effectively does
  it use NVIDIA models" criterion. Costs GPU hours and a chunk of week 4.
- **Use `Qwen3-Embedding-8B`** from Token Factory. $0.01/Mtok, one line of
  config, no infrastructure. But it is not an NVIDIA model, and the submission
  currently claims NVIDIA embeddings.

Whichever is chosen, `LEGACY.md` and the prior-work disclosure must match it.

### Also found

- `nvidia/Nemotron-3_5-Lightning`: same price as Nano, ~5x throughput, built
  for agentic tool use. Not in the build plan. Worth benchmarking for both
  `summarize` and `execute`.
- `NousResearch/Hermes-4-405B` is served — the plan's "cheap surface area"
  suggestion via `NEMOCLAW_AGENT=hermes` is available.
- A bug the new pricing surfaced: the fallback YAML parser did not unquote
  *keys*, only values. The pricing block is keyed by routing keys, which are
  quoted because they contain slashes — so on any VM without PyYAML the cost
  meter would have silently read "no rate". Fixed; the fallback now matches
  PyYAML exactly on the shipped file, which is asserted.
- Committing the base URL broke `test_env_example_holds_no_values`, correctly:
  the guard forbade *any* value. But the rule it should enforce is about
  secrecy, not emptiness — a public endpoint is not a credential, and having
  it wrong costs a debugging session. Rewritten as
  `test_env_example_holds_no_secrets` with an explicit `PUBLISHABLE_DEFAULTS`
  map, so a committed value is a decision somebody made rather than drift,
  plus a per-credential test so a failure names the variable that leaked.
  Verified by planting a fake key in `.env.example` and watching both fail.

## 2026-10-02 — the rules, read rather than assumed

Read the live Devpost rules instead of working from the build plan's 19 Sep
summary. Deadline confirmed unchanged (30 Oct, 10:00 PDT). Three corrections,
one of which changes the risk profile of the whole project.

- **"Token Factory *or* AI Cloud."** The eligibility requirement is an OR, not
  an AND. Token Factory alone qualifies. The build plan's framing implied both
  were needed, which made NemoClaw look like a blocker to submitting at all.
  It is not. NemoClaw is what makes the governance *argument* real — losing it
  costs the thesis, not eligibility. That is a much smaller and more
  manageable risk than it looked yesterday.
- **The City Winner Award is gone.** The Official Rules limit it to "Entrants
  attending one of the following participating IRL city events". London was
  15 Sep. The resources page says attendance is not required; the Official
  Rules say it is. Where two official sources disagree, the rules govern.
  Removed from the prize strategy rather than left as a hopeful line.
- **Most Valuable Feedback is the best-value prize left**: $100 + swag, ten
  winners, and the criterion is literally completing the feedback section —
  which is a required submission field anyway. The build log is already the
  raw material for it.

Credits: $50 Token Factory ($25 promo + $25 Builders Program) against a
measured $5.45 forecast, so inference is covered nine times over. **No AI
Cloud credits** — GPU hours are out of pocket, and they are the entire bill.

Also noted: the demo requirement reads "a URL to a working demo, hosted
application, **or test build**", which is softer than assumed, and 16,309
entrants are registered — so a track award plus the Tavily bonus remains the
realistic ceiling, as the plan said.
- Verified the full prize table. Overall Awards are $20,000 / $10,000 /
  $6,000; the Personal AI track award is an NVIDIA Jetson Orin Nano, i.e.
  hardware, not cash. All the money sits in the three Overall Awards.
- The useful part: Overall eligibility reads "All Eligible Submissions", so
  every entry is automatically in that pool. Entering a track does not forfeit
  it. The stacking rule caps what a project can *win*, not what it is judged
  for — which means there is no strategy to play, only a submission to make
  good. Worth knowing, because the build plan's framing ("the realistic
  ceiling is track winner plus Tavily") reads as though aiming lower were a
  choice being made.

## 2026-10-02 — NemoClaw prerequisites: no GPU

Read the official docs
(<https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/get-started/prerequisites>)
rather than inferring from the build plan. The plan says the VM "needs Linux,
containers, a GPU". The GPU half is wrong for our architecture.

**The hardware table lists CPU, RAM and disk. There is no GPU row.**

| Resource | Minimum | Recommended |
|---|---|---|
| CPU | 4 vCPU | 4+ vCPU |
| RAM | 8 GB | 16 GB |
| Disk | 20 GB free | 40 GB free |

CUDA appears twice in the whole page: once for N1x FASTOS, a *deferred*
platform we are not using, and otherwise only around **local** model serving
— managed vLLM, Ollama, llama.cpp. We do none of that. Inference is routed to
Token Factory, which the docs treat as a first-class path ("Choose an
Inference Provider ... routed inference configuration").

So the VM is a **plain CPU box**, roughly an order of magnitude cheaper than
the GPU instance the plan implied. Given there are no AI Cloud credits, this
is the single largest cost decision in the project and it was based on a
requirement that does not exist.

Software: Node.js 22.19+, npm 10+, Python 3, and Docker Engine/Desktop/Colima
(or qualified rootless Podman). All already satisfied locally.

### Why not run it on the laptop

Windows WSL2 is a supported platform ("Tested with limitations", Docker
Desktop backend). Tempting, because it would cost nothing. But this machine
has **7.8 GB of RAM — under the 8 GB minimum** — and the docs are specific
about what happens:

> On machines with less than 8 GB of RAM, this combined usage can trigger the
> OOM killer. If you cannot add memory, configure at least 8 GB of swap.

4 logical cores, exactly the minimum. And the agent host would be competing
with Next.js and a browser. The build plan already reached the same
conclusion from the other direction: "8 GB — workable, but keep Docker off
the laptop entirely and develop against the remote VM."

Decision: small CPU-only cloud VM. Not the laptop, not a GPU instance.

### Already on the machine

`wsl --list` shows an `OpenClawGateway` distribution (Ubuntu 24.04.5 LTS)
alongside `docker-desktop`. Neither `nemoclaw` nor `openshell` is installed
inside it, so this is a leftover scaffold from an earlier attempt rather than
a working install. Worth clearing or at least knowing about before onboarding,
since the docs warn against managing OpenShell separately from
`nemoclaw onboard`.

Ubuntu 24.04 is the docs' primary validated path, which is the right target
for the VM image too.
- Built `packages/memory` while waiting on credentials: pgvector schema,
  embedding client and vector recall. Week-4 work pulled forward, so week 4
  becomes "point it at Supabase" rather than "write the memory layer".
- The schema adds `embedding_nv` **beside** any existing column rather than
  altering it, and records `embedding_model` per row. A swap is a re-index,
  and a re-index that fails with no fallback column means recomputing
  everything. `memory_rows_needing_embedding` makes the re-index resumable.
  Grounding lives in its own table so re-running the nightly pass never
  rewrites the rows being checked.
- `embeddings.provenance()` derives the README claim from configuration
  rather than prose, so the submission cannot drift into claiming an NVIDIA
  embedding model it is not using.
- Two bugs the new tests caught, both of the kind that look fine until they
  do not:
  1. The demo embedding unpacked SHA-256 bytes as IEEE-754 floats. Some
     inputs decode to **NaN**, and because every comparison with NaN is false,
     a single poisoned vector silently dropped the correct top hit out of a
     sorted result — recall returned a 0.0 match while an exact 1.0 match sat
     in the same list. Now mapped from integers into [-1, 1), with a test that
     every component is finite.
  2. `recall` defaulted to `min_score=0.0`, which discarded every negative
     cosine — about half the rows — so a kind-filtered recall came back empty
     while relevant rows existed. Default is now no floor; cutting off a
     ranked result is a caller's decision.

## 2026-10-04 — nightly synthesis

`jobs/` only did grounding, while the README claimed "Nebius Serverless Jobs:
nightly memory synthesis". Built the synthesis pass so the claim is true.

It reads the day's event log, asks Ultra what is worth remembering, and writes
the result to the memory store. This is the only place in LifeOS that writes
to memory without a human in the loop, so it is built to be distrusted:

- Every proposal must cite the event ids it came from; no citation, no row. A
  memory you cannot trace is one you cannot later correct.
- A proposal whose words do not overlap its cited events is dropped. Cheap,
  and it catches the obvious failure of the model summarising its own prior
  knowledge instead of the log.
- Near-duplicates of existing rows are skipped, so running nightly does not
  slowly fill memory with restatements.
- `MAX_NEW_ROWS` bounds the damage from one bad night.
- Without a client it writes nothing and says so, rather than guessing.

`main()` runs synthesis then grounding, so a claim learned tonight is verified
in the same run rather than sitting unverified until tomorrow.

### Found by running it

The first run fed **3,606 events** — about 72k tokens — into the prompt,
almost all of it `DEMO_LOOP` repeating the same 18 lines. Added `condense()`,
which collapses identical agent+summary pairs to their first occurrence with a
repeat count, then keeps the most recent 1,200. The same session now yields
**18 events**, a 99.5% reduction, and the cost of a night's synthesis drops
from $0.072 to $0.0004 at the real Ultra rate.

The reduction is incidental; the real gain is that the model now reads a day
rather than 3,600 lines of noise. An agent doing the same thing forty times is
one fact, not forty.
