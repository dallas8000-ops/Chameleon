import React, { useEffect, useRef, useState } from "react";
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
type Attempt = { key: string; payload: Record<string, unknown> };

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
  const storageKey = `generation-attempt:${userId ?? "session"}:${workspaceId}:${projectId ?? "none"}`;

  useEffect(() => {
    attempt.current = null;
    setJob(null);
    setQuote(null);
    setUncertain(false);
    try {
      const saved = sessionStorage.getItem(storageKey);
      if (saved) {
        const parsed = JSON.parse(saved) as Attempt;
        if (typeof parsed.key === "string" && parsed.payload?.quote_id) {
          attempt.current = parsed;
          setUncertain(true);
        }
      }
    } catch { /* A storage failure cannot authorize a new paid request. */ }
  }, [storageKey, sessionStatus]);

  useEffect(() => {
    const controller = new AbortController();
    setQuote(null);
    if (!canWrite || uncertain || !prompt.trim() || sessionStatus === "anonymous") {
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
  }, [workspaceId, projectId, prompt, ratio, canWrite, uncertain, revision, sessionStatus, userId]);

  useEffect(() => {
    if (!quote) return;
    const timer = setTimeout(() => {
      setQuote(null);
      setReason("Quote expired. Request a new estimate.");
    }, Math.max(0, Date.parse(quote.expires_at) - Date.now()));
    return () => clearTimeout(timer);
  }, [quote]);

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
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      const accepted = await apiRequest<GenerationJob>("/jobs/image-generation/", {
        method: "POST", headers: { "Idempotency-Key": current.key }, body: JSON.stringify(current.payload),
      });
      setJob(accepted);
      setUncertain(false);
      attempt.current = null;
      sessionStorage.removeItem(storageKey);
      setQuote(null);
    } catch (caught) {
      setError(caught);
      if (caught instanceof ApiError && caught.status > 0 && caught.status < 500
          && ![401, 403].includes(caught.status) && caught.code !== "idempotency_conflict") {
        // A rejected request has no accepted paid attempt. Requoting never auto-submits.
        attempt.current = null;
        sessionStorage.removeItem(storageKey);
        setUncertain(false);
        setQuote(null);
        if (["quote_changed", "quote_expired"].includes(caught.code)) setRevision(value => value + 1);
      } else {
        setUncertain(true);
        setQuote(null);
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
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
      <button disabled={busy || !canWrite || uncertain} onClick={() => setRevision(value => value + 1)}>Refresh estimate</button>
      {uncertain && <div role="alert">
        The submission outcome is unknown. Do not generate again. Resolve the same attempt or contact an operator.
        <button disabled={busy || !canWrite} onClick={() => void submit(true)}>Resolve existing attempt</button>
      </div>}
      <p>Presenter generation is unavailable until secure workspace audio and provider mapping are configured.</p>
      <p>Generated images become scene assets only after private saving is ready. This is not a cinematic motion or continuity system.</p>
      {job && <JobStatusCard key={job.id} jobId={job.id} status={job.status} message={job.error_message}
        initialJob={job} pollIntervalMs={pollIntervalMs} onAssetReady={onAssetReady} />}
      {error ? <ErrorAlert error={error} /> : null}
    </section>
  );
}
