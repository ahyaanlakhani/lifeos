# LifeOS — an always-on personal chief of staff you can watch and interrupt

LifeOS is a private, always-on personal assistant with persistent memory and
its own skills. This repository is the build that moves it onto **NVIDIA
Nemotron 3** models served by **Nebius Token Factory**, puts every agent inside
an **OpenShell** sandbox under **NemoClaw**, and adds **Glass Box** — a web
control plane that makes everything the agents do visible and stoppable.

The governance problem is the point: an agent with access to your calendar,
inbox and contacts, running unattended, is only acceptable if you can see what
it is doing and stop it mid-action from your phone.

> Status: week 1 of 6. Scaffolding. Nothing below is verified working yet —
> this README is written incrementally, not at the end.

## Where NVIDIA and Nebius are used

| Component | Used for |
|---|---|
| Nemotron 3 Ultra | Daily planning pass, nightly memory synthesis |
| Nemotron 3 Super | Agent execution — the default working tier |
| Nemotron 3 Nano | Activity-feed summarization, event classification |
| Nebius Token Factory | All LLM inference, OpenAI-compatible endpoint |
| NemoClaw + OpenShell | Per-agent sandboxing with egress allowlists |
| NVIDIA embeddings | pgvector memory index |
| NVIDIA Parakeet | Voice input |
| Nebius AI Cloud | GPU VM hosting the agent host, sandboxes and voice |
| Nebius Serverless Jobs | Nightly memory synthesis |
| Tavily | Research agent search + memory-claim grounding |

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
    docs/              SPEC.md, BUILD-LOG.md, WEEK1-UNKNOWNS.md

## Setup

    cp .env.example .env     # DEMO=true needs no real credentials

Full setup, the run instructions and the Token Factory notes land here as each
piece starts working.

## Demo mode

`DEMO=true` swaps every data source for synthetic fixtures. The whole system
runs with zero real credentials. See `fixtures/README.md`.

## Prior work

LifeOS existed before the Submission Period. `LEGACY.md` records exactly what
was carried over and what was built during it.

## Licence

MIT. See `LICENSE`.
