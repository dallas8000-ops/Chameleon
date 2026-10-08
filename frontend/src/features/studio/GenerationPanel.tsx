import React, { useState } from "react";

import { ErrorAlert } from "../../components/ErrorAlert";
import { ApiError, apiRequest } from "../../lib/api/client";
import type { GenerationJob } from "../../lib/api/types";
import { JobStatusCard } from "../jobs/JobStatusCard";

type GenerationPanelProps = {
  workspaceId: number;
  projectId?: number;
  canWrite?: boolean;
};

type JobState = { status: string; message?: string };

export function GenerationPanel({ workspaceId, projectId, canWrite = true }: GenerationPanelProps) {
  const [prompt, setPrompt] = useState("Studio background");
  const [presenter, setPresenter] = useState({ image: "", audio: "", start: "0", end: "5" });
  const [jobState, setJobState] = useState<JobState | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(path: string, body: Record<string, unknown>) {
    setBusy(true);
    setError(null);
    try {
      const job = await apiRequest<GenerationJob>(path, { method: "POST", body: JSON.stringify(body) });
      setJobState({ status: job.status });
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

  const base = { workspace_id: workspaceId, ...(projectId ? { project_id: projectId } : {}) };

  return (
    <section aria-label="Generation" className="mt-6">
      <h2 className="text-xl font-semibold">Generate</h2>
      <label className="block">
        Image prompt
        <input className="block w-full border p-1" value={prompt} onChange={(event) => setPrompt(event.target.value)} />
      </label>
      <button disabled={busy || !canWrite || prompt.trim() === ""} onClick={() => void submit("/jobs/image-generation/", { ...base, prompt })}>
        Generate image
      </button>

      <fieldset className="mt-4">
        <legend>Presenter</legend>
        {(
          [
            ["image", "Image asset ID"],
            ["audio", "Audio asset ID"],
            ["start", "Start seconds"],
            ["end", "End seconds"],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="block">
            {label}
            <input
              className="block border p-1"
              value={presenter[key]}
              onChange={(event) => setPresenter({ ...presenter, [key]: event.target.value })}
            />
          </label>
        ))}
        <button
          disabled={busy || !canWrite || presenter.image === "" || presenter.audio === ""}
          onClick={() =>
            void submit("/jobs/presenter-generation/", {
              ...base,
              image_asset_id: Number(presenter.image),
              audio_asset_id: Number(presenter.audio),
              start_seconds: Number(presenter.start),
              end_seconds: Number(presenter.end),
            })
          }
        >
          Generate presenter
        </button>
      </fieldset>

      {jobState ? <JobStatusCard status={jobState.status} message={jobState.message} /> : null}
      {error ? <ErrorAlert error={error} /> : null}
    </section>
  );
}
