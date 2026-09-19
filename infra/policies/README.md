# OpenShell egress allowlists

One file per agent. Each allowlist is deliberately minimal — the Calendar
agent has no business reaching `api.tavily.com`, and the fact that it cannot
is the point made on camera at 1:25 of the demo video.

The schema below is provisional. Reconcile it with `nemoclaw --help` and the
OpenShell policy docs in week one, then update all three files together.
