import type { ConnectionState } from "../lib/useStream";

const LABEL: Record<ConnectionState, string> = {
  connecting: "connecting",
  live: "live",
  down: "reconnecting",
};

export function Conn({ state, count }: { state: ConnectionState; count?: number }) {
  return (
    <span className="conn" role="status">
      <span className={`dot ${state === "live" ? "live" : state === "down" ? "down" : ""}`} />
      {LABEL[state]}
      {count !== undefined && ` · ${count}`}
    </span>
  );
}
