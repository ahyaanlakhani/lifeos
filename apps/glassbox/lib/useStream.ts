"use client";

/** Live event stream with backfill and reconnection.
 *
 *  The host replays its recent ring buffer on connect, so a reconnect does not
 *  leave a hole in the timeline. Events are de-duplicated by id and summary
 *  patches replace the event in place — the host emits an event immediately
 *  with the raw log line and patches in Nano's one-liner a beat later.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { WS_URL, api } from "./api";
import type { LifeEvent } from "./types";

export type ConnectionState = "connecting" | "live" | "down";

const MAX_EVENTS = 2000;
const RETRY_BASE_MS = 500;
const RETRY_MAX_MS = 10_000;

export function useStream(): {
  events: LifeEvent[];
  state: ConnectionState;
  error: string | null;
} {
  const [events, setEvents] = useState<LifeEvent[]>([]);
  const [state, setState] = useState<ConnectionState>("connecting");
  const [error, setError] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = useRef(0);
  const closedRef = useRef(false);

  const absorb = useCallback((incoming: LifeEvent[]) => {
    if (incoming.length === 0) return;
    setEvents((current) => {
      const byId = new Map(current.map((e) => [e.id, e]));
      for (const event of incoming) byId.set(event.id, event);
      const merged = [...byId.values()].sort((a, b) => a.ts - b.ts || a.id.localeCompare(b.id));
      return merged.length > MAX_EVENTS ? merged.slice(-MAX_EVENTS) : merged;
    });
  }, []);

  const connect = useCallback(() => {
    if (closedRef.current) return;
    setState((s) => (s === "live" ? s : "connecting"));

    let socket: WebSocket;
    try {
      socket = new WebSocket(WS_URL);
    } catch {
      scheduleRetry();
      return;
    }
    socketRef.current = socket;

    socket.onopen = () => {
      attemptRef.current = 0;
      setState("live");
      setError(null);
    };

    socket.onmessage = (message) => {
      try {
        absorb([JSON.parse(message.data as string) as LifeEvent]);
      } catch {
        /* a malformed frame must not take down the timeline */
      }
    };

    socket.onerror = () => {
      setError(`Lost the event stream at ${WS_URL}`);
    };

    socket.onclose = () => {
      socketRef.current = null;
      if (closedRef.current) return;
      setState("down");
      scheduleRetry();
    };

    function scheduleRetry() {
      const attempt = attemptRef.current++;
      const delay = Math.min(RETRY_BASE_MS * 2 ** attempt, RETRY_MAX_MS);
      timerRef.current = setTimeout(connect, delay);
    }
  }, [absorb]);

  useEffect(() => {
    closedRef.current = false;

    // Backfill first so the timeline is populated even if the socket is slow
    // or blocked; the socket's own replay then de-duplicates against it.
    api
      .events(0)
      .then((body) => absorb(body.events))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));

    connect();

    return () => {
      closedRef.current = true;
      if (timerRef.current) clearTimeout(timerRef.current);
      socketRef.current?.close();
    };
  }, [absorb, connect]);

  return { events, state, error };
}
