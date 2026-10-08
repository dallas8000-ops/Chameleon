import React, { useState } from "react";

import { ErrorAlert } from "../../components/ErrorAlert";
import { ApiError, apiRequest } from "../../lib/api/client";
import type { GenerationJob } from "../../lib/api/types";
import { JobStatusCard } from "../jobs/JobStatusCard";

export type GenerationQuote = { credits: number; basis: string };

type GenerationPanelProps = {
  workspaceId: number;
  projectId?: number;
  canWrite?: boolean;
  /** Server-provided pre-submit quote. The backend has no quote API yet, so this stays null. */
  quote?: GenerationQuote | null;
  pollIntervalMs?: number;
};

type JobState = { jobId?: number; status: string; message?: string };

export function GenerationPanel({ workspaceId, projectId, canWrite = true, quote = null, pollIntervalMs }: GenerationPanelProps) {
  const [prompt, setPrompt] = useState("Studio background");
  const [jobState, setJobState] = useState<JobState | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function generateImage() {
    setBusy(true);
    setError(null);
    try {
      const job = await apiRequest<GenerationJob>("/jobs/image-generation/", {
        method: "POST",
        body: JSON.stringify({ workspace_id: workspaceId, ...(projectId ? { project_id: projectId } : {}), prompt }),
      });
      setJobState({ jobId: job.id, status: job.status });
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "provider_not_configured") {
        setJobState({
          status: "blocked_provider_not_configured",
          message: "Configure Magic Hour API key on the server before generating. No job was run.",
        });
      } else {
        setJobState(null);
        setError(caught);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Generation" className="mt-6">
      <h2 className="text-xl font-semibold">Generate</h2>
      <label className="block">
        Image prompt
        <input className="block w-full border p-1" value={prompt} onChange={(event) => setPrompt(event.target.value)} />
      </label>
      {quote ? (
        <p>
          Estimated cost: {quote.credits} credits. <span className="text-sm">{quote.basis}</span>
        </p>
      ) : (
        <p className="text-sm text-gray-700">
          Cost estimate unavailable: the server does not provide a pre-submit quote yet, so paid image generation is disabled.
        </p>
      )}
      <button disabled={busy || !canWrite || !quote || prompt.trim() === ""} onClick={() => void generateImage()}>
        Generate image
      </button>
      <p className="mt-3 text-sm text-gray-700">
        Presenter generation is unavailable until secure workspace asset upload and mapping to the provider is configured.
      </p>
      <p className="text-sm text-gray-700">
        Generated results are temporary provider output and cannot be saved as workspace assets yet. Upload media as a private asset to
        use it in scenes and exports.
      </p>
      {jobState ? (
        <JobStatusCard
          key={jobState.jobId ?? "local"}
          jobId={jobState.jobId}
          status={jobState.status}
          message={jobState.message}
          pollIntervalMs={pollIntervalMs}
        />
      ) : null}
      {error ? <ErrorAlert error={error} /> : null}
    </section>
  );
}
