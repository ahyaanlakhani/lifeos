# LifeOS on Nemotron — Build Spec (source of truth)

_Text extracted from LifeOS-on-Nemotron-Build-Spec.pdf, 2026-09-18. This file is the reference; do not re-read the PDF._


=============== PAGE 1 ===============
LifeOS on Nemotron — Hackathon Build
Spec
 2026-09-18  ·  @Someone
The submission in one paragraph
Track: Personal AI. Project: LifeOS — the always-on personal chief of staff — ported onto
NVIDIA open models running on Nebius, wrapped in OpenShell sandboxes, and given a
web control plane called Glass Box that makes everything the agents do visible and
stoppable.
The pitch to judges: I had a personal OS running closed models on an unisolated VPS.
During the submission period I moved its inference onto open Nemotron models via Nebius
Token Factory, moved its memory onto NVIDIA embeddings, gave it a voice interface built
on NVIDIA Parakeet, put every agent inside an OpenShell sandbox under NemoClaw, and
built the control plane that makes running an autonomous agent over my own life
something I can actually watch and interrupt.
That narrative works because the NVIDIA and Nebius components are load-bearing
rather than decorative. Remove them and there is no project.
Hackathon facts and prize strategy
Taken from the official Devpost rules on 19 September 2026. Re-check before submitting
— the rules state they may change at any time.
Dates
Milestone When
Submission closes Fri 30 Oct 2026, 10:00 PT (18:00 in London)
Judging 1–15 Dec 2026
Winners announced ~11 Jan 2027
LifeOS on Nemotron — Hackathon Build Spec
Page 1 of 29
=============== PAGE 2 ===============
Prizes
The stacking rule — this matters
Each project is eligible for one Overall Award OR one Track Award, plus one Bonus
Award. So the realistic ceiling for this project is Personal AI Track winner plus Best Use of
Tavily, or an Overall placing plus Tavily.
The Tavily bonus requires only a functional runtime call to the Tavily API as part of the
solution. Your Research agent already needs web search. That is $3,000 sitting behind
maybe a day of work, contested by far fewer entrants than the overall prizes. Add Tavily.
Two further cheap wins. The Nebius Builder Program hands out credits for Token Factory,
Tavily and Nebius Academy — join it. And London is on the Builders & Brews city list; if you
can attend one, that is a $500 pool with a much smaller field.
Also complete the feedback section regardless. It is its own prize category, and it is a
required submission field anyway.
Judging criteria — four, equally weighted
Stage one is pass/fail: does the project genuinely attempt the track's stated goal rather
than being a superficial rebrand of an unrelated idea? LifeOS is a real always-on private
assistant with persistent memory and its own skills, so it passes cleanly — but the
framing in the description must lead with that, not with the dashboard.
Stage two, all weighted equally:
Award Value
Grand Prize $20,000
2nd place $10,000
3rd place $6,000
Each track winner (4) NVIDIA Jetson Orin Nano
Best Use of Tavily $3,000
City Winner Awards $500 × 20
Most Valuable Feedback $100 + NVIDIA swag, ×10
LifeOS on Nemotron — Hackathon Build Spec
Page 2 of 29
=============== PAGE 3 ===============
Equal weighting is the key insight. Design counts as much as implementation, which is
unusual for a hackathon and plays directly to your strengths. It also means a technically
brilliant project with a rough interface scores no better than a well-built one that looks
finished.
Architecture — where everything runs
The single most important design decision: almost nothing heavy runs on your laptop.
Five tiers.
Criterion What it asks Where LifeOS wins or loses
Technological
Implementation
How well built, and how
effectively does it use Nebius
and NVIDIA models?
Strong — NemoClaw,
OpenShell, three Nemotron
tiers, NVIDIA embeddings,
Parakeet
Design A complete, coherent product
experience, not a proof of
concept
Strong — this is exactly why
Glass Box exists
Potential Impact A credible, specific case for a
real problem and a real
audience
Needs care — argue the
governance problem, not
"personal assistant" generally
Quality of the Idea Creative, non-obvious use of
the models; genuine
understanding of the problem
space
Strong — visible agent
governance is non-obvious
Tier What lives here Why
Your laptop Next.js dev server, browser, editor,
git
Authoring only
Nebius AI Cloud
VM
NemoClaw + OpenShell
sandboxes, LifeOS agent host,
Parakeet voice service
Needs Linux, containers, a GPU
Nebius Token
Factory
Nemotron 3 Nano / Super / Ultra
inference
OpenAI-compatible API, no GPU
management
Supabase Postgres + pgvector memory store Already in LifeOS
LifeOS on Nemotron — Hackathon Build Spec
Page 3 of 29
=============== PAGE 4 ===============
Glass Box is a Next.js app that talks to two things: the agent host on the VM over
WebSocket for live events, and Token Factory directly for its own summarization calls.
The agent host is the piece everything hinges on — a small Python or Node service sitting
beside the NemoClaw sandbox that shells out to the nemoclaw  CLI, tails sandbox logs,
watches the workspace files, and exposes a REST + WebSocket surface. Build it first.
Nothing else works until it does.
One detail worth knowing early: NemoClaw ships a documented path for deploying to
remote GPU instances. That is the path you want, not local installation.
Hardware: is an 8–16 GB laptop enough?
Yes. Your laptop is a development machine and a browser, not an inference machine.
Every model in this project runs on Nebius.
What your laptop actually does
Next.js dev server, a browser with a few tabs, VS Code or Cursor, git, an SSH session to
the VM. That is a normal web development workload.
16 GB — comfortable. You can also run Docker locally to test an OpenShell sandbox
before pushing to the VM.
8 GB — workable, but keep Docker off the laptop entirely and develop against the
remote VM. Close Slack and Spotify while the dev server runs. Expect to babysit
browser tabs.
Disk matters more than people expect: budget 25–30 GB free. Node modules, Python
environments, container layers if you run any, and recorded demo footage add up fast.
What your laptop absolutely cannot do
Do not attempt to run Nemotron locally. Nemotron 3 Nano is 30B total parameters; even
heavily quantized that is well past 16 GB, and the Super and Ultra tiers are not remotely in
range. This is not a limitation to work around — Token Factory exists precisely so you do
not need the hardware.
Tier What lives here Why
Nebius Serverless
Jobs
Nightly memory synthesis, LoRA
fine-tune runs
Bursty background work
LifeOS on Nemotron — Hackathon Build Spec
Page 4 of 29
=============== PAGE 5 ===============
The one genuine local possibility
Parakeet TDT 0.6B is only 600 million parameters and will run on CPU in roughly 2–3 GB. On
a 16 GB machine you could run voice transcription locally if you wanted an offline-privacy
story. On 8 GB, put it on the VM with everything else.
Operating system
This is the real constraint, not RAM. OpenShell does container and kernel-level
sandboxing, which points at Linux.
Linux laptop — everything works locally if you want it to.
Windows — use WSL2 for any local container work, or skip local entirely.
macOS — assume the remote VM path. Apple Silicon plus kernel-level Linux
sandboxing is the least likely combination to work smoothly, and debugging it is not
how you want to spend week one.
Verify NemoClaw's prerequisites page against your actual OS in the first two days. It
is alpha software; this is the assumption most likely to be wrong.
Software checklist
On the laptop
Tool Notes
Node.js 20 LTS or newer Next.js 15, Glass Box frontend
pnpm or npm pnpm is lighter on an 8 GB machine
Python 3.11+ Agent host, NeMo tooling
uv Much faster and lighter than pip for Python envs
Git + GitHub CLI Public repo, MIT licence on day one
VS Code or Cursor See the note below
SSH client Reaching the Nebius VM
ffmpeg Audio handling for the voice pipeline
Supabase CLI Local migrations against your existing schema
Nebius CLI Provisioning the VM and Serverless Jobs
LifeOS on Nemotron — Hackathon Build Spec
Page 5 of 29
=============== PAGE 6 ===============
Worth knowing: NemoClaw ships packaged agent skills designed to walk coding
assistants such as Cursor and Claude Code through setup, inference config, policy
management, monitoring and troubleshooting. Install those skills in week one. On alpha
software with thin documentation, that is a meaningful accelerant.
On the Nebius VM
Accounts
Nebius (Token Factory API key plus AI Cloud), Supabase, GitHub, YouTube for the demo
video. Google OAuth credentials if the Calendar and Email agents talk to real accounts —
though note that the June guide already routed around Google's CASA audit by using
gmail.send  rather than restricted scopes.
Optional but useful
Tailscale, so Glass Box on your laptop can reach the VM without exposing ports publicly.
Also the cleanest way to demo from a phone.
NVIDIA and Nebius surface map
Ordered by certainty. Everything in the first group is committed; the second group is
conditional on time.
Tool Notes
Ubuntu 22.04 or 24.04 Match whatever NemoClaw's prerequisites
specify
Docker / container runtime Required by OpenShell
NVIDIA drivers + container toolkit For GPU passthrough into containers
NemoClaw CLI curl -fsSL
https://www.nvidia.com/nemoclaw.sh | bash  —
then pin the version
Python 3.11+ with NeMo Parakeet inference, if self-hosting voice
Caddy or nginx TLS in front of the agent host
tmux Keeping the host alive across SSH drops
LifeOS on Nemotron — Hackathon Build Spec
Page 6 of 29
=============== PAGE 7 ===============
Committed
Nemotron 3, all three tiers. Ultra plans (55B active of 550B MoE, 1M context, built for
agent orchestration and long-horizon workflows). Super executes (120B with 12B active,
hybrid Mamba-Transformer MoE, also 1M context). Nano handles the cheap constant
work — summarizing the activity feed, classifying events. The tiering is visible in Glass
Box with live latency and cost.
NemoClaw + OpenShell + NVIDIA Agent Toolkit. Every LifeOS agent runs inside a
sandbox. Network egress is policy-controlled, and approval requests surface in Glass Box.
Nebius Token Factory. All LLM inference, via the OpenAI-compatible endpoint.
NVIDIA embeddings. Swap the pgvector embedding model to llama-nemotron-embed-
1b-v2  (NVIDIA Open Model License). Roughly a day including re-indexing, and it makes
the memory layer NVIDIA end to end.
NVIDIA Parakeet. Voice input. The Parakeet family tops the Hugging Face Open ASR
leaderboard; parakeet-tdt-0.6b-v3  is the current small workhorse. NeMo Speech also
ships an open-source Voice Agent framework built on Pipecat — streaming STT → LLM →
TTS with natural turn-taking and tool calling — so the pipeline is closer to assembly than
invention. Pair with MagpieTTS for speech out.
Nebius Serverless Jobs. Nightly memory synthesis with Ultra.
Conditional
LoRA fine-tune of Nemotron Nano on your own labelled email and task data, trained on
Nebius AI Cloud. Nano supports LoRA and full SFT. Highest-signal item on the list and
almost nobody attempts it in six weeks — but only start it if week four is calm.
NeMo Guardrails on agent outputs. Gives a clean two-layer governance story: OpenShell
controls what the agent can reach, Guardrails controls what it can say and do. Both
become panels in Glass Box.
Hermes as a second agent runtime. NemoClaw supports it via NEMOCLAW_AGENT=hermes .
Cheap surface area, and Hermes appears by name in the track brief.
Verify before designing around it
Token Factory definitely serves the Nemotron 3 tiers. The embedding and speech models
are NeMo/NIM components that you will most likely self-host on Nebius AI Cloud rather
than call from Token Factory. Confirm in the Token Factory console during week one.
LifeOS on Nemotron — Hackathon Build Spec
Page 7 of 29
=============== PAGE 8 ===============
The port: LifeOS onto Nemotron
LifeOS was designed around Claude Agent SDK against Anthropic models on a Hetzner
VPS. The hackathon requires NVIDIA open models on Nebius. Bridging that gap is the
project, and it is also the riskiest part of the schedule.
Scope decision: three agents, not seven
Port Calendar, Email and Research. Leave CRM, Networking, Internship and Content as
they are and disclose them as pre-existing. Seven agent ports plus a new frontend plus a
voice pipeline in six weeks is how this misses the deadline.
What has to change
1. Inference client. Token Factory is OpenAI-compatible, so the base URL and auth swap
is mechanical. The real work is tool-calling format — Claude Agent SDK's tool schema
and Nemotron's function-calling conventions differ. Write one adapter layer and route
all three agents through it.
2. Prompt adaptation. The LifeOS master prompt was tuned for a different model family.
Expect to rework the system prompt per agent. Budget real time here; it is usually
underestimated.
3. Orchestration. If the June design leaned on Agent SDK's loop, you need a
replacement. Simplest option is your own loop in the agent host. Ultra's long context
and orchestration strength means you can keep the loop fairly plain.
4. Sandboxing. Each agent process moves inside an OpenShell container with an explicit
egress allowlist — Google APIs, Token Factory, Supabase, nothing else.
5. Embeddings. Re-index pgvector against the NVIDIA embedding model. Keep the old
column until the new one is verified.
Routing policy
Make this table a config file, not hardcoded. Glass Box reads it and lets you override live,
which is both a real feature and the cleanest way to demo tiering on camera.
Model Used for
Nano Event summarization, classification, the Glass Box
activity feed
Super Agent execution — the default working tier
Ultra Daily planning pass, nightly memory synthesis,
anything multi-step
LifeOS on Nemotron — Hackathon Build Spec
Page 8 of 29
=============== PAGE 9 ===============
Glass Box
The agent host
A small service on the VM beside the sandbox. Responsibilities:
Shell out to the nemoclaw  CLI for sandbox lifecycle
Tail sandbox logs and normalize them into a typed event stream
Watch workspace files (agent identity, memory, config persist there) and emit diffs
Surface network approval requests and relay decisions back
Expose REST for commands, WebSocket for the live stream
Three unknowns to resolve in week one, because they determine what is buildable:
1. Can a network approval request be observed and answered programmatically, or is the
flow interactive-only? If interactive-only, the fallback is writing policy files and driving
the CLI — still demoable, but design for it early.
2. What exactly lands in the workspace files, and how often? The memory view depends
on that shape.
3. Can sandbox logs be tailed as a stream, or only polled?
Screens
Approvals must work well on a phone. It is the strongest thirty seconds of the demo video,
and "I denied it from my phone" only lands if the interface is genuinely built for that.
Screen Content
Timeline Live agent actions, each summarized by Nano
Approvals Egress requests as tap-to-approve cards, mobile-
first
Memory Workspace and pgvector diffs, browsable, editable,
with sources
Routing Nano/Super/Ultra selector with live latency and
spend
Voice Push-to-talk, live Parakeet transcript, resulting
actions
Replay Scrub back through a past session
LifeOS on Nemotron — Hackathon Build Spec
Page 9 of 29
=============== PAGE 10 ===============
Privacy and demo mode
The repository must be public. LifeOS holds your email, calendar, contacts and transfer-
application material. These two facts are in direct tension, and resolving it late is how
projects get pulled at the last minute.
Decide in week one
Build a seed-data demo mode from day one. A DEMO=true  flag that swaps every data
source for synthetic fixtures — a fake inbox, a fake calendar, a fake CRM, a fake contact
graph. Judges run this. You record the video against this. Your real data never leaves your
VM.
Retrofitting demo mode in week five is miserable and it is where deadlines die.
Repository hygiene
MIT or Apache 2.0 licence file committed on day one, visible at the top of the repo page
Rename everything to LifeOS — no personal name anywhere, which continues the
pass already done on the master prompt
.env.example  only; real .env  in .gitignore  from the first commit
Scrub git history before going public — a key committed in week two and removed in
week three is still in the history
No real contact names, email addresses or application material in fixtures, commits or
screenshots
On camera
Every frame of the demo video should be demo mode. Check the browser tab titles,
notification banners and any autofill dropdowns before recording — that is where real
data leaks into footage.
Schedule — 18 Sep to 30 Oct
Week 1 (18–24 Sep) — recon and spike
Repo public with licence on day one. Provision the Nebius VM. Install NemoClaw, pin the
version, never upgrade. Get one sandbox running with inference pointed at Token Factory.
Answer the three agent-host unknowns. Build the demo-mode fixture layer.
Gate: one existing LifeOS agent running on Nemotron inside an OpenShell sandbox. If this
slips past 28 Sep, cut voice from scope.
LifeOS on Nemotron — Hackathon Build Spec
Page 10 of 29
=============== PAGE 11 ===============
Week 2 (25 Sep–1 Oct) — agent host
Adapter layer, event stream, Timeline screen. First real demo moment: agent actions
appearing live in a browser.
Week 3 (2–8 Oct) — approvals and the other two agents
Approval flow end to end, working on a phone. Calendar and Research agents ported.
Week 4 (9–15 Oct) — memory and voice
Embedding swap and re-index. Memory diff view. Nightly synthesis as a Serverless Job
with Ultra. Parakeet pipeline via the Pipecat-based Voice Agent framework.
Decision point: if week 4 closes on time, start the LoRA fine-tune. If not, drop it without
regret.
Week 5 (16–22 Oct) — routing, polish, deploy
Routing UI and cost meter. Public deployment. Full run-through in demo mode on a clean
machine.
Feature freeze 22 Oct.
Week 6 (23–28 Oct) — ship
README, demo script, video shoot and edit, feedback write-up, the what-changed
disclosure. Submit 28 Oct, two days early.
Nothing new goes in after 26 Oct. Hackathon projects die at the submission step far
more often than at the build step.
Video and submission
Beat sheet (3:00 hard cap)
Time Beat
0:00–0:15 The problem: an always-on agent running your life,
unobserved
0:15–0:45 Voice command to LifeOS, Parakeet transcript
appearing live
0:45–1:25 Timeline: agents acting, Nano narrating each step
LifeOS on Nemotron — Hackathon Build Spec
Page 11 of 29
=============== PAGE 12 ===============
Say "Nebius Token Factory" and "NVIDIA Nemotron" out loud in the audio. The rules
require it and judges skim. Shoot in demo mode only.
Checklist
Write the feedback section as you go, from notes taken during the build. Written on the
last day it reads generic; written from a running log it is specific and useful, and specificity
is visible.
Prior work disclosure (draft)
The rules require a written explanation of what was significantly updated during the
Submission Period when a project existed beforehand. Adapt this to what is actually true
on submission day.
Time Beat
1:25–2:00 Agent reaches an unapproved domain, you deny it
from your phone, timeline logs the block
2:00–2:30 Memory view: edit a fact, show its source
2:30–2:50 Flip Super → Ultra mid-task, cost meter moves
2:50–3:00 One line on Nemotron and Token Factory
Working project on Nebius using at least one NVIDIA open model
Track selected: Personal AI
Project description — what, why, how
Working demo URL, reachable in demo mode without your credentials
Public YouTube video, 3:00 or under, with audio
Public repo with OSS licence visible at the top of the page
README: setup, how to run, where Nemotron is used, where Token Factory
accelerated the work, other Nebius services used
Feedback on Token Factory, AI Cloud and the NVIDIA tooling
What-changed disclosure for the pre-existing work
City selection if you attended a Builders & Brews event
LifeOS on Nemotron — Hackathon Build Spec
Page 12 of 29
=============== PAGE 13 ===============
Prior work. LifeOS began as a personal project before the Submission Period. What
existed beforehand: an architecture and build guide for a seven-agent personal
assistant, a React dashboard, and a master system prompt. Its agents ran on closed
models through the Claude Agent SDK, on a single unisolated VPS, with no runtime
visibility.
Built during the Submission Period. Every NVIDIA and Nebius component in this
submission is new work:
Ported the Calendar, Email and Research agents off the Claude Agent SDK onto
NVIDIA Nemotron 3 via Nebius Token Factory, including a new tool-calling adapter
and per-agent prompt rework
Moved every agent into an OpenShell sandbox under NemoClaw, with explicit
network egress policy per agent
Built Glass Box, the control plane: live timeline, mobile approval flow, memory diff
view, model routing with cost telemetry, and session replay — entirely new,
roughly N thousand lines
Replaced the memory embedding model with NVIDIA's Nemotron embedding
model and re-indexed the vector store
Added a voice interface built on NVIDIA Parakeet
Moved nightly memory synthesis onto Nebius Serverless Jobs using Nemotron 3
Ultra
Built a synthetic demo mode so the system is publicly runnable without personal
data
The four remaining agents are carried over largely unchanged and are marked as
such in the repository.
Mark carried-over files in the repo itself — a header comment or a LEGACY.md  listing pre-
existing modules. It costs nothing and it reads as confidence rather than concealment.
Execution runbook
Day 1–3: zero to a Nemotron call inside a sandbox
One caveat that shapes this whole section: NemoClaw is alpha, so the exact flags and
subcommands come from nemoclaw --help  and the current docs, not from memory.
What follows is the sequence and the verification checkpoint at each step — treat the
checkpoints as the contract and read the CLI for the exact syntax.
LifeOS on Nemotron — Hackathon Build Spec
Page 13 of 29
=============== PAGE 14 ===============
Step 0 — repo, before anything else
gh repo create lifeos --public --license mit
cd lifeos
printf 'node_modules/\n.env\n.env.*\n!.env.example\n__pycache__/\n.venv/\n' > 
.gitignore
git add -A && git commit -m "init" && git push
Licence first. It is the cheapest requirement to satisfy and the most embarrassing to
forget.
Step 1 — Token Factory, before any infrastructure
Prove inference works before you build anything around it. On your laptop:
curl https://api.studio.nebius.com/v1/chat/completions \
  -H "Authorization: Bearer $NEBIUS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"<nemotron-3-super-id>","messages":
