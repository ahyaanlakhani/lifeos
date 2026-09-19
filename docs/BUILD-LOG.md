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
