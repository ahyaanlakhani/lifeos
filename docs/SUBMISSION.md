# Submission

Deadline **Fri 30 Oct 2026, 10:00 PDT** (18:00 London). Submit **28 Oct**, two
days early. Nothing new goes in after 26 Oct.

**Verified against the live Devpost rules on 2 Oct 2026.** Deadline unchanged.
16,309 participants registered. Re-check again before submitting.

<https://nebiusglobalaihackathon.devpost.com/rules>

## The requirement, read exactly

> All submissions must run on either Nebius Token Factory **or** Nebius AI
> Cloud and use at least one NVIDIA open source model.

It is an **OR**. Token Factory alone satisfies eligibility — the GPU VM is not
required to enter. The build plan assumed both were needed, and that framing
made NemoClaw look like a blocker to submitting at all. It is not. It is a
blocker to the *governance argument*, which is a different and smaller risk.

The Personal AI track names "tools such as NVIDIA NemoClaw, OpenShell, Hermes
Agent, and Nebius Serverless". "Such as" is suggestive, not mandatory.

The demo requirement is also softer than assumed: "a URL to a working demo,
**hosted application, or test build**".

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
- [ ] Claim the $25 promo credits (code `NEBIUS-DEVPOST-GLOBAL26`) and join
      the Builders Program for the second $25
- [ ] README: setup, how to run, where Nemotron is used, where Token Factory
      accelerated the work, other Nebius services used
- [ ] Feedback on Token Factory, AI Cloud and the NVIDIA tooling — write this
      from `BUILD-LOG.md`, not from memory on the last day
- [ ] What-changed disclosure for the pre-existing work
- ~~City selection~~ — not eligible, no event attended (see above)

## Prizes, verified 2 Oct 2026

| | Prize | Qty | Eligibility as written |
|---|---|---|---|
| **Overall** | Grand Prize **$20,000** | 1 | All Eligible Submissions |
| | 2nd Place **$10,000** | 1 | All Eligible Submissions |
| | 3rd Place **$6,000** | 1 | All Eligible Submissions |
| **Track** | Personal AI — *NVIDIA Jetson Orin Nano* | 1 | All submissions in the track |
| **Bonus** | Best Use of Tavily **$3,000** | 1 | Functional runtime Tavily call |
| | City Winner $500 | 20 | Entrants attending an IRL event — not us |
| | Most Valuable Feedback $100 + swag | 10 | Complete the feedback section |

**The track award is hardware, not cash.** All the money is in the three
Overall Awards.

> Each Project is eligible for one (1) Overall Award OR one (1) Track Award
> and one (1) Bonus Award.

**There is no trade-off to manage.** Overall eligibility is "All Eligible
Submissions" — every entry is automatically considered. You do not pick a pool
or forfeit one by entering a track. The rule caps what a project may *win*,
not what it is judged for. So the only lever is making the submission as good
as possible; there is nothing to hedge.

Best realistic outcome: **$20,000 + $3,000 = $23,000.** Floor, if the project
lands well in its track: a Jetson + $3,000.

## Prize strategy

- **Tavily ($3,000)** needs only a functional runtime call. Done — the Research
  agent's search tool and the nightly grounding pass. Far fewer entrants
  contest this than the overall prizes.
- **Nebius Builder Program** — credits for Token Factory, Tavily and Nebius
  Academy. Join it.
- ~~**Builders & Brews, London**~~ — **not available.** The Official Rules
  restrict City Winner Awards to "Entrants attending one of the following
  participating IRL city events". London was 15 Sep and has passed. The
  resources page claims attendance is not needed; the Official Rules say it
  is, and the rules govern. Remaining events are Boston (2 Oct), SF (9 Oct)
  and LA (13 Oct) — all US. Treat this prize as gone.
- **Most Valuable Feedback** — $100 + NVIDIA swag, **10 winners**, and the
  stated criterion is simply "All Eligible Submissions that complete the
  feedback submission section". Best effort-to-odds ratio on the board.

### Credits

- $25 Token Factory credits via the promo form, activation code
  `NEBIUS-DEVPOST-GLOBAL26`
- $25 more by joining the Nebius Builders Program (also the Tavily credits)

$50 total. The measured forecast for the entire six weeks of inference is
**$5.45**, so inference is covered roughly nine times over.

**No AI Cloud credits are provided.** The only mention is that Builders &
Brews attendees "can also unlock additional Nebius AI Cloud, Token Factory,
Tavily credits" — and those events are past or overseas. So GPU hours come out
of pocket, which is the entire bill. Stop the VM when not using it.

## The four criteria, equally weighted

| Criterion | Where this project stands |
|---|---|
| Technological implementation | NemoClaw, OpenShell, three Nemotron tiers, NVIDIA embeddings |
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
> - Moved nightly memory synthesis onto Nebius Serverless Jobs using
>   Nemotron 3 Ultra, including a Tavily-backed grounding pass that marks
>   remembered claims confirmed, stale or contradicted
> - Built a synthetic demo mode so the system is publicly runnable without
>   personal data
>
> The four remaining agents are carried over largely unchanged and are marked
> as such in `LEGACY.md`.

Fill in N from `git diff --stat` against the first commit. Do not round up.

Voice was cut on 30 Sep and is deliberately absent from the list above. Do not
disclose work that was not done — the disclosure is the one part of the
submission a judge can check against the repository.

## Feedback section — raw material

Write from `docs/BUILD-LOG.md`. Specific beats generic, and specificity is
visible to anyone reading it. Threads worth developing, already logged:

- NemoClaw is alpha with thin docs; the packaged agent skills for coding
  assistants were the intended mitigation — did they help?
- What the three week-one unknowns turned out to be, and how much design
  hinged on them
- Tool-calling reliability on Nemotron versus what the adapter had to absorb
- Whether Token Factory served the embedding model, or whether self-hosting
  on AI Cloud was needed
- Cutting voice on 30 Sep: the schedule had a decision rule for it, and having
  the rule written down in advance made the call cost about a minute instead
  of a day of hedging
- Serverless Jobs for the nightly pass: cold starts, scheduling, cost