[{"role":"user","content":"reply with OK"}]}'
Get the exact base URL and model ids from the Token Factory console — do not guess
them. Checkpoint: a 200 with content. While you are in the console, note which models
are actually served: specifically whether any NVIDIA embedding or speech model is
there, since that decides whether you self-host them later.
Then the same call with a tool definition attached, and confirm the response shape for
tool calls. That shape drives the entire adapter.
Step 2 — the VM
Provision an Ubuntu GPU instance on Nebius AI Cloud. Install Docker, NVIDIA drivers, the
container toolkit. Verify with nvidia-smi  inside a container before going further — GPU
passthrough failing silently is a classic half-day loss.
Step 3 — NemoClaw
curl -fsSL https://www.nvidia.com/nemoclaw.sh | bash
nemoclaw --version   # write this down; pin it; never upgrade
nemoclaw --help
Run the onboard wizard. Point the inference profile at Token Factory. Checkpoint: a
sandboxed agent answering a prompt using Nemotron.
LifeOS on Nemotron — Hackathon Build Spec
Page 14 of 29
=============== PAGE 15 ===============
Also install NemoClaw's packaged agent skills into Cursor or Claude Code now. They are
written to walk a coding assistant through inference config, policy, monitoring and
troubleshooting, which is exactly the documentation gap you are about to hit.
Step 4 — the three unknowns
Before writing a line of frontend, answer these by experiment:
nemoclaw --help                  # full surface area
# find: sandbox lifecycle, log access, policy commands, status/inspect
1. Trigger an egress request to a blocked domain. Watch what happens. Can it be
observed and answered without a human at a terminal?
2. Find the workspace directory. Make the agent remember something. Diff the files.
What lands there and how often?
3. Can logs be tailed as a stream, or only polled?
Write the answers into this doc. Everything downstream depends on them.
Repo layout and what runs where
lifeos/
├ ── LICENSE                 # MIT, day one
├ ── README.md               # written incrementally, not at the end
├ ── LEGACY.md               # pre-existing modules, marked honestly
├ ── apps/
│   ├ ── glassbox/           # Next.js — laptop in dev, Nebius in prod
│   └── host/               # agent host — VM only
│       ├ ── nemoclaw.py     # CLI wrapper: lifecycle, logs, policy
│       ├ ── events.py       # log lines → typed events
│       ├ ── watcher.py      # workspace file diffs
│       └── server.py       # FastAPI + WebSocket
├ ── packages/
│   ├ ── inference/          # Token Factory adapter — the critical piece
│   │   ├ ── client.py       # OpenAI-compatible wrapper
│   │   ├ ── tools.py        # tool-schema translation
│   │   └── routing.yaml    # Nano/Super/Ultra policy, hot-reloadable
│   ├ ── agents/
│   │   ├ ── calendar/
│   │   ├ ── email/
│   │   └── research/
│   └── memory/             # pgvector + NVIDIA embeddings
├ ── voice/                  # Parakeet + Pipecat pipeline — VM only
├ ── jobs/                   # Nebius Serverless Jobs
LifeOS on Nemotron — Hackathon Build Spec
Page 15 of 29
=============== PAGE 16 ===============
│   └── nightly_synthesis/
├ ── fixtures/               # demo mode data — built week one
└── infra/
    ├ ── policies/           # OpenShell egress allowlists per agent
    └── compose.yml
