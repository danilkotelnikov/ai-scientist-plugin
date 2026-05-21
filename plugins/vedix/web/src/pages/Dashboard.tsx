import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listJobs, type JobStatus } from "../api/jobs";

export function Dashboard(): JSX.Element {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["jobs"],
    queryFn: listJobs,
  });

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Recent jobs</h1>
        <Link to="/jobs/new" className="vedix-button">
          New job
        </Link>
      </header>

      {isLoading && <p className="text-gray-500">Loading…</p>}
      {isError && (
        <p className="text-red-600">{(error as Error).message}</p>
      )}
      {data && data.length === 0 && (
        <div className="vedix-card p-8 text-center text-gray-500">
          No jobs yet. Click <strong>New job</strong> to start one.
        </div>
      )}
      {data && data.length > 0 && (
        <ul className="vedix-card divide-y divide-gray-100">
          {data.map((j) => (
            <JobRow key={j.job_id} job={j} />
          ))}
        </ul>
      )}
    </div>
  );
}

function JobRow({ job }: { job: JobStatus }): JSX.Element {
  return (
    <li className="flex items-center justify-between p-4">
      <Link to={`/jobs/${job.job_id}`} className="flex-1">
        <div className="font-mono text-sm">{job.job_id.slice(0, 8)}…</div>
        <div className="text-xs text-gray-500">
          {job.phase ?? "—"} · {job.progress}%
        </div>
      </Link>
      <StateBadge state={job.state} />
    </li>
  );
}

function StateBadge({ state }: { state: JobStatus["state"] }): JSX.Element {
  const styles: Record<JobStatus["state"], string> = {
    queued: "bg-gray-100 text-gray-700",
    running: "bg-blue-100 text-blue-700",
    done: "bg-emerald-100 text-emerald-700",
    failed: "bg-red-100 text-red-700",
  };
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full ${styles[state]}`}
    >
      {state}
    </span>
  );
}
