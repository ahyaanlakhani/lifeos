"use client";

/** Routing.
 *
 *  The three Nemotron tiers, what each is doing, and what it costs. Switching
 *  a task to a different tier rewrites routing.yaml on the host, which is
 *  hot-reloaded — so the change takes effect on the next call with nothing
 *  restarted. That is the 2:30 beat of the demo, and it is a real feature
 *  rather than a screen built for the camera.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Conn } from "../../components/Conn";
import { api } from "../../lib/api";
import { isPlaceholder, type LifeEvent, type Task } from "../../lib/types";
import { useStream } from "../../lib/useStream";

const PURPOSE: Record<Task, string> = {
  plan: "Daily planning pass and nightly memory synthesis. Long horizon, multi-step.",
  execute: "Agent work. The default working tier.",
  summarize: "Activity feed and classification. Cheap, constant.",
};

interface Stats {
  calls: number;
  medianLatency: number | null;
  spend: number | null;
  tokens: number;
}

function statsFor(events: LifeEvent[], task: Task): Stats {
  const rows = events.filter((e) => e.kind === "inference" && e.detail?.task === task);
  const latencies = rows
    .map((e) => e.detail?.latency_ms)
    .filter((v): v is number => typeof v === "number")
    .sort((a, b) => a - b);

  const costs = rows.map((e) => e.detail?.cost_usd).filter((v): v is number => typeof v === "number");
  const tokens = rows.reduce((total, e) => {
    const p = typeof e.detail?.prompt_tokens === "number" ? e.detail.prompt_tokens : 0;
    const c = typeof e.detail?.completion_tokens === "number" ? e.detail.completion_tokens : 0;
    return total + p + c;
  }, 0);

  return {
    calls: rows.length,
    medianLatency: latencies.length ? latencies[Math.floor(latencies.length / 2)] : null,
    // null, not 0 — a meter reading zero looks like a working meter reporting
    // a free call. Pricing is filled in from the Token Factory console.
    spend: costs.length ? costs.reduce((a, b) => a + b, 0) : null,
    tokens,
  };
}

export default function Routing() {
  const { events, state } = useStream();
  const [routing, setRouting] = useState<Record<string, string>>({});
  const [tasks, setTasks] = useState<Task[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const body = await api.routing();
      setRouting(body.routing);
      setTasks(body.tasks);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Every model id the host has ever mentioned, so a tier can be switched to
  // one that is actually configured rather than typed from memory.
  const models = useMemo(() => {
    const known = new Set(Object.values(routing));
    for (const event of events) {
      if (typeof event.detail?.model === "string") known.add(event.detail.model);
    }
    return [...known].filter(Boolean).sort();
  }, [routing, events]);

  async function change(task: Task, model: string) {
    if (!model || model === routing[task]) return;
    setSaving(task);
    try {
      const body = await api.setRouting({ [task]: model });
      setRouting(body.routing);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(null);
    }
  }

  const anyPlaceholder = Object.values(routing).some(isPlaceholder);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Routing</h1>
          <p className="sub">
            Which Nemotron tier serves which job. Changes rewrite routing.yaml on
            the host and take effect on the next call — nothing restarts.
          </p>
        </div>
        <Conn state={state} />
      </div>

      {error && <div className="banner">{error}</div>}

      {anyPlaceholder && (
        <div className="banner" style={{ borderColor: "var(--warn)" }}>
          Model ids are still scaffold placeholders. Replace them with the exact
          ids from the Token Factory console — the client refuses to call out
          until you do, which is deliberate.
        </div>
      )}

      <div className="tiers">
        {tasks.map((task) => {
          const model = routing[task] ?? "";
          const stats = statsFor(events, task);
          return (
            <div className="tier" key={task}>
              <div className="task">{task}</div>
              <div className={`model${isPlaceholder(model) ? " placeholder" : ""}`}>
                {model || "unset"}
              </div>
              <p className="sub" style={{ fontSize: 12, marginBottom: 10 }}>
                {PURPOSE[task]}
              </p>

              <label>
                <span className="task">switch to</span>
                <select
                  value={model}
                  disabled={saving === task || models.length === 0}
                  onChange={(e) => change(task, e.target.value)}
                >
                  {models.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>

              <div className="stat-row">
                <div className="stat">
                  <div className="label">calls</div>
                  <div className="value">{stats.calls}</div>
                </div>
                <div className="stat">
                  <div className="label">median</div>
                  <div className={`value${stats.medianLatency === null ? " unknown" : ""}`}>
                    {stats.medianLatency === null ? "—" : `${stats.medianLatency}ms`}
                  </div>
                </div>
                <div className="stat">
                  <div className="label">tokens</div>
                  <div className="value">{stats.tokens.toLocaleString()}</div>
                </div>
                <div className="stat">
                  <div className="label">spend</div>
                  <div className={`value${stats.spend === null ? " unknown" : ""}`}>
                    {stats.spend === null ? "no rate" : `$${stats.spend.toFixed(4)}`}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