Process map
One rule worth holding: the agent host is the only thing that touches the nemoclaw  CLI.
If Glass Box ever shells out directly, you have lost the ability to deploy the frontend
separately, and the demo URL requirement gets much harder.
The inference adapter
This is where the port lives or dies. Everything else is plumbing around it.
Client
Token Factory is OpenAI-compatible, so use the OpenAI SDK rather than writing HTTP by
hand:
# packages/inference/client.py
from openai import AsyncOpenAI
import yaml, time
client = AsyncOpenAI(
    base_url=os.environ["NEBIUS_BASE_URL"],   # from the console
    api_key=os.environ["NEBIUS_API_KEY"],
)
ROUTING = yaml.safe_load(open("routing.yaml"))
Process Where Started by
Glass Box Laptop (dev) / Nebius (prod) pnpm dev
Agent host VM systemd or tmux
Sandboxes VM nemoclaw  via the host
Voice service VM systemd
Nightly synthesis Serverless Jobs cron trigger
Postgres + pgvector Supabase managed
LifeOS on Nemotron — Hackathon Build Spec
Page 16 of 29
=============== PAGE 17 ===============
async def complete(task: str, messages, tools=None, model_override=None):
    model = model_override or ROUTING[task]      # "plan" | "execute" | 
"summarize"
    t0 = time.monotonic()
    resp = await client.chat.completions.create(
        model=model, messages=messages, tools=tools,
    )
    emit_event({                                  # Glass Box telemetry
        "kind": "inference",
        "task": task, "model": model,
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "prompt_tokens": resp.usage.prompt_tokens,
        "completion_tokens": resp.usage.completion_tokens,
    })
    return resp
