import React, { useCallback, useEffect, useRef, useState } from "react";
import { ErrorAlert } from "../../components/ErrorAlert";
import { ApiError, apiRequest } from "../../lib/api/client";
import type { GenerationCapabilities, GenerationJob, GenerationQuote } from "../../lib/api/types";
import { useSessionStore } from "../../lib/auth/session-store";
import { JobStatusCard } from "../jobs/JobStatusCard";

type Props = {
  workspaceId: number;
  projectId?: number;
  canWrite?: boolean;
  pollIntervalMs?: number;
  onAssetReady?: () => void;
};
type Attempt = { key: string; payload: Record<string, unknown>; job?: GenerationJob };

export function GenerationPanel({ workspaceId, projectId, canWrite = true, pollIntervalMs, onAssetReady }: Props) {
  const userId = useSessionStore(state => state.user?.id);
  const sessionStatus = useSessionStore(state => state.status);
  const [prompt, setPrompt] = useState("Studio background");
  const [ratio, setRatio] = useState("1:1");
  const [quote, setQuote] = useState<GenerationQuote | null>(null);
  const [job, setJob] = useState<GenerationJob | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [reason, setReason] = useState("Checking server capability and pricing.");
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [revision, setRevision] = useState(0);
  const attempt = useRef<Attempt | null>(null);
  const inFlight = useRef(false);
  const context = useRef(0);
  const storageKey = `generation-attempt:${userId ?? "session"}:${workspaceId}:${projectId ?? "none"}`;

  useEffect(() => {
    context.current += 1;
    attempt.current = null;
    setJob(null);
    setQuote(null);
    setUncertain(false);
    setBusy(false);
    setError(null);
    try {
      const saved = sessionStorage.getItem(storageKey);
      if (saved) {
        const parsed = JSON.parse(saved) as Attempt;
        if (typeof parsed?.key === "string" && parsed.payload?.quote_id) {
          attempt.current = parsed;
          if (parsed.job?.id && parsed.job.status) setJob(parsed.job);
          else setUncertain(true);
        } else throw new Error("Invalid saved attempt.");
      }
    } catch {
      setUncertain(true);
      setError(new Error("Unable to restore submission identity. Do not generate again; contact an operator."));
    }
    return () => { context.current += 1; };
  }, [storageKey, sessionStatus]);

  useEffect(() => {
    const controller = new AbortController();
    setQuote(null);
    if (!canWrite || uncertain || job || !prompt.trim() || sessionStatus === "anonymous") {
      setReason(!canWrite ? "Read-only workspace." : "Review or resolve the existing attempt first.");
      return () => controller.abort();
    }
    const timer = setTimeout(() => {
      void (async () => {
        try {
          const capabilities = await apiRequest<GenerationCapabilities>(`/jobs/capabilities/?workspace_id=${workspaceId}`, { signal: controller.signal });
          const capability = capabilities.capabilities.find(item => item.capability === "image.generate");
          if (!capability?.available || !capability.can_submit) {
            if (!controller.signal.aborted) setReason(capability?.reason_code ?? "Generation unavailable.");
            return;
          }
          const next = await apiRequest<GenerationQuote>("/jobs/image-generation/quote/", {
            method: "POST", signal: controller.signal,
            body: JSON.stringify({ workspace_id: workspaceId, ...(projectId ? { project_id: projectId } : {}), prompt, aspect_ratio: ratio }),
          });
          if (!controller.signal.aborted) {
            if (!Number.isInteger(next.estimated_credits) || next.estimated_credits < 0
                || !Number.isFinite(Date.parse(next.expires_at)) || Date.parse(next.expires_at) <= Date.now()) {
              setReason("The server returned an invalid or expired quote.");
              return;
            }
            setQuote(next);
            setReason("");
          }
        } catch (caught) {
          if (!controller.signal.aborted) {
            setReason(caught instanceof Error ? caught.message : "Quote unavailable.");
          }
        }
      })();
    }, 150);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [workspaceId, projectId, prompt, ratio, canWrite, uncertain, revision, sessionStatus, userId, job]);

  useEffect(() => {
    if (!quote) return;
    const timer = setTimeout(() => {
      setQuote(null);
      setReason("Quote expired. Request a new estimate.");
    }, Math.max(0, Date.parse(quote.expires_at) - Date.now()));
    return () => clearTimeout(timer);
  }, [quote]);

  const assetReady = useCallback((readyJob: GenerationJob) => {
    const current = attempt.current;
    if (!current || current.job?.id !== readyJob.id) return;
    current.job = readyJob;
    try { sessionStorage.setItem(storageKey, JSON.stringify(current)); }
    catch { setError(new Error("Unable to preserve updated job state. The existing job is still saved on the server.")); }
    setJob(readyJob);
    onAssetReady?.();
  }, [storageKey, onAssetReady]);

  async function submit(resolve = false) {
    if (inFlight.current || !canWrite) return;
    if (!resolve && (!quote || Date.parse(quote.expires_at) <= Date.now() || uncertain)) return;
    if (!resolve) {
      attempt.current = {
        key: crypto.randomUUID(),
        payload: { workspace_id: workspaceId, ...(projectId ? { project_id: projectId } : {}),
          prompt, aspect_ratio: ratio, quote_id: quote!.quote_id },
      };
      try {
        sessionStorage.setItem(storageKey, JSON.stringify(attempt.current));
      } catch {
        setError(new Error("Unable to preserve submission identity. Generation was not submitted."));
        attempt.current = null;
        return;
      }
    }
    const current = attempt.current;
    if (!current) return;
    const requestContext = context.current;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      const accepted = await apiRequest<GenerationJob>("/jobs/image-generation/", {
        method: "POST", headers: { "Idempotency-Key": current.key }, body: JSON.stringify(current.payload),
      });
      if (!accepted || !Number.isInteger(accepted.id) || accepted.id < 1 || ![
        "pending_provider", "queued", "processing", "completed", "failed", "canceled", "blocked_provider_not_configured",
      ].includes(accepted.status)) {
        throw new ApiError(0, { code: "invalid_response", message: "The server did not confirm an accepted job.", errors: {} });
      }
      current.job = accepted;
      sessionStorage.setItem(storageKey, JSON.stringify(current));
      if (context.current !== requestContext) return;
      setJob(accepted);
      setUncertain(false);
      setQuote(null);
    } catch (caught) {
      const rejected = caught instanceof ApiError && caught.status === 409 && caught.submission_not_accepted
        && ["quote_changed", "quote_expired"].includes(caught.code);
      if (rejected) sessionStorage.removeItem(storageKey);
      if (context.current !== requestContext) return;
      setError(caught);
      if (rejected) {
        // Only the locked, unconsumed-quote rejection can release a paid attempt.
        attempt.current = null;
        setUncertain(false);
        setQuote(null);
        if (["quote_changed", "quote_expired"].includes(caught.code)) setRevision(value => value + 1);
      } else {
        setUncertain(true);
        setQuote(null);
      }
    } finally {
      inFlight.current = false;
      if (context.current === requestContext) setBusy(false);
    }
  }

  return (
    <section aria-label="Generation" className="mt-6">
      <h2 className="text-xl font-semibold">Generate image foundation</h2>
      <label className="block">Image prompt
        <input className="block w-full border p-1" value={prompt} disabled={busy || uncertain}
          onChange={event => { setQuote(null); setPrompt(event.target.value); }} />
      </label>
      <label>Aspect ratio
        <select value={ratio} disabled={busy || uncertain} onChange={event => { setQuote(null); setRatio(event.target.value); }}>
          <option>1:1</option><option>16:9</option><option>9:16</option>
        </select>
      </label>
      {quote ? (
        <p>Estimated cost: {quote.estimated_credits} credits. {quote.parameters.model}, {quote.parameters.resolution},
          {quote.parameters.image_count} image. {quote.basis.description} Version {quote.pricing_version}.
          Expires {quote.expires_at}. This is not a guaranteed maximum charge.</p>
      ) : <p>Cost estimate unavailable: {reason} Paid generation is disabled without a current server quote.</p>}
      <button disabled={busy || !canWrite || !quote || uncertain || !prompt.trim()} onClick={() => void submit()}>
        Generate image
      </button>
      <button disabled={busy || !canWrite || uncertain || (!!job && job.asset_status !== "ready")} onClick={() => {
        if (job) {
          try { sessionStorage.removeItem(storageKey); }
          catch { setError(new Error("Unable to clear the saved successful attempt.")); return; }
          attempt.current = null;
          setJob(null);
        }
        setRevision(value => value + 1);
      }}>Refresh estimate</button>
      {uncertain && <div role="alert">
        The submission outcome is unknown. Do not generate again. Resolve the same attempt or contact an operator.
        <button disabled={busy || !canWrite || !attempt.current} onClick={() => void submit(true)}>Resolve existing attempt</button>
      </div>}
      <p>Presenter generation is unavailable until secure workspace audio and provider mapping are configured.</p>
      <p>Generated images become scene assets only after private saving is ready. This is not a cinematic motion or continuity system.</p>
      {job && <JobStatusCard key={job.id} jobId={job.id} status={job.status} message={job.error_message}
        initialJob={job} pollIntervalMs={pollIntervalMs} onAssetReady={assetReady} />}
      {error ? <ErrorAlert error={error} /> : null}
    </section>
  );
}
