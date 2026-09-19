# Pre-existing modules

LifeOS existed before the Submission Period (opened 18 Sep 2026). This file
records honestly what is carried over and what is new, so that the
what-changed disclosure in the submission matches the repository.

## Carried over, unchanged, OUT OF SCOPE for this build

These agents keep running however they run today. They are not migrated to
Nemotron, not sandboxed, and not refactored.

| Module | Status |
|---|---|
| CRM agent | pre-existing, unchanged |
| Networking agent | pre-existing, unchanged |
| Internship agent | pre-existing, unchanged |
| Content agent | pre-existing, unchanged |
| LifeOS master system prompt | pre-existing; per-agent adaptations layered on top are new |
| LifeOS dashboard (React) | pre-existing; Glass Box is a new surface beside it |
| Supabase schema + pgvector store | pre-existing; the NVIDIA embedding column is new |
| n8n scheduled workflows | pre-existing; work touching ported agents moves to Serverless Jobs |

## Built during the Submission Period

Everything under:

- `packages/inference/` — Token Factory client, tool-schema adapter, routing
- `apps/host/` — agent host, event stream, approvals API
- `apps/glassbox/` — the Glass Box control plane
- `infra/policies/` — OpenShell egress allowlists
- `voice/` — Parakeet + Pipecat pipeline
- `jobs/` — Nebius Serverless Jobs
- `fixtures/` — synthetic demo mode

plus the Nemotron port of the Calendar, Email and Research agents, and the
swap of the memory embedding model to NVIDIA's.

Carried-over source files carry a `LEGACY:` header comment.