Every call emits an event. That is what makes the routing screen and the cost meter
possible, and it costs nothing to add now versus retrofitting in week five.
Tool translation
The real work. Claude Agent SDK tool definitions and OpenAI-style function definitions
differ in schema and in how results are returned. Write one translation module and route
all three agents through it:
# packages/inference/tools.py
def to_openai_tool(anthropic_tool: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": anthropic_tool["name"],
            "description": anthropic_tool["description"],
            "parameters": anthropic_tool["input_schema"],
        },
    }
def from_openai_call(tool_call) -> dict:
    return {
        "id": tool_call.id,
        "name": tool_call.function.name,
        "input": json.loads(tool_call.function.arguments),
    }
Two things reliably bite here. Nemotron may emit arguments that are almost-valid JSON
— wrap the parse in a retry that feeds the error back to the model. And tool-result
messages use a different role and shape than the Agent SDK's content blocks, so the
LifeOS on Nemotron — Hackathon Build Spec
Page 17 of 29
=============== PAGE 18 ===============
message-history builder needs rewriting, not patching.
Write tests against recorded fixtures. Ten saved tool-calling exchanges you can replay
offline will save you hours of burning credits on debug loops.
Routing config
# routing.yaml — hot-reloaded; Glass Box writes to it
plan:      nvidia/nemotron-3-ultra
execute:   nvidia/nemotron-3-super
summarize: nvidia/nemotron-3-nano
Agent host: run loop and event stream
One event type for everything
Every observable thing becomes the same shape. Glass Box renders one stream; adding a
new event kind never means touching the transport.
@dataclass
class Event:
    ts: float
    kind: str        # action | inference | egress_request | egress_decision
                     # | memory_write | error | voice
    agent: str       # calendar | email | research | system
    summary: str     # one line, written by Nano
    detail: dict     # the raw payload
    session: str
