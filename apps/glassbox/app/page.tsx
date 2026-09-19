"use client";

import { useMemo, useState } from "react";
import { Conn } from "../components/Conn";
import { EventRow } from "../components/EventRow";
import { useStream } from "../lib/useStream";
import { KIND_LABEL, type EventKind } from "../lib/types";

const FILTERS: { value: "all" | EventKind; label: string }[] = [
  { value: "all", label: "everything" },
  { value: "action", label: KIND_LABEL.action },
  { value: "inference", label: KIND_LABEL.inference },
  { value: "search", label: KIND_LABEL.search },
  { value: "memory_write", label: KIND_LABEL.memory_write },
  { value: "egress_request", label: KIND_LABEL.egress_request },
  { value: "error", label: KIND_LABEL.error },
];

export default function Timeline() {
  const { events, state, error } = useStream();
  const [filter, setFilter] = useState<"all" | EventKind>("all");

  const shown = useMemo(
    () => (filter === "all" ? events : events.filter((e) => e.kind === filter)),
    [events, filter],
  );

  // Newest at the top: on a live feed the eye should not have to chase the
  // bottom of a growing list.
  const ordered = useMemo(() => [...shown].reverse(), [shown]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Timeline</h1>
          <p className="sub">
            Every action the agents take, as they take it. Raw log lines appear
            immediately and dimmed; Nano rewrites each into one clean line a beat
            later.
          </p>
        </div>
        <Conn state={state} count={events.length} />
      </div>

      {error && <div className="banner">{error}</div>}

      <div className="filters" role="group" aria-label="Filter by event kind">
        {FILTERS.map((option) => (
          <button
            key={option.value}
            onClick={() => setFilter(option.value)}
            aria-pressed={filter === option.value}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div className="timeline">
        {ordered.length === 0 ? (
          <div className="empty">
            <strong>Nothing yet</strong>
            {state === "live"
              ? "The agents are idle. Start a sandbox and this fills up."
              : `Waiting for the agent host.`}
          </div>
        ) : (
          ordered.map((event) => <EventRow key={event.id} event={event} />)
        )}
      </div>
    </>
  );
}
