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

While in the console for Step 1, note:

- [ ] Exact base URL:
- [ ] Nemotron 3 Nano id:
- [ ] Nemotron 3 Super id:
- [ ] Nemotron 3 Ultra id:
- [ ] Is `llama-nemotron-embed-1b-v2` (or any NVIDIA embedding model) served?
- [ ] Is any NVIDIA speech model (Parakeet / MagpieTTS) served?

If embeddings or speech are not served, they get self-hosted on the AI Cloud
VM. That decision belongs in week one, not week four.

## 5. Tool-calling response shape

Make one Token Factory call with a tool definition attached and record the
exact response shape. Save it to `tests/fixtures/` — that recording drives the
entire adapter and lets the adapter tests run offline.

- [ ] Recorded to tests/fixtures/