The host keeps a ring buffer of the last few thousand events and appends everything to
JSONL on disk. The buffer serves the live view; the file serves replay. Both are trivial and
you want both.
The loop
async def run():
    await asyncio.gather(
        tail_sandbox_logs(),     # or poll, depending on week-one findings
        watch_workspace(),       # file diffs → memory_write events
        poll_egress_requests(),  # → egress_request events
        serve_api(),             # FastAPI + WebSocket
    )
LifeOS on Nemotron — Hackathon Build Spec
Page 18 of 29
=============== PAGE 19 ===============
Summarization, done carefully
Raw log lines are unreadable on camera. Nano rewrites them into one clean line each —
but batch them. One inference call per log line will be slow and expensive:
async def summarize_batch(events: list[Event]):
    # collect over a 2s window, summarize up to 20 at once
    resp = await complete("summarize", [...])
    ...
Emit the event immediately with the raw text, then patch in the summary when it arrives.
The timeline stays live and fills in a beat later, which looks deliberate rather than laggy.
Approvals
GET  /api/events?since=<ts>     backfill on page load
WS   /api/stream                live events
GET  /api/approvals             pending egress requests
POST /api/approvals/<id>        {"decision": "allow"|"deny", "scope": 
"once"|"always"}
GET  /api/memory/diff
POST /api/routing               rewrite routing.yaml
If week one showed that approvals cannot be answered programmatically, this endpoint
writes a policy file and restarts the sandbox instead. Slower, still demoable, and the API
surface stays identical — which is why you define the API before you know the answer.
The daily dev loop
On an 8 GB machine this matters more than anything else in the runbook. The goal is that
your laptop only ever runs Next.js and a browser.
Setup, once
Tailscale on both machines. The VM gets a stable name; no public ports, and your phone
joins the same network — which is how the mobile approval demo works without
deploying anything.
# .env.local on the laptop
NEXT_PUBLIC_HOST_URL=http://lifeos-vm:8000
NEXT_PUBLIC_WS_URL=ws://lifeos-vm:8000/api/stream
LifeOS on Nemotron — Hackathon Build Spec
Page 19 of 29
=============== PAGE 20 ===============
Every session
# laptop, terminal 1
pnpm --filter glassbox dev        # ~600 MB, the only heavy local process
# laptop, terminal 2
ssh lifeos-vm
tmux attach -t host               # agent host logs, live
Edit the frontend locally with hot reload against real events from the VM. Edit host or
agent code, then:
# from the laptop
rsync -av --exclude node_modules apps/host packages/ lifeos-vm:~/lifeos/
ssh lifeos-vm 'systemctl --user restart lifeos-host'
A two-line make sync  wrapper pays for itself by day three.
Memory discipline on 8 GB
One browser profile for development, another for everything else — and keep the
second closed
Never run Docker on the laptop; that is what the VM is for
NODE_OPTIONS=--max-old-space-size=2048  if Next.js starts thrashing
Watch out for Next.js dev-server memory growth over long sessions; restart it every
few hours rather than debugging a phantom slowdown
Credits
Develop against Nano. Switch to Super and Ultra only when testing the real routing path,
and record fixtures so repeat debugging runs offline. Burning your Token Factory credits
on week-two debug loops is a real and avoidable way to lose week five.
Failure modes and fallbacks
Decide these now, while it costs nothing. Mid-build, under time pressure, you will make
worse calls.
LifeOS on Nemotron — Hackathon Build Spec
Page 20 of 29
=============== PAGE 21 ===============
The two things that are never negotiable
The repo and licence exist from day one. A brilliant project with no licence file is
disqualified on a technicality.
The video gets shot by 26 October. Every hackathon post-mortem says the same thing:
the build was fine, the submission was rushed. Two days of slack is the difference
between a project and a submission.
Keep a build log
One markdown file, a few lines a day: what broke, what the workaround was, what
surprised you. It writes your feedback section for free, and feedback written from a
running log reads specific rather than generic — which is visible to anyone reading it.
If this fails Fallback Decide
by
NemoClaw won't install or run on
your setup
Different VM image, or run OpenShell
directly without the NemoClaw
wrapper
24 Sep
Approvals are interactive-only Policy-file writes plus sandbox restart;
same API, slower demo
24 Sep
Logs can't be streamed Poll every 500 ms; visually identical on
camera
24 Sep
Tool calling is unreliable on Nemotron Constrain to fewer, simpler tools and
add a JSON-repair retry loop
1 Oct
Agent port is taking too long Ship two agents instead of three 8 Oct
No NVIDIA embedding model on
Token Factory
Self-host on the VM, or run it as a
Serverless Job over a batch
15 Oct
Voice pipeline won't come together Cut it; Glass Box is the core and stands
alone
15 Oct
LoRA fine-tune stalls Drop it without regret; it was always
conditional
22 Oct
Public deployment is fighting you Record the video locally; the demo URL
can point at a Tailscale-fronted instance
or a read-only replay build
26 Oct
LifeOS on Nemotron — Hackathon Build Spec
Page 21 of 29
=============== PAGE 22 ===============
Tavily — the $3,000 addition
The bonus requires a functional runtime call to the Tavily API as part of the solution. Not a
demo endpoint, not a stub — something the product actually depends on.
Where it goes
The Research agent. It needs live web search; Tavily is a search API built for agents. This is
the natural fit rather than a bolt-on, which matters because judges can tell the difference.
A second, stronger placement: grounding in the memory layer. When LifeOS stores a
fact with an external claim in it, the nightly synthesis job can verify it against a Tavily
search and mark it as confirmed, stale or contradicted. Glass Box then shows memory
entries with a provenance badge. That is a non-obvious use, it strengthens the
governance story, and it makes the Tavily call load-bearing rather than incidental.
Shape
# packages/agents/research/search.py
import httpx, os
async def search(query: str, depth: str = "basic") -> list[dict]:
    async with httpx.AsyncClient() as c:
        r = await c.post(
            "https://api.tavily.com/search",
            json={
                "api_key": os.environ["TAVILY_API_KEY"],
                "query": query,
                "search_depth": depth,
                "max_results": 5,
            },
        )
    emit_event({"kind": "search", "agent": "research",
                "summary": f"Searched: {query}", "detail": {"query": query}})
    return r.json()["results"]
