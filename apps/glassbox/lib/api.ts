/** The agent host is the only backend Glass Box talks to.
 *
 *  Glass Box writes exactly two things — approval decisions and routing.yaml.
 *  Everything else it renders is someone else's state. Keeping it read-mostly
 *  is what lets it be deployed separately and handed to judges as a URL.
 */

import type { MemoryRow } from "./memory";
import type { Approval, Decision, Health, LifeEvent, RoutingTable, Scope } from "./types";

export const HOST_URL = process.env.NEXT_PUBLIC_HOST_URL ?? "http://localhost:8000";
export const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/api/stream";

export class HostError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "HostError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${HOST_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    // A dead host is the normal state while the VM is down. Say so plainly
    // rather than surfacing a browser-specific network message.
    throw new HostError(`Cannot reach the agent host at ${HOST_URL}`, 0);
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* non-JSON error body; the status text will do */
    }
    throw new HostError(detail, response.status);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("/api/health"),

  events: (since = 0, limit = 1000) =>
    request<{ session: string; now: number; events: LifeEvent[] }>(
      `/api/events?since=${since}&limit=${limit}`,
    ),

  approvals: () => request<{ approvals: Approval[] }>("/api/approvals"),

  decide: (id: string, decision: Decision, scope: Scope) =>
    request<{ ok: boolean }>(`/api/approvals/${encodeURIComponent(id)}`, {
      method: "POST",
      body: JSON.stringify({ decision, scope }),
    }),

  memory: () => request<{ rows: MemoryRow[]; source: string }>("/api/memory"),

  memoryDiff: (limit = 50) =>
    request<{ changes: LifeEvent[] }>(`/api/memory/diff?limit=${limit}`),

  routing: () => request<RoutingTable>("/api/routing"),

  setRouting: (updates: Record<string, string>) =>
    request<{ routing: Record<string, string> }>("/api/routing", {
      method: "POST",
      body: JSON.stringify(updates),
    }),

  sandboxes: () =>
    request<{ sandboxes: { id: string; agent: string; state: string; started_at: number }[] }>(
      "/api/sandboxes",
    ),
};
