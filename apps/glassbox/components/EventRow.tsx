import { KIND_COLOUR, KIND_LABEL, type LifeEvent } from "../lib/types";

function clockTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

/** Latency and spend ride along on inference rows. That telemetry is only
 *  possible because every call through complete() emits an event. */
function inferenceMeta(detail: Record<string, unknown>): string | null {
  const latency = detail.latency_ms;
  const cost = detail.cost_usd;
  const parts: string[] = [];
  if (typeof latency === "number") parts.push(`${latency}ms`);
  if (typeof cost === "number") parts.push(`$${cost.toFixed(4)}`);
  return parts.length ? parts.join(" · ") : null;
}

export function EventRow({ event }: { event: LifeEvent }) {
  const colour = KIND_COLOUR[event.kind] ?? "var(--k-action)";
  const meta = event.kind === "inference" ? inferenceMeta(event.detail) : null;
  const model = typeof event.detail.model === "string" ? event.detail.model : null;

  return (
    <div
      className={`row${event.summary_pending ? " pending" : ""}`}
      style={{ ["--kind" as string]: colour }}
    >
      <span className="time">{clockTime(event.ts)}</span>
      <span className="pip" aria-hidden="true" />
      <span className="body">
        <span className="text">{event.summary}</span>
      </span>
      <span className="meta">
        {meta && <span>{meta}</span>}
        {model && <span>{model.split("/").pop()}</span>}
        <span className="tag">{event.agent}</span>
        <span className="tag kind">{KIND_LABEL[event.kind] ?? event.kind}</span>
      </span>
    </div>
  );
}
