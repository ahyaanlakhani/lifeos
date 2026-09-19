"use client";

/** Approvals.
 *
 *  Built phone-first because that is where it gets used: the agent is running
 *  unattended and you are not at a desk. "I denied it from my phone" only lands
 *  if the interface is genuinely built for a phone — big targets, one decision
 *  per screen, no horizontal scrolling, and enough context on the card to
 *  decide without opening anything else.
 */

import { useCallback, useEffect, useState } from "react";
import { Conn } from "../../components/Conn";
import { api, HostError } from "../../lib/api";
import type { Approval, Decision, Scope } from "../../lib/types";

function ago(ts: number): string {
  const seconds = Math.max(0, Math.round(Date.now() / 1000 - ts));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  return `${Math.round(seconds / 3600)}h ago`;
}

export default function Approvals() {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [decided, setDecided] = useState<{ id: string; host: string; decision: Decision }[]>([]);

  const refresh = useCallback(async () => {
    try {
      const body = await api.approvals();
      setApprovals(body.approvals);
      setConnected(true);
      setError(null);
    } catch (err) {
      setConnected(false);
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 2000);
    return () => clearInterval(timer);
  }, [refresh]);

  async function decide(request: Approval, decision: Decision, scope: Scope) {
    setBusy(request.id);
    setError(null);
    try {
      await api.decide(request.id, decision, scope);
      setApprovals((current) => current.filter((a) => a.id !== request.id));
      setDecided((current) => [{ id: request.id, host: request.host, decision }, ...current].slice(0, 5));
    } catch (err) {
      // A 409 means the backend cannot express that scope — the policy-file
      // fallback has no way to allow something once. Say so rather than
      // leaving the card looking broken.
      setError(
        err instanceof HostError && err.status === 409
          ? `${err.message} Deny, or allow it permanently.`
          : err instanceof Error
            ? err.message
            : String(err),
      );
      refresh();
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Approvals</h1>
          <p className="sub">
            A sandbox tried to reach a host that is not on its allowlist. Nothing
            has gone out. Until you decide, it stays blocked.
          </p>
        </div>
        <Conn state={connected ? "live" : "down"} count={approvals.length} />
      </div>

      {error && <div className="banner">{error}</div>}

      {approvals.length === 0 ? (
        <div className="card">
          <div className="empty">
            <strong>Nothing waiting</strong>
            Every agent is inside its allowlist.
          </div>
        </div>
      ) : (
        approvals.map((request) => (
          <div className="card urgent" key={request.id}>
            <h2>
              <span style={{ textTransform: "capitalize" }}>{request.agent}</span> wants to
              reach
            </h2>
            <div className="host">{request.host}</div>
            <p className="why">
              {request.reason === "not_in_allowlist"
                ? "Not on this agent's allowlist."
                : request.reason || "No reason given."}
              {typeof request.detail?.detail === "string" && (
                <>
                  {" "}
                  Attempted: <code>{String(request.detail.detail)}</code>.
                </>
              )}
            </p>
            <p className="why" style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
              {request.id} · {ago(request.requested_at)}
            </p>

            <div className="actions">
              <button
                className="allow"
                disabled={busy === request.id}
                onClick={() => decide(request, "allow", "always")}
              >
                Allow always
              </button>
              <button
                className="deny"
                disabled={busy === request.id}
                onClick={() => decide(request, "deny", "always")}
              >
                Deny
              </button>
            </div>
          </div>
        ))
      )}

      {decided.length > 0 && (
        <div className="card" style={{ marginTop: 18 }}>
          <h2 style={{ fontSize: 13, color: "var(--text-dim)" }}>Just decided</h2>
          {decided.map((entry) => (
            <p key={entry.id} className="why" style={{ fontFamily: "var(--mono)", fontSize: 12 }}>
              <span
                style={{
                  color: entry.decision === "deny" ? "var(--danger)" : "var(--ok)",
                }}
              >
                {entry.decision}
              </span>{" "}
              {entry.host}
            </p>
          ))}
        </div>
      )}
    </>
  );
}
