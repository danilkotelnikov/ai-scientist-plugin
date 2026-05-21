import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { createJob, type ExperimentSetup } from "../api/jobs";

/**
 * zod schema mirrors plugins/vedix/saas/app/schemas/job.py:JobCreateRequest.
 * Keep the literal unions and the (10..500) length bounds aligned with the
 * Pydantic source of truth.
 */
const schema = z.object({
  topic: z
    .string()
    .min(10, "Topic must be at least 10 characters")
    .max(500, "Topic must be 500 characters or fewer"),
  discipline: z.enum([
    "chemistry",
    "biology",
    "medicine",
    "physics",
    "mathematics",
    "geology",
    "computer_science",
    "humanities",
  ]),
  language: z.enum(["en", "ru", "es", "de", "fr", "zh", "ja"]),
  venue: z.string().min(1, "Venue is required"),
  hypothesis_style: z.enum([
    "confirmatory",
    "exploratory",
    "comparative",
    "descriptive",
  ]),
  experiment_type: z.enum([
    "empirical",
    "computational",
    "review",
    "theoretical",
  ]),
  primary_metric: z.string().min(1, "Primary metric is required"),
  expected_direction: z.enum(["increase", "decrease", "no-change", "comparison"]),
  tolerance: z.coerce
    .number()
    .gt(0, "Must be > 0")
    .lt(1, "Must be < 1"),
  codebase_path: z.string().optional(),
});

type FormValues = z.infer<typeof schema>;

const DISCIPLINES: Array<{ value: ExperimentSetup["discipline"]; label: string }> = [
  { value: "chemistry", label: "Chemistry" },
  { value: "biology", label: "Biology" },
  { value: "medicine", label: "Medicine" },
  { value: "physics", label: "Physics" },
  { value: "mathematics", label: "Mathematics" },
  { value: "geology", label: "Geology" },
  { value: "computer_science", label: "Computer Science" },
  { value: "humanities", label: "Humanities" },
];

const LANGUAGES: Array<{ value: ExperimentSetup["language"]; label: string }> = [
  { value: "en", label: "English" },
  { value: "ru", label: "Russian" },
  { value: "es", label: "Spanish" },
  { value: "de", label: "German" },
  { value: "fr", label: "French" },
  { value: "zh", label: "Chinese" },
  { value: "ja", label: "Japanese" },
];

const HYPOTHESIS_STYLES: Array<{
  value: ExperimentSetup["hypothesis_style"];
  label: string;
}> = [
  { value: "confirmatory", label: "Confirmatory" },
  { value: "exploratory", label: "Exploratory" },
  { value: "comparative", label: "Comparative" },
  { value: "descriptive", label: "Descriptive" },
];

const EXPERIMENT_TYPES: Array<{
  value: ExperimentSetup["experiment_type"];
  label: string;
}> = [
  { value: "empirical", label: "Empirical" },
  { value: "computational", label: "Computational" },
  { value: "review", label: "Review" },
  { value: "theoretical", label: "Theoretical" },
];

const DIRECTIONS: Array<{
  value: ExperimentSetup["expected_direction"];
  label: string;
}> = [
  { value: "increase", label: "Increase" },
  { value: "decrease", label: "Decrease" },
  { value: "no-change", label: "No change" },
  { value: "comparison", label: "Comparison" },
];

const DEFAULTS: FormValues = {
  topic: "",
  discipline: "computer_science",
  language: "en",
  venue: "preprint",
  hypothesis_style: "confirmatory",
  experiment_type: "computational",
  primary_metric: "accuracy",
  expected_direction: "increase",
  tolerance: 0.05,
  codebase_path: undefined,
};

export function JobForm(): JSX.Element {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: DEFAULTS,
  });
  const navigate = useNavigate();

  const mutation = useMutation({
    mutationFn: (payload: ExperimentSetup) => createJob(payload),
    onSuccess: (response) => {
      navigate(`/jobs/${response.job_id}`);
    },
  });

  const onSubmit = (values: FormValues) => {
    // react-hook-form returns strings for `<input type="number">`; zod's
    // `.coerce.number()` already converted, but we trim the optional path
    // here so the API doesn't receive an empty string.
    const payload: ExperimentSetup = {
      ...values,
      codebase_path: values.codebase_path?.trim() ? values.codebase_path : undefined,
    };
    mutation.mutate(payload);
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-5 p-6 max-w-2xl">
      <h1 className="text-2xl font-bold">New research job</h1>

      <Field label="Topic" error={errors.topic?.message}>
        <textarea
          {...register("topic")}
          rows={3}
          placeholder="Describe the research question in plain English."
          className="vedix-input w-full"
        />
      </Field>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Field label="Discipline" error={errors.discipline?.message}>
          <select {...register("discipline")} className="vedix-input w-full">
            {DISCIPLINES.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Language" error={errors.language?.message}>
          <select {...register("language")} className="vedix-input w-full">
            {LANGUAGES.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Venue" error={errors.venue?.message}>
          <input
            {...register("venue")}
            placeholder="preprint, nature, jacs…"
            className="vedix-input w-full"
          />
        </Field>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Field label="Hypothesis style" error={errors.hypothesis_style?.message}>
          <select {...register("hypothesis_style")} className="vedix-input w-full">
            {HYPOTHESIS_STYLES.map((h) => (
              <option key={h.value} value={h.value}>
                {h.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Experiment type" error={errors.experiment_type?.message}>
          <select {...register("experiment_type")} className="vedix-input w-full">
            {EXPERIMENT_TYPES.map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </select>
        </Field>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Field label="Primary metric" error={errors.primary_metric?.message}>
          <input {...register("primary_metric")} className="vedix-input w-full" />
        </Field>

        <Field label="Expected direction" error={errors.expected_direction?.message}>
          <select {...register("expected_direction")} className="vedix-input w-full">
            {DIRECTIONS.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Tolerance (0–1)" error={errors.tolerance?.message}>
          <input
            type="number"
            step="0.01"
            {...register("tolerance")}
            className="vedix-input w-full"
          />
        </Field>
      </div>

      <Field
        label="Codebase path (optional)"
        error={errors.codebase_path?.message}
        hint="Local path to source code if this is a codebase-aware run."
      >
        <input {...register("codebase_path")} className="vedix-input w-full" />
      </Field>

      {mutation.isError && (
        <div className="text-red-600 text-sm" role="alert">
          {(mutation.error as Error).message}
        </div>
      )}

      <button
        type="submit"
        disabled={isSubmitting || mutation.isPending}
        className="vedix-button"
      >
        {mutation.isPending ? "Submitting…" : "Run pipeline"}
      </button>
    </form>
  );
}

interface FieldProps {
  label: string;
  error?: string | undefined;
  hint?: string;
  children: React.ReactNode;
}

function Field({ label, error, hint, children }: FieldProps): JSX.Element {
  return (
    <label className="block space-y-1">
      <span className="font-medium text-sm text-gray-700">{label}</span>
      {children}
      {hint && !error && <p className="text-xs text-gray-500">{hint}</p>}
      {error && <p className="text-red-600 text-sm">{error}</p>}
    </label>
  );
}
