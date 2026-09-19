# LifeOS — an always-on personal chief of staff you can watch and interrupt

LifeOS is a private, always-on personal assistant with persistent memory and
its own skills. This repository is the build that moves it onto **NVIDIA
Nemotron 3** models served by **Nebius Token Factory**, puts every agent inside
an **OpenShell** sandbox under **NemoClaw**, and adds **Glass Box** — a web
control plane that makes everything the agents do visible and stoppable.

The governance problem is the point. An agent with access to your calendar,
inbox and contacts, running unattended, is only acceptable if you can see what
it is doing and stop it mid-action from your phone.

> **Status: week 1 of 6.** Everything below either runs today or is marked as
> not built. Nothing has yet made a real inference call — the Token Factory
> model ids are still placeholders, and the client refuses to call out until
> they are replaced, deliberately.

## Try it — no credentials, no VM, no GPU

```bash
git clone <this repo> && cd lifeos-nemotron
python -m pip install -r requirements.txt
npm install --prefix apps/glassbox
./scripts/demo.sh
```

Glass Box on <http://localhost:3000>, the agent host on <http://localhost:8000>.

`DEMO=true` is the default, and it fails closed: if `DEMO` is unset or
misspelt, the system reads synthetic fixtures rather than a real inbox. A
scripted agent session drives the timeline, so every screen has something real
to render.

## What works today

| | |
|---|---|
| **Timeline** | Live event stream over WebSocket, with backfill and reconnect. Filterable by kind. |
| **Approvals** | A sandbox reaching a host outside its allowlist surfaces as a card. Phone-first: one tap to deny, and the decision is logged. |
| **Memory** | What LifeOS believes, with provenance. Claims about the outside world are marked confirmed, stale or contradicted by the nightly grounding pass. |
| **Routing** | The three Nemotron tiers with per-tier latency, tokens and spend. Switching a tier rewrites `routing.yaml`, hot-reloaded, nothing restarts. |
| **Inference adapter** | Agent SDK ↔ OpenAI tool-schema translation, message-history rewrite, and JSON repair for almost-valid arguments. Fully tested offline. |
| **Agent loop** | The replacement for the Agent SDK's orchestration. Refuses tools marked as needing approval, treats tool output as data not instructions, and caps turns and tool calls. |
| **Sandbox driver** | A `SandboxDriver` interface with a real NemoClaw implementation and a fake one. Demo mode runs the fake. |
| **Tavily** | The Research agent's search tool, and the memory-grounding pass. |
| **Nano summarization** | Batched rewrite of raw log lines into the activity feed. Built and tested; dormant until a Token Factory key and real model ids exist. |

**Not built yet:** voice (Parakeet + Pipecat), the embedding swap, session replay, editing a memory fact from the UI, and any
real model call.

## Where NVIDIA and Nebius are used

| Component | Used for | Status |
|---|---|---|
| Nemotron 3 Ultra | Daily planning, nightly memory synthesis and grounding | routed, awaiting model id |
| Nemotron 3 Super | Agent execution — the default working tier | routed, awaiting model id |
| Nemotron 3 Nano | Activity-feed summarization, classification | routed, awaiting model id |
| Nebius Token Factory | All LLM inference, OpenAI-compatible endpoint | client built |
| NemoClaw + OpenShell | Per-agent sandboxing with egress allowlists | driver built, CLI unverified |
| NVIDIA embeddings | pgvector memory index | week 4 |
| NVIDIA Parakeet | Voice input | week 4 |
| Nebius AI Cloud | GPU VM hosting the host, sandboxes and voice | week 1 |
| Nebius Serverless Jobs | Nightly memory synthesis and grounding | job written, not yet deployed |
| Tavily | Research search, memory-claim grounding | built |

No other inference provider is used, and adding one is prohibited by
`CLAUDE.md`. Agents never call a model API directly — everything goes through
`complete()` in `packages/inference/client.py`, which is what makes the routing
screen and the cost meter possible at all.

## Layout

    apps/glassbox      Next.js control plane
    apps/host          agent host: nemoclaw wrapper, events, API (VM only)
    packages/inference Token Factory client, tool translation, routing.yaml
    packages/agents    calendar, email, research (ported)
    packages/memory    Supabase + pgvector + NVIDIA embeddings
    voice/             Parakeet + Pipecat pipeline (VM only)
    jobs/              Nebius Serverless Jobs
    fixtures/          demo-mode data
    infra/policies/    OpenShell egress allowlists, one per agent
    docs/              SPEC.md, BUILD-LOG.md, WEEK1-UNKNOWNS.md, DEMO-SCRIPT.md

## Sandboxing

One allowlist per agent in `infra/policies/`, each deliberately minimal and
denying by default. The Calendar agent cannot reach a search API; the Research
agent cannot reach your inbox. Tests assert both, because a regression there is
invisible in the UI and fatal to the argument the project is making.

## Tests

```bash
python -m pytest
npm run typecheck --prefix apps/glassbox
```

326 tests, all offline. Nothing in the suite reaches a network or spends a
credit — the inference transport, the sandbox driver and the search client are
all injectable, and recorded fixtures stand in for live responses. That is not
tidiness: burning Token Factory credits on debug loops is a real way to lose a
week later on.

`tests/test_demo_mode.py` is the demo-mode audit, run on every commit rather
than once by hand in week five.

## Demo mode

`DEMO=true` swaps every data source for synthetic fixtures — a fake inbox,
calendar, contact graph, memory store and recorded search results. Real data
never leaves the VM. Every address sits on an RFC 2606 reserved domain and
every URL is unresolvable, both enforced by tests.

Fixture dates rebase by whole weeks onto the current week, so the demo day
always looks live and its weekdays stay consistent with the prose in the
fixtures.

## Prior work

LifeOS existed before the Submission Period. `LEGACY.md` records exactly what
was carried over and what was built during it. The CRM, Networking, Internship
and Content agents are pre-existing and out of scope for this build.

## Licence

MIT. See `LICENSE`.
