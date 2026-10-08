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
  onAssetReady?: () => void;
  initialJob?: GenerationJob;
};

type View = { status: string; message?: string; job?: GenerationJob };

/** Shows server-reported job state; polls GET /jobs/:id/ until terminal and stops on unmount. */
export function JobStatusCard({ status, message, jobId, pollIntervalMs = 3000, onAssetReady, initialJob }: JobStatusCardProps) {
  const [view, setView] = useState<View>({ status, message, job: initialJob });
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
    setView({ status, message, job: initialJob });
    setError(null);
  }, [status, message, jobId, initialJob]);

  const terminal = TERMINAL.has(view.status) && (
    view.status !== "completed" || ["ready", "failed"].includes(view.job?.asset_status ?? "")
  );
  const readyId = view.job?.asset_status === "ready" ? view.job.result?.asset_id : undefined;
  useEffect(() => { if (typeof readyId === "number") onAssetReady?.(); }, [readyId]);
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
      {typeof view.job?.quoted_credits === "number" ? <p className="text-sm">Accepted estimate: {view.job.quoted_credits} credits.</p> : null}
      {view.job && <p>Provider reported charge: {view.job.provider_reported_credits ?? "Unknown"} credits.</p>}
      {view.status === "completed" ? (
        view.job?.asset_status === "ready" && typeof assetId === "number" ? (
          <p className="text-sm">Saved as workspace asset #{assetId}.</p>
        ) : (
          <p className="text-sm">{view.job?.asset_status === "failed"
            ? `Provider completed; Asset save failed (${view.job.asset_error_code}). No regeneration or refund is implied.`
            : "Provider completed; saving private Asset. It is not ready for scenes or export."}</p>
        )
      ) : null}
      {view.job?.asset_retryable && <button onClick={() => {
        void apiRequest<GenerationJob>(`/jobs/${jobId}/asset-ingestion/retry/`, { method: "POST", body: "{}" })
          .then(job => { setError(null); setView({ status: job.status, job }); })
          .catch(setError);
      }}>Retry saving only</button>}
      {jobId !== undefined ? (
        <button type="button" onClick={() => void fetchJob()}>
          Refresh job
        </button>
      ) : null}
      {error ? <ErrorAlert error={error} /> : null}
    </section>
  );
}
