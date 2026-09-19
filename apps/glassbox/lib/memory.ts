/** Memory rows as the host serves them. Mirrors fixtures/memory.json plus the
 *  grounding status written by the nightly Tavily verification pass. */

export type Provenance = "confirmed" | "stale" | "contradicted" | "unverified";

export interface MemoryRow {
  id: string;
  kind: string;
  text: string;
  source: string;
  confidence: number;
  external_claim: string | null;
  grounding?: { status?: string; last_checked?: string | null; note?: string };
}

export function provenanceOf(row: Pick<MemoryRow, "grounding">): Provenance {
  const status = row.grounding?.status;
  return status === "confirmed" || status === "stale" || status === "contradicted"
    ? status
    : "unverified";
}
