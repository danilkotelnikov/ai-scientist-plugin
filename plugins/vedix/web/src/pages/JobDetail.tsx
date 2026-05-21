import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { getJob } from "../api/jobs";
import { ManuscriptPreview } from "../components/ManuscriptPreview";
import { ProgressStream } from "../components/ProgressStream";

export function JobDetail(): JSX.Element {
  const { id = "" } = useParams<{ id: string }>();

  const statusQuery = useQuery({
    queryKey: ["job", id],
    queryFn: () => getJob(id),
    refetchInterval: (q) => {
      const state = q.state.data?.state;
      return state === "running" || state === "queued" ? 5_000 : false;
    },
    enabled: Boolean(id),
  });

  if (!id) {
    return <div className="p-6 text-red-600">Missing job id.</div>;
  }

  const status = statusQuery.data;

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Job {id.slice(0, 8)}…</h1>
          {status && (
            <p className="text-sm text-gray-500 mt-1">
              state: <strong>{status.state}</strong>
              {status.phase && (
                <>
                  {" "}· phase: <strong>{status.phase}</strong>
                </>
              )}{" "}
              · progress: <strong>{status.progress}%</strong>
            </p>
          )}
        </div>
      </header>

      {statusQuery.isError && (
        <p className="text-red-600">
          {(statusQuery.error as Error).message}
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ProgressStream jobId={id} />
        {status?.state === "done" ? (
          <ManuscriptPreview jobId={id} />
        ) : (
          <div className="vedix-card p-8 text-center text-gray-500">
            Manuscript preview will appear here when the run completes.
          </div>
        )}
      </div>
    </div>
  );
}
