# Week-1 unknowns — answer by experiment, by 24 Sep

Everything downstream depends on these. Write the answers in here. The
fallbacks are already decided so that a bad answer costs no design time.

## 1. Can an egress approval request be observed and answered programmatically?

Experiment: start a sandbox, have the agent reach a domain not on its
allowlist, watch what NemoClaw does.

- [ ] Answered
- **Finding:**
- **Fallback if interactive-only:** `POST /api/approvals/<id>` writes a policy
  file and restarts the sandbox. Same API surface, slower demo. Decide 24 Sep.

## 2. What lands in the workspace directory, and how often?

Experiment: find the workspace dir, make the agent remember something, diff
the files before and after.

- [ ] Answered
- **Workspace path:**
- **Files that change:**
- **Write frequency:**
- **Why it matters:** the Memory diff screen renders exactly this shape.

## 3. Can sandbox logs be tailed as a stream, or only polled?

- [ ] Answered
- **Finding:**
- **Fallback:** poll every 500 ms. Visually identical on camera. Decide 24 Sep.

## 4. (Console check) Which models does Token Factory actually serve?

**ANSWERED 1 Oct 2026**, read from tokenfactory.nebius.com -> Model endpoints.
25 public endpoints, 0 dedicated.

- [x] **Base URL: `https://api.tokenfactory.nebius.com/v1/`**
      Not `api.studio.nebius.com` as the build plan says — the product was
      renamed and that address is stale. studio.nebius.com redirects here.
- [x] Nano:  `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`  — $0.06 / $0.24 per Mtok, 60 tok/s
- [x] Super: `nvidia/nemotron-3-super-120b-a12b`      — $0.30 / $0.90 per Mtok, 127 tok/s
- [x] Ultra: `nvidia/Nemotron-3-Ultra-550b-a55b`      — $1.00 / $3.00 per Mtok, 523 tok/s

The console calls these **routing keys**. Four models from one vendor, four
naming conventions: a redundant `NVIDIA-` prefix on Nano, all-lowercase on
Super, mixed case on Ultra, and an underscore for the point-release on
Lightning. None of it is inferable from the display names.

- [x] **No NVIDIA embedding model is served.** The only embedding endpoint is
      `Qwen3-Embedding-8B` ($0.01/Mtok, 4096 dims). So `llama-nemotron-embed-1b-v2`
      means self-hosting on AI Cloud -> Serverless AI -> Endpoints, or
      switching to the Qwen model. **Open decision — see BUILD-LOG.**
- ~~Is any NVIDIA speech model (Parakeet / MagpieTTS) served?~~ — moot, voice
  cut 30 Sep. For the record: no speech models of any kind are served.

### Also worth knowing

- **`nvidia/Nemotron-3_5-Lightning`** exists and is not in the build plan.
  Same price as Nano ($0.06/$0.24), ~5x the throughput (314 vs 60 tok/s), 30B
  MoE with 3B active, described as built for agentic reasoning and tool use.
  A candidate for `summarize`, possibly for `execute`.
- **`NousResearch/Hermes-4-405B`** is served. The build plan flags Hermes as
  cheap surface area because NemoClaw supports it via `NEMOCLAW_AGENT=hermes`
  and it appears by name in the track brief.
- Public endpoints carry a warning: *"Availability and processing region may
  change without notice and break the current base_url."* For a demo URL that
  must work for judges in December, that is a real risk. Dedicated endpoints
  are the production path and need a login to create.

## 5. Tool-calling response shape

Make one Token Factory call with a tool definition attached and record the
exact response shape. Save it to `tests/fixtures/` — that recording drives the
entire adapter and lets the adapter tests run offline.

- [ ] Recorded to tests/fixtures/
