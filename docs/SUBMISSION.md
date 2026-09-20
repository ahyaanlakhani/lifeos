# Submission

Deadline **Fri 30 Oct 2026, 10:00 PT** (18:00 London). Submit **28 Oct**, two
days early. Nothing new goes in after 26 Oct.

Re-check the rules on Devpost before submitting — they state they may change.

## Checklist

- [ ] Working project on Nebius using at least one NVIDIA open model
- [x] Track selected: **Personal AI**
- [ ] Project description — what, why, how. Lead with the always-on private
      assistant with persistent memory and its own skills, **not** with the
      dashboard. Stage one of judging is pass/fail on whether the project
      genuinely attempts the track's goal.
- [ ] Working demo URL, reachable in demo mode without your credentials
- [ ] Public YouTube video, 3:00 or under, with audio
- [x] Public repo with an OSS licence visible at the top of the page — MIT,
      committed in the first commit.
      <https://github.com/ahyaanlakhani/lifeos>
- [ ] README: setup, how to run, where Nemotron is used, where Token Factory
      accelerated the work, other Nebius services used
- [ ] Feedback on Token Factory, AI Cloud and the NVIDIA tooling — write this
      from `BUILD-LOG.md`, not from memory on the last day
- [ ] What-changed disclosure for the pre-existing work
- [ ] City selection if you attended a Builders & Brews event

## Prize strategy

One Overall Award **or** one Track Award, plus one Bonus Award. The realistic
ceiling is Personal AI track winner plus Best Use of Tavily.

- **Tavily ($3,000)** needs only a functional runtime call. Done — the Research
  agent's search tool and the nightly grounding pass. Far fewer entrants
  contest this than the overall prizes.
- **Nebius Builder Program** — credits for Token Factory, Tavily and Nebius
  Academy. Join it.
- **Builders & Brews, London** — $500 pool with a much smaller field.
- **Most Valuable Feedback** — its own category, and a required field anyway.

## The four criteria, equally weighted

| Criterion | Where this project stands |
|---|---|
| Technological implementation | NemoClaw, OpenShell, three Nemotron tiers, NVIDIA embeddings, Parakeet |
| Design | Glass Box exists for exactly this. A quarter of the score. |
| Potential impact | Argue the **governance** problem, not "personal assistant" generally |
| Quality of the idea | Visible agent governance is the non-obvious part |

Equal weighting is the key insight: a technically strong project with a rough
interface scores no better than a well-built one that looks finished.

## Prior work disclosure (draft)

Adapt to what is actually true on submission day.

> **Prior work.** LifeOS began as a personal project before the Submission
> Period. What existed beforehand: an architecture and build guide for a
> seven-agent personal assistant, a React dashboard, and a master system
> prompt. Its agents ran on closed models through the Claude Agent SDK, on a
> single unisolated VPS, with no runtime visibility.
>
> **Built during the Submission Period.** Every NVIDIA and Nebius component in
> this submission is new work:
>
> - Ported the Calendar, Email and Research agents off the Claude Agent SDK
>   onto NVIDIA Nemotron 3 via Nebius Token Factory, including a new
>   tool-calling adapter and per-agent prompt rework
> - Moved every agent into an OpenShell sandbox under NemoClaw, with explicit
>   network egress policy per agent
> - Built Glass Box, the control plane: live timeline, mobile approval flow,
>   memory view with provenance, model routing with cost telemetry, and session
>   replay — entirely new, roughly N thousand lines
> - Replaced the memory embedding model with NVIDIA's Nemotron embedding model
>   and re-indexed the vector store
> - Added a voice interface built on NVIDIA Parakeet
> - Moved nightly memory synthesis onto Nebius Serverless Jobs using
>   Nemotron 3 Ultra, including a Tavily-backed grounding pass that marks
>   remembered claims confirmed, stale or contradicted
> - Built a synthetic demo mode so the system is publicly runnable without
>   personal data
>
> The four remaining agents are carried over largely unchanged and are marked
> as such in `LEGACY.md`.

Fill in N from `git diff --stat` against the first commit. Do not round up.

## Feedback section — raw material

Write from `docs/BUILD-LOG.md`. Specific beats generic, and specificity is
visible to anyone reading it. Threads worth developing, already logged:

- NemoClaw is alpha with thin docs; the packaged agent skills for coding
  assistants were the intended mitigation — did they help?
- What the three week-one unknowns turned out to be, and how much design
  hinged on them
- Tool-calling reliability on Nemotron versus what the adapter had to absorb
- Whether Token Factory served the embedding and speech models, or whether
  self-hosting on AI Cloud was needed
- Serverless Jobs for the nightly pass: cold starts, scheduling, cost
