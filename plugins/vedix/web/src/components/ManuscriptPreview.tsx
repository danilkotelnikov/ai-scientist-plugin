import { useEffect, useMemo, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { API_BASE } from "../api/client";
import { getToken } from "../lib/auth";
import { manuscriptUrl } from "../api/jobs";

// Pin pdf.js worker to the version bundled with react-pdf so the worker
// thread agrees with the main-thread reader.
pdfjs.GlobalWorkerOptions.workerSrc = `https://cdn.jsdelivr.net/npm/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.js`;

interface ManuscriptPreviewProps {
  /** Either pass a jobId (we resolve to /jobs/:id/manuscript.pdf) or a raw URL. */
  jobId?: string;
  url?: string;
  /** Render width in CSS pixels. */
  width?: number;
}

/**
 * PDF viewer for the rendered manuscript. We fetch the bytes with an
 * Authorization header (react-pdf accepts ArrayBuffer) rather than passing
 * a bare URL, because the backend manuscript endpoint is JWT-protected.
 */
export function ManuscriptPreview({
  jobId,
  url,
  width = 800,
}: ManuscriptPreviewProps): JSX.Element {
  const [numPages, setNumPages] = useState(0);
  const [bytes, setBytes] = useState<ArrayBuffer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const sourceUrl = useMemo(() => {
    if (url) return url;
    if (jobId) return `${API_BASE}${manuscriptUrl(jobId)}`;
    return null;
  }, [url, jobId]);

  useEffect(() => {
    if (!sourceUrl) {
      setError("No manuscript source provided");
      setLoading(false);
      return;
    }

    let cancelled = false;
    const controller = new AbortController();

    (async () => {
      setLoading(true);
      setError(null);
      try {
        const token = getToken();
        const r = await fetch(sourceUrl, {
          signal: controller.signal,
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!r.ok) {
          throw new Error(`HTTP ${r.status}`);
        }
        const buf = await r.arrayBuffer();
        if (!cancelled) {
          setBytes(buf);
        }
      } catch (err) {
        if (cancelled || (err as Error).name === "AbortError") return;
        setError((err as Error).message || "Failed to load manuscript");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [sourceUrl]);

  if (loading) {
    return (
      <div className="vedix-card p-8 text-center text-gray-500">
        Loading manuscript…
      </div>
    );
  }

  if (error || !bytes) {
    return (
      <div className="vedix-card p-8 text-center text-red-600">
        {error ?? "No PDF available yet."}
      </div>
    );
  }

  return (
    <div className="vedix-card overflow-auto h-[calc(100vh-200px)]">
      <Document
        file={{ data: bytes }}
        onLoadSuccess={({ numPages: n }) => setNumPages(n)}
        onLoadError={(err) => setError(err.message)}
        loading={<div className="p-8 text-gray-500">Parsing PDF…</div>}
      >
        {Array.from({ length: numPages }, (_, i) => (
          <Page
            key={`page_${i + 1}`}
            pageNumber={i + 1}
            width={width}
            className="border-b border-gray-100"
          />
        ))}
      </Document>
    </div>
  );
}
