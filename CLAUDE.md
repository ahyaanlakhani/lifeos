# LifeOS — Nebius x NVIDIA Hackathon

## What this is
An always-on personal assistant (LifeOS) running NVIDIA Nemotron models on
Nebius Token Factory, with agents sandboxed under NemoClaw/OpenShell, and a
web control plane (Glass Box) making agent activity visible and stoppable.

Deadline: 30 Oct 2026, 10:00 PT. Personal AI track. Feature freeze 22 Oct.
Video shot by 26 Oct. Submit 28 Oct.

## Non-negotiables
- All LLM inference goes through Token Factory. Never add another provider.
- Agents never call an inference API directly. Always use complete() from
  packages/inference/client.py.
- Every agent action emits an Event. No silent work.
- DEMO=true must run the whole system with zero real credentials.
- No real personal data in fixtures, commits or screenshots. Ever.
- No personal name anywhere in the repo. It is "LifeOS".
- The agent host is the only thing that shells out to the nemoclaw CLI.
  Glass Box must never shell out — it would break separate deployment of the
  judges' demo URL.
- Never guess NEBIUS_BASE_URL or a Nemotron model id. They come from the
  Token Factory console and live in routing.yaml / .env.

## Layout
- apps/glassbox        Next.js control plane (laptop in dev, Nebius in prod)
- apps/host            agent host: nemoclaw wrapper, events, API (VM only)
- packages/inference   Token Factory client, tool translation, routing.yaml
- packages/agents      calendar, email, research (ported); others are legacy
- packages/memory      Supabase + pgvector + NVIDIA embeddings
- voice/               Parakeet + Pipecat (VM only)
- fixtures/            demo-mode data
- infra/policies/      OpenShell egress allowlists, one per agent
- jobs/                Nebius Serverless Jobs (nightly synthesis)
- docs/                SPEC.md (source of truth), BUILD-LOG.md, WEEK1-UNKNOWNS.md

## Model routing
packages/inference/routing.yaml, hot-reloaded:
- plan      -> Nemotron 3 Ultra   (daily planning, nightly synthesis)
- execute   -> Nemotron 3 Super   (agent work, default tier)
- summarize -> Nemotron 3 Nano    (event feed, classification)

Develop against Nano. Never hardcode a model id in agent code.

## Legacy
CRM, Networking, Internship and Content agents are pre-existing and OUT OF
SCOPE. Do not refactor, migrate or tidy them. See LEGACY.md.

## Conventions
- Python 3.11 + uv. TypeScript for glassbox. No other languages.
- Tests run against recorded fixtures in tests/fixtures. Never hit live APIs
  in tests.
- Conventional commits.

## Working style
- Read only the files needed for the task. Do not survey the repo.
- Ask before adding a dependency.
- Prefer editing existing files over creating new ones.
- Keep responses short. Do not re-explain code you just wrote.
- Avoid subagents. Point at files instead.