Check the current request shape against Tavily's docs — the auth header convention in
particular has changed across versions. Emit an event for every call, so searches appear in
the Glass Box timeline alongside everything else. That is also your evidence of a runtime
call.
LifeOS on Nemotron — Hackathon Build Spec
Page 22 of 29
=============== PAGE 23 ===============
Budget and credits
Tavily credits come with the Nebius Builder Program, which is another reason to join it.
Add TAVILY_API_KEY  to .env.example  and the OpenShell egress allowlist for the
Research agent — api.tavily.com  — or the sandbox will block it, which is a confusing
thirty minutes if you forget.
Schedule
Week 3, alongside the Research agent port. Roughly a day including the provenance
badge in the memory view. Do not leave it to week five — an obvious last-minute bolt-on
reads as exactly that.
Connecting to the LifeOS ecosystem
What already exists, and what attaches where
LifeOS today is roughly four things: a master system prompt defining the assistant's
behaviour, a dashboard interface, a Supabase database with pgvector for memory, and a
set of agent designs — seven of them — plus n8n workflows for scheduled automation.
The new layer does not replace any of that. It slides underneath.
LifeOS piece What happens to it
Master system prompt Adapted per agent for Nemotron; kept as the
source of behaviour
Dashboard Stays; Glass Box becomes a new surface
beside it, sharing the design language
Supabase + pgvector Stays; embedding column swapped to the
NVIDIA model
Calendar / Email / Research agents Ported to Nemotron, moved inside sandboxes
CRM / Networking / Internship / Content
agents
Untouched, disclosed as pre-existing
n8n workflows Scheduled work migrates to Nebius
Serverless Jobs where it touches the ported
agents
LifeOS on Nemotron — Hackathon Build Spec
Page 23 of 29
=============== PAGE 24 ===============
Three integration points
1. Memory is the shared spine. Both the old agents and the new sandboxed ones read
and write the same Supabase tables. This is what makes it one system rather than two.
The sandboxed agents reach Supabase through the egress allowlist; nothing else changes.
2. The master prompt stays the source of truth. Keep it as one file, with per-agent
adaptations layered on top rather than forked copies. When you rework prompts for
Nemotron, you are editing adaptations, not rewriting LifeOS's identity. The September
specification pass already did the hard thinking here — build on it rather than starting
over.
3. Glass Box observes, it does not own. It reads events from the agent host and writes
only two things: approval decisions and routing.yaml . Everything else it renders is
someone else's state. Keeping it read-mostly is what lets you deploy it separately and
hand judges a URL.
What deliberately stays out of scope
The four unported agents keep running however they run today. Do not migrate them, do
not refactor them, do not tidy them. They exist in the repo, they are marked as pre-
existing in LEGACY.md , and they are not part of the six-week build. Every hour spent there
is an hour not spent on the submission.
Data flow
  voice ──► Parakeet ──► intent ──┐
                                  ▼
  Glass Box ◄── WS events ── agent host ──► nemoclaw ──► sandbox
      │                           ▲                        │
      │ approvals,                │ events                 │ tool calls
      │ routing.yaml              │                         ▼
      ▼                           │              ┌──────────────────┐
  infra/policies/ ────────────────┘              │ Token Factory    │
                                                 │ Nemotron N/S/U   │
  Supabase ◄── read/write ── agents ───────────── ┤  Tavily           │
  (pgvector, NVIDIA embeddings)                  │ Google APIs      │
      ▲                                          └──────────────────┘
      │
  Serverless Job (nightly: Ultra synthesis + Tavily grounding)
