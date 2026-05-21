import { api } from "./client";

/**
 * ExperimentSetup mirrors the Pydantic model at
 * `plugins/vedix/saas/app/schemas/job.py:JobCreateRequest` which itself
 * mirrors `orchestrator.preflight_dialog.ExperimentSetup`. Keep the
 * literal unions in sync.
 */
export type Discipline =
  | "chemistry"
  | "biology"
  | "medicine"
  | "physics"
  | "mathematics"
  | "geology"
  | "computer_science"
  | "humanities";

export type Language = "en" | "ru" | "es" | "de" | "fr" | "zh" | "ja";

export type HypothesisStyle =
  | "confirmatory"
  | "exploratory"
  | "comparative"
  | "descriptive";

export type ExperimentType =
  | "empirical"
  | "computational"
  | "review"
  | "theoretical";

export type ExpectedDirection =
  | "increase"
  | "decrease"
  | "no-change"
  | "comparison";

export interface ExperimentSetup {
  topic: string;
  discipline: Discipline;
  language: Language;
  venue: string;
  hypothesis_style: HypothesisStyle;
  experiment_type: ExperimentType;
  primary_metric: string;
  expected_direction: ExpectedDirection;
  tolerance: number;
  codebase_path?: string;
}

export type JobState = "queued" | "running" | "done" | "failed";

export interface JobCreateResponse {
  job_id: string;
  state: JobState;
}

export interface JobStatus {
  job_id: string;
  state: JobState;
  phase: string | null;
  progress: number;
  artifact_root?: string | null;
  error?: string | null;
}

export interface ProvenanceEntry {
  sentence: string;
  agent: string;
  model: string;
  evidence: string[];
  reflection_rounds: number;
}

export const createJob = (payload: ExperimentSetup): Promise<JobCreateResponse> =>
  api<JobCreateResponse>("/v1/api/jobs", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const getJob = (id: string): Promise<JobStatus> =>
  api<JobStatus>(`/v1/api/jobs/${id}`);

export const listJobs = (): Promise<JobStatus[]> =>
  api<JobStatus[]>("/v1/api/jobs");

export const getProvenance = (
  jobId: string,
  sentenceId: string,
): Promise<ProvenanceEntry> =>
  api<ProvenanceEntry>(`/v1/api/jobs/${jobId}/provenance/${sentenceId}`);

export const manuscriptUrl = (jobId: string): string =>
  `/v1/api/jobs/${jobId}/manuscript.pdf`;
