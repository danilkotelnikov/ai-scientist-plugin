import { useState, useRef, useCallback } from "react";
import { getProvenance, type ProvenanceEntry } from "../api/jobs";

interface ProvenanceTooltipProps {
  jobId: string;
  sentenceId: string;
  /** Optional element to attach the tooltip to. Defaults to a small "prov" badge. */
  children?: React.ReactNode;
}

/**
 * Hover-anchored tooltip that fetches and displays the provenance ledger
 * entry for a single manuscript sentence:
 *
 *   GET /v1/api/jobs/:jobId/provenance/:sentenceId
 *   → { sentence, agent, model, evidence[], reflection_rounds }
 *
 * We lazy-load on first hover (cached in component state thereafter) so
 * a long manuscript doesn't trigger N requests on page render.
 */
export function ProvenanceTooltip({
  jobId,
  sentenceId,
  children,
}: ProvenanceTooltipProps): JSX.Element {
  const [data, setData] = useState<ProvenanceEntry | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const fetchedRef = useRef(false);

  const ensureLoaded = useCallback(async () => {
    if (fetchedRef.current) return;
    fetchedRef.current = true;
    try {
      const entry = await getProvenance(jobId, sentenceId);
      setData(entry);
    } catch (err) {
      setError((err as Error).message || "Failed to load provenance");
    }
  }, [jobId, sentenceId]);

  const onEnter = () => {
    setOpen(true);
    void ensureLoaded();
  };
  const onLeave = () => setOpen(false);

  return (
    <span
      className="relative inline-block"
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      onFocus={onEnter}
      onBlur={onLeave}
      tabIndex={0}
    >
      {children ?? (
        <span className="underline decoration-dotted decoration-gray-400 cursor-help text-xs text-gray-500 align-baseline ml-1">
          prov
        </span>
      )}
      {open && (
        <div
          role="tooltip"
          className="absolute z-50 left-0 top-full mt-1 w-80 max-w-[90vw]
                     bg-white border border-gray-200 rounded shadow-lg
                     p-3 text-xs text-gray-800 space-y-1"
        >
          {error && <div className="text-red-600">{error}</div>}
          {!error && !data && <div className="text-gray-500">Loading…</div>}
          {data && (
            <>
              <div className="border-b border-gray-100 pb-1 mb-1 italic text-gray-700">
                &ldquo;{data.sentence.slice(0, 140)}
                {data.sentence.length > 140 ? "…" : ""}&rdquo;
              </div>
              <Row label="Agent" value={data.agent} />
              <Row label="Model" value={data.model} />
              <Row
                label="Evidence"
                value={data.evidence.length ? data.evidence.join(", ") : "(none)"}
              />
              <Row label="Reflections" value={String(data.reflection_rounds)} />
            </>
          )}
        </div>
      )}
    </span>
  );
}

function Row({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="flex gap-2">
      <span className="font-semibold text-gray-600 shrink-0 w-20">{label}:</span>
      <span className="text-gray-800 break-words">{value}</span>
    </div>
  );
}