Contracts to fix early
These are the seams. Settle each one in week one and the rest of the build stops rippling.
LifeOS on Nemotron — Hackathon Build Spec
Page 24 of 29
=============== PAGE 25 ===============
That fifth row is the demo. Each agent's allowlist should be genuinely minimal — the
Calendar agent has no business reaching api.tavily.com , and the fact that it can't is the
point you are making on camera.
Environment
NEBIUS_API_KEY=          # Token Factory
NEBIUS_BASE_URL=         # from the console, do not guess
TAVILY_API_KEY=          # Builder Program credits
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
HOST_URL=http://lifeos-vm:8000
DEMO=false               # true swaps every data source for fixtures
DEMO=true  must produce a fully working system with zero real credentials. Test that on a
clean machine in week five, not on submission day.
Working with Claude Code
CLAUDE.md — drop this in the repo root
Claude Code reads this file automatically at the start of every session. It is the single
highest-leverage token saving available: without it, you re-explain the project in every
session, for six weeks.
Seam Contract
Host → Glass Box The Event  dataclass. One shape, additive changes
only
Glass Box → host The six REST endpoints. Stable even if the
implementation behind approvals changes
Agents → memory Existing Supabase schema, plus one new
embedding column
Agents → models The complete()  function. No agent calls an
inference API directly
Agents → outside world The egress allowlist per agent, in
infra/policies/
LifeOS on Nemotron — Hackathon Build Spec
Page 25 of 29
=============== PAGE 26 ===============
# LifeOS — Nebius x NVIDIA Hackathon
## What this is
An always-on personal assistant (LifeOS) running NVIDIA Nemotron models on
Nebius Token Factory, with agents sandboxed under NemoClaw/OpenShell, and a
web control plane (Glass Box) making agent activity visible and stoppable.
Deadline: 30 Oct 2026, 10:00 PT. Personal AI track.
## Non-negotiables
- All LLM inference goes through Token Factory. Never add another provider.
- Agents never call an inference API directly. Always use complete() from
  packages/inference/client.py.
