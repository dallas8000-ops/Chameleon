import React, { useCallback, useEffect, useState } from "react";

import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { GenerationJob } from "../../lib/api/types";

const TERMINAL = new Set(["completed", "failed", "canceled", "blocked_provider_not_configured"]);

type JobStatusCardProps = {
  status: string;
  message?: string;
  jobId?: number;
  pollIntervalMs?: number;
};

type View = { status: string; message?: string; job?: GenerationJob };

/** Shows server-reported job state; polls GET /jobs/:id/ until terminal and stops on unmount. */
export function JobStatusCard({ status, message, jobId, pollIntervalMs = 3000 }: JobStatusCardProps) {
  const [view, setView] = useState<View>({ status, message });
  const [error, setError] = useState<unknown>(null);

  const fetchJob = useCallback(
    async (signal?: AbortSignal) => {
      if (jobId === undefined) {
        return;
      }
      try {
        const job = await apiRequest<GenerationJob>(`/jobs/${jobId}/`, { signal });
        if (!signal?.aborted) {
          setError(null);
          setView({ status: job.status, message: job.error_message || undefined, job });
        }
      } catch (caught) {
        if (!signal?.aborted) {
          setError(caught);
        }
      }
    },
    [jobId],
  );

  useEffect(() => {
    setView({ status, message });
    setError(null);
  }, [status, message, jobId]);

  const terminal = TERMINAL.has(view.status);
  useEffect(() => {
    if (jobId === undefined || terminal || error) {
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => void fetchJob(controller.signal), pollIntervalMs);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [jobId, terminal, error, view, pollIntervalMs, fetchJob]);

  const assetId = view.job?.result?.asset_id;
  return (
    <section role="status" className="mt-3 rounded border p-3">
      <h3 className="font-medium">Generation status</h3>
      <p>{view.status}</p>
      {view.message ? <p className="text-sm text-gray-700">{view.message}</p> : null}
      {view.job?.quoted_credits ? <p className="text-sm">Quoted credits: {view.job.quoted_credits}</p> : null}
      {view.status === "completed" ? (
        typeof assetId === "number" ? (
          <p className="text-sm">Saved as workspace asset #{assetId}.</p>
        ) : (
          <p className="text-sm">Completed, but the result is not saved as a workspace asset, so it cannot be used in exports.</p>
        )
      ) : null}
      {jobId !== undefined ? (
        <button type="button" onClick={() => void fetchJob()}>
          Refresh job
        </button>
      ) : null}
      {error ? <ErrorAlert error={error} /> : null}
    </section>
  );
}
