/** Mirrors the Event dataclass in apps/host/events.py.
 *
 *  One shape for everything the host observes, so the timeline renders a single
 *  stream and adding a new kind of observable thing never touches the transport.
 *  Additive changes only — old JSONL session files must stay readable.
 */

export type EventKind =
  | "action"
  | "inference"
  | "egress_request"
  | "egress_decision"
  | "memory_write"
  | "search"
  | "voice"
  | "error";

export type AgentName = "calendar" | "email" | "research" | "system";

export interface LifeEvent {
  id: string;
  ts: number;
  kind: EventKind;
  agent: AgentName;
  summary: string;
  /** True until Nano's one-line rewrite lands. Rendered dimmed. */
  summary_pending: boolean;
  session: string;
  detail: Record<string, unknown>;
}

export interface Approval {
  id: string;
  agent: AgentName;
  host: string;
  reason: string;
  requested_at: number;
  sandbox_id: string;
  detail: Record<string, unknown>;
}

export type Decision = "allow" | "deny";
export type Scope = "once" | "always";

export type Task = "plan" | "execute" | "summarize";

export interface RoutingTable {
  routing: Record<string, string>;
  tasks: Task[];
}

export interface Health {
  ok: boolean;
  session: string;
  uptime_s: number;
  driver: string;
  demo: string;
  events: number;
}

/** A model id still carrying the scaffold's placeholder marker. */
export function isPlaceholder(model: string): boolean {
  return /\bTODO\b/i.test(model);
}

export const KIND_COLOUR: Record<EventKind, string> = {
  action: "var(--k-action)",
  inference: "var(--k-inference)",
  egress_request: "var(--k-egress-request)",
  egress_decision: "var(--k-egress-allow)",
  memory_write: "var(--k-memory)",
  search: "var(--k-search)",
  voice: "var(--k-voice)",
  error: "var(--k-error)",
};

export const KIND_LABEL: Record<EventKind, string> = {
  action: "act",
  inference: "llm",
  egress_request: "egress",
  egress_decision: "decided",
  memory_write: "memory",
  search: "search",
  voice: "voice",
  error: "error",
};
