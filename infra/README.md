# Deploying to the Nebius VM

Two paths. Pick one; do not run both.

## systemd (simpler, and the one to start with)

One less layer between the agent host and the `nemoclaw` CLI it drives, which
matters while the CLI is still alpha and being worked out.

    cp infra/lifeos-host.service ~/.config/systemd/user/
    systemctl --user daemon-reload
    systemctl --user enable --now lifeos-host
    loginctl enable-linger $USER    # or an SSH drop kills it

Glass Box runs separately, either `npm run start` under its own unit or from
the compose file below.

## compose (for the public deployment in week 5)

    cp .env.example infra/.env     # fill it in
    docker compose -f infra/compose.yml up -d

The sandboxes are deliberately not in the compose file. The agent host creates
and destroys them through the `nemoclaw` CLI, and two owners of one lifecycle
is a bad trade.

## Before the judges' URL goes live

- [ ] Real hostname in `Caddyfile`, replacing `lifeos.example`
- [ ] `GLASSBOX_ORIGINS` narrowed from the dev default to that hostname
- [ ] `PUBLIC_HOST_URL` / `PUBLIC_WS_URL` set — Next inlines these at build
      time, so a rebuild is needed if they change
- [ ] `DEMO=true` on the public instance. The judges' URL must be reachable
      without your credentials, and your real inbox must not be behind it
- [ ] Verify `wss://` works through Caddy, not just `https://`. A silently
      broken WebSocket leaves the timeline looking empty rather than erroring
