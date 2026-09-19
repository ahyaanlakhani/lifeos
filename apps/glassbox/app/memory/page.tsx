"use client";

/** Memory.
 *
 *  Two things, in the order they matter. First: what LifeOS currently believes,
 *  each row carrying where it came from and — for claims about the outside
 *  world — whether last night's Tavily pass found it confirmed, stale or
 *  contradicted. Second: the raw stream of changes to the workspace.
 *
 *  The provenance badge is the payoff from grounding memory against a live
 *  search rather than letting remembered facts quietly rot.
 */

import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";
import { provenanceOf, type MemoryRow } from "../../lib/memory";
import type { LifeEvent } from "../../lib/types";

function Diff({ text }: { text: string }) {
  return (
    <pre className="diff">
      {text.split("\n").map((line, index) => {
        const cls = line.startsWith("+")
          ? "add"
          : line.startsWith("-")
            ? "del"
            : line.startsWith("@@")
              ? "hunk"
              : undefined;
        return (
          <span key={index} className={cls}>
            {line}
            {"\n"}
          </span>
        );
      })}
    </pre>
  );
}

export default function Memory() {
  const [rows, setRows] = useState<MemoryRow[]>([]);
  const [source, setSource] = useState<string>("");
  const [changes, setChanges] = useState<LifeEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [memory, diffs] = await Promise.all([api.memory(), api.memoryDiff(40)]);
      setRows(memory.rows);
      setSource(memory.source);
      setChanges(diffs.changes);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 4000);
    return () => clearInterval(timer);
  }, [refresh]);

  const recent = [...changes].reverse().slice(0, 12);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Memory</h1>
          <p className="sub">
            What LifeOS believes and where each thing came from. Claims about the
            outside world are re-checked nightly against a live search, so a fact
            that has gone stale says so instead of being presented flat.
          </p>
        </div>
        {source && <span className="conn">source · {source}</span>}
      </div>

      {error && <div className="banner">{error}</div>}

      {rows.length === 0 ? (
        <div className="card">
          <div className="empty">
            <strong>Memory is empty</strong>
            {source === "supabase"
              ? "No rows in the vector store yet."
              : "No seed rows loaded."}
          </div>
        </div>
      ) : (
        rows.map((row) => {
          const provenance = provenanceOf(row);
          return (
            <div className="card" key={row.id}>
              <div className="mem">
                <div className="grow">
                  <span className="tag">{row.kind}</span>
                  <p style={{ margin: "7px 0 0" }}>{row.text}</p>
                  <p className="why" style={{ margin: "6px 0 0", fontSize: 12 }}>
                    {row.source} · confidence {row.confidence.toFixed(2)}
                    {row.external_claim && (
                      <>
                        {" "}
                        · checked as{" "}
                        <span style={{ fontFamily: "var(--mono)" }}>{row.external_claim}</span>
                      </>
                    )}
                  </p>
                </div>
                <span className={`prov ${provenance}`} title={row.grounding?.note ?? ""}>
                  {provenance}
                </span>
              </div>
            </div>
          );
        })
      )}

      <h1 style={{ fontSize: 15, margin: "26px 0 4px" }}>Recent changes</h1>
      <p className="sub" style={{ marginBottom: 12 }}>
        Writes to the sandbox workspace, as they happen.
      </p>

      {recent.length === 0 ? (
        <div className="card">
          <div className="empty">
            <strong>No changes yet</strong>
            Workspace writes appear here as the agents learn things.
          </div>
        </div>
      ) : (
        recent.map((event) => {
          const path = typeof event.detail?.path === "string" ? event.detail.path : null;
          const diff = typeof event.detail?.diff === "string" ? event.detail.diff : "";
          const action = typeof event.detail?.action === "string" ? event.detail.action : "wrote";
          const isOpen = open === event.id;

          return (
            <div className="card" key={event.id}>
              <div className="mem">
                <div className="grow">
                  <h2 style={{ fontFamily: "var(--mono)", fontSize: 13 }}>
                    {path ?? event.summary}
                  </h2>
                  <p className="why" style={{ margin: "2px 0 0" }}>
                    {action} by {event.agent} ·{" "}
                    {new Date(event.ts * 1000).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                      hour12: false,
                    })}
                  </p>
                </div>
              </div>

              {diff && (
                <>
                  <div className="toolbar">
                    <button onClick={() => setOpen(isOpen ? null : event.id)}>
                      {isOpen ? "Hide diff" : "Show diff"}
                    </button>
                  </div>
                  {isOpen && <Diff text={diff} />}
                </>
              )}
            </div>
          );
        })
      )}
    </>
  );
}