- Every agent action emits an Event. No silent work.
- DEMO=true must run the whole system with zero real credentials.
- No real personal data in fixtures, commits or screenshots. Ever.
- The agent host is the only thing that shells out to the nemoclaw CLI.
## Layout
- apps/glassbox        Next.js control plane (laptop in dev, Nebius in prod)
- apps/host            agent host: nemoclaw wrapper, events, API (VM only)
- packages/inference   Token Factory client, tool translation, routing.yaml
- packages/agents      calendar, email, research (ported); others are legacy
- packages/memory      Supabase + pgvector + NVIDIA embeddings
- voice/               Parakeet + Pipecat (VM only)
- fixtures/            demo-mode data
- infra/policies/      OpenShell egress allowlists, one per agent
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
LifeOS on Nemotron — Hackathon Build Spec
Page 26 of 29
=============== PAGE 27 ===============
- Read only the files needed for the task. Do not survey the repo.
- Ask before adding a dependency.
- Prefer editing existing files over creating new ones.
- Keep responses short. Do not re-explain code you just wrote.
Update it whenever a decision gets made. Every ten minutes spent keeping it current
buys back hours of re-explaining.
Token discipline on a Pro plan
You are on Pro, not Max. Six weeks of daily building will hit limits unless you are deliberate.
The good news is that almost all waste comes from a handful of habits.
Where tokens actually go
Not on generating code — on reading. A session that surveys the repo, re-reads files, and
swallows long logs burns context before any work starts. Every one of the rules below is
about reading less.
The rules
Point at files. Never say "look at the codebase." Instead of "figure out how the inference
client works and add retry logic", say "in packages/inference/client.py, add a retry with
exponential backoff around the create() call." The first burns thousands of tokens on
exploration; the second starts working immediately.
Use /clear  between unrelated tasks. Context carries forward until you clear it.
Finishing the memory diff view and moving to the voice pipeline with the same context
means every voice message carries the memory conversation along with it. Clear first.
Never paste raw logs. Grep, then paste the five relevant lines. A thousand-line stack
trace costs more than the fix.
One task per session. Long sessions accumulate context that every later message pays
for. Short focused sessions are cheaper and produce better code.
Don't ask it to verify its own edits. If an edit succeeded, it succeeded. Asking it to re-
read the file to confirm doubles the cost of every change.
Batch related edits into one request. Five small requests about the same file each reload
that file. One request describing all five changes loads it once.
Turn off MCP servers you are not using. Every connected server's tool definitions sit in
context for the whole session, whether or not you use them.
LifeOS on Nemotron — Hackathon Build Spec
Page 27 of 29
=============== PAGE 28 ===============
Avoid subagents unless you need them. Each one starts cold and re-derives context you
already have. They are the expensive path. Useful for a genuinely broad search; wasteful
for anything you could point at directly.
Commit often. With a clean history it can read a diff instead of a file.
Plan in chat, build in Claude Code. Architecture conversations, trade-off discussions and
"what should I do here" belong in a normal Claude chat with this document. Claude Code
is for making changes to files. Mixing the two is the most common way people burn a Pro
plan.
One line to add to prompts when it matters
Read only what you need for this change. Don't survey the repo. Keep your response
short — no summary of what you did unless I ask.
When you do hit a limit
Don't sit and wait. Switch to the work that needs no model: shoot video footage, write the
README, build fixtures by hand, test demo mode, draft the feedback section. Week six
work done in week three is week six bought back.
Session sequence
One session per row. Clear context between them. Each has a checkpoint — if it isn't met,
fix it before moving on rather than stacking a second problem on the first.
# Ask for Checkpoint
1 Scaffold the repo layout, CLAUDE.md,
LICENSE, .env.example, .gitignore
tree  matches the layout
2 Token Factory client with usage logging,
from the verified base URL and model ids
A real call returns, and logs tokens
3 Tool-schema translation with fixture tests Tests pass offline
4 nemoclaw CLI wrapper: sandbox lifecycle,
log tail
A sandbox starts and stops from
Python
5 Event model, ring buffer, JSONL append Events land on disk
6 FastAPI + WebSocket server, all six
endpoints
curl  and a WS client both work
LifeOS on Nemotron — Hackathon Build Spec
Page 28 of 29
=============== PAGE 29 ===============
How to open a session
Give it the task, the files, and the constraint. Nothing else — CLAUDE.md carries the rest.
Session 5. Build the event model and ring buffer in apps/host/events.py per the spec:
an Event dataclass with ts, kind, agent, summary, detail, session; a 5000-entry ring
buffer; append every event to JSONL under data/sessions/. No API layer yet — that's
next session. Don't read outside apps/host.
That last clause is worth including every time.
What not to hand to Claude Code
Architecture decisions, scope cuts, "should I do X or Y", debugging a conceptual problem,
anything in this document. Those belong in a normal chat, where the reasoning is cheap
and you keep the context yourself. Claude Code is for writing and changing files — give it
decisions already made.
# Ask for Checkpoint
7 Glass Box scaffold + Timeline screen Live events render in the browser
8 Approvals: endpoints, then the mobile UI Deny works end to end from a phone
9 Port the Calendar agent It completes a real task in a sandbox
10 Port Research + Tavily + event emission Searches appear in the timeline
11 Port the Email agent Same
12 Embedding swap + re-index script Retrieval quality holds up
13 Memory diff view Edits persist, sources show
14 Nightly synthesis as a Serverless Job It runs on schedule
15 Parakeet + Pipecat voice pipeline Speech in, action out
16 Routing UI + cost meter Switching tiers changes behaviour live
17 Demo-mode audit across every surface Clean machine, no credentials,
everything works
18 Deploy Judges' URL loads
LifeOS on Nemotron — Hackathon Build Spec
Page 29 of 29