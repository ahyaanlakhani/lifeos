"use client";

/** Replay.
 *
 *  Scrub back through a past session. The host writes every event to JSONL as
 *  it happens, so this reads off disk rather than out of memory — a session
 *  recorded before the host restarted is still replayable, which is the point
 *  of writing the file at all.
 *
 *  The scrubber is positional rather than wall-clock: agents are bursty, and a
 *  time-proportional slider spends most of its travel on the gaps between
 *  bursts. Stepping event by event is what someone auditing a run actually
 *  wants.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { EventRow } from "../../components/EventRow";
import { api } from "../../lib/api";
import type { LifeEvent } from "../../lib/types";

interface SessionRow {
  session: string;
  bytes: number;
  modified: number;
  live: boolean;
}

const SPEEDS = [1, 2, 4, 16] as const;

function when(ts: number): string {
  return new Date(ts * 1000).toLocaleString([], {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export default function Replay() {
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [events, setEvents] = useState<LifeEvent[]>([]);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<number>(4);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    api
      .sessions()
      .then((body) => {
        setSessions(body.sessions);
        if (body.sessions.length > 0) setSelected(body.sessions[0].session);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  const load = useCallback(async (id: string) => {
    if (!id) return;
    setLoading(true);
    setPlaying(false);
    try {
      const body = await api.replay(id);
      setEvents(body.events);
      setCursor(body.events.length);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setEvents([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(selected);
  }, [selected, load]);

  // Play steps through events, pausing by the real gap between them, clamped
  // so a five-minute idle stretch does not stall the playback.
  useEffect(() => {
    if (!playing || cursor >= events.length) {
      if (cursor >= events.length) setPlaying(false);
      return;
    }
    const current = events[cursor];
    const next = events[cursor + 1];
    const gapMs = next ? Math.min((next.ts - current.ts) * 1000, 3000) : 400;
    timer.current = setTimeout(() => setCursor((c) => c + 1), Math.max(gapMs / speed, 40));
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [playing, cursor, events, speed]);

  const shown = useMemo(() => events.slice(0, cursor).reverse(), [events, cursor]);
  const at = cursor > 0 ? events[cursor - 1] : null;
  const elapsed =
    at && events.length > 0 ? Math.round(at.ts - events[0].ts) : 0;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Replay</h1>
          <p className="sub">
            Step back through a past session. Every event was written to disk as
            it happened, so this survives a restart of the host.
          </p>
        </div>
      </div>

      {error && <div className="banner">{error}</div>}

      <div className="card">
        <label>
          <span className="task">session</span>
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            disabled={sessions.length === 0}
          >
            {sessions.map((s) => (
              <option key={s.session} value={s.session}>
                {s.session}
                {s.live ? " · live" : ""} · {Math.max(1, Math.round(s.bytes / 1024))} KB ·{" "}
                {when(s.modified)}
              </option>
            ))}
          </select>
        </label>

        <div className="stat-row">
          <div className="stat">
            <div className="label">position</div>
            <div className="value">
              {cursor}
              <span style={{ color: "var(--text-faint)" }}> / {events.length}</span>
            </div>
          </div>
          <div className="stat">
            <div className="label">elapsed</div>
            <div className="value">{elapsed}s</div>
          </div>
          <div className="stat">
            <div className="label">at</div>
            <div className={`value${at ? "" : " unknown"}`} style={{ fontSize: 14 }}>
              {at ? new Date(at.ts * 1000).toLocaleTimeString([], { hour12: false }) : "—"}
            </div>
          </div>
        </div>

        <input
          type="range"
          min={0}
          max={events.length}
          value={cursor}
          disabled={events.length === 0}
          onChange={(e) => {
            setPlaying(false);
            setCursor(Number(e.target.value));
          }}
          aria-label="Scrub through the session"
          style={{ width: "100%", marginTop: 12 }}
        />

        <div className="toolbar">
          <button onClick={() => setCursor(0)} disabled={cursor === 0}>
            ⏮ Start
          </button>
          <button
            onClick={() => {
              setPlaying(false);
              setCursor((c) => Math.max(0, c - 1));
            }}
            disabled={cursor === 0}
          >
            ◀ Step
          </button>
          <button
            onClick={() => {
              if (cursor >= events.length) setCursor(0);
              setPlaying((p) => !p);
            }}
            disabled={events.length === 0}
          >
            {playing ? "❚❚ Pause" : "▶ Play"}
          </button>
          <button
            onClick={() => {
              setPlaying(false);
              setCursor((c) => Math.min(events.length, c + 1));
            }}
            disabled={cursor >= events.length}
          >
            Step ▶
          </button>
          <button onClick={() => setCursor(events.length)} disabled={cursor >= events.length}>
            End ⏭
          </button>
          {SPEEDS.map((s) => (
            <button key={s} onClick={() => setSpeed(s)} aria-pressed={speed === s}>
              {s}×
            </button>
          ))}
        </div>
      </div>

      <div className="timeline" style={{ marginTop: 12 }}>
        {loading ? (
          <div className="empty">Loading…</div>
        ) : shown.length === 0 ? (
          <div className="empty">
            <strong>{events.length === 0 ? "Nothing recorded" : "At the start"}</strong>
            {events.length === 0
              ? "Run the system and this fills up."
              : "Press play, or drag the scrubber."}
          </div>
        ) : (
          shown.map((event) => <EventRow key={event.id} event={event} />)
        )}
      </div>
    </>
  );
}
