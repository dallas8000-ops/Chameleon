import React, { useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import { AppShell } from "../../components/AppShell";
import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { ExportRecord } from "../../lib/api/types";
import { useProjectDetail } from "../studio/use-project-detail";

export function ExportPage() {
  const { id } = useParams();
  const { sessionStatus, state, canWrite, retry } = useProjectDetail(id);
  const [trackId, setTrackId] = useState("");
  const [burn, setBurn] = useState(true);
  const [burnLabel, setBurnLabel] = useState(false);
  const [copied, setCopied] = useState(false);
  const [record, setRecord] = useState<ExportRecord | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function run(path: string, init: RequestInit) {
    setBusy(true);
    setError(null);
    try {
      setRecord(await apiRequest<ExportRecord>(path, init));
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  if (sessionStatus === "anonymous") {
    return <Navigate to="/login" replace />;
  }
  if (state.status !== "ready") {
    return (
      <AppShell projectId={id}>
        {state.status === "error" ? <ErrorAlert error={state.error} onRetry={retry} /> : <p role="status" className="text-muted">Loading export…</p>}
      </AppShell>
    );
  }
  const captions = state.project.captions;
  const needsTrack = captions.length > 1;
  const scenes = state.project.scenes;
  const missingMedia = scenes.filter((scene) => typeof scene.config.asset_id !== "number");
  const aiDisclosure = state.project.ai_disclosure === true;
  const bioLine = "AI-generated character";

  async function copyBio() {
    try {
      await navigator.clipboard.writeText(bioLine);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <AppShell projectId={id}>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-title">Export</h1>
          <p className="mt-1 text-sm text-muted">Render this project to an MP4 with optional burned-in captions.</p>
        </div>
        <Link to={`/app/projects/${id}/studio`} className="btn btn-ghost">
          Back to studio
        </Link>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        {scenes.length === 0 || missingMedia.length > 0 ? (
          <section aria-label="Export readiness" className="card border-warn/40 bg-warn-soft lg:col-span-2">
            <h2 className="panel-title text-warn">This project is not ready to export</h2>
            <p className="mt-1 text-sm text-muted">
              Export assembles uploaded images and videos. Every scene needs one attached, and script-only scenes cannot be
              rendered yet because media generation is not available.
            </p>
            {scenes.length === 0 ? (
              <p className="mt-2 text-sm">The project has no scenes.</p>
            ) : (
              <ul className="mt-2 list-disc pl-5 text-sm">
                {missingMedia.map((scene) => (
                  <li key={scene.id}>
                    Scene {scenes.indexOf(scene) + 1} ({scene.kind}) has no media attached
                  </li>
                ))}
              </ul>
            )}
            <Link to={`/app/projects/${id}/studio`} className="btn mt-3">
              Fix in studio
            </Link>
          </section>
        ) : null}
        {aiDisclosure ? (
          <section aria-label="Posting checklist" className="card space-y-3 lg:col-span-2">
            <h2 className="panel-title">Before you post: AI disclosure</h2>
            <p className="text-sm text-muted">
              YouTube, TikTok, Instagram and Facebook all require labelling realistic AI-generated people. Unlabelled videos can be
              removed or lose monetization.
            </p>
            <ul className="list-disc space-y-1 pl-5 text-sm">
              <li>Turn on each platform's AI-generated content label when you upload.</li>
              <li>Add the line below to your bio or description.</li>
              <li>Only use faces and names you own or have permission to use.</li>
            </ul>
            <div className="flex flex-wrap items-center gap-2">
              <code className="rounded-md border border-line bg-canvas px-2 py-1 text-sm">{bioLine}</code>
              <button type="button" className="btn" onClick={() => void copyBio()}>
                Copy bio line
              </button>
              {copied ? <span role="status" className="text-sm text-brand">Copied.</span> : null}
            </div>
          </section>
        ) : null}
        <section className="card space-y-4" aria-label="Export settings">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="h-4 w-4 accent-brand" checked={burn} onChange={(event) => setBurn(event.target.checked)} /> Burn in captions
          </label>
          {aiDisclosure && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="h-4 w-4 accent-brand" checked={burnLabel} onChange={(event) => setBurnLabel(event.target.checked)} /> Add a small AI-generated label to the video
            </label>
          )}
          {needsTrack && (
            <label className="field-label">
              Caption track
              <select className="input" value={trackId} onChange={(event) => setTrackId(event.target.value)}>
                <option value="">Select a caption track…</option>
                {captions.map((track) => (
                  <option key={track.id} value={track.id}>
                    {track.language}
                  </option>
                ))}
              </select>
            </label>
          )}
          {!canWrite && <p className="text-sm text-warn">You have read-only access; exports cannot be queued.</p>}
          <button
            className="btn btn-primary"
            disabled={busy || !canWrite || (needsTrack && trackId === "")}
            onClick={() =>
              void run(`/projects/${encodeURIComponent(id ?? "")}/exports/`, {
                method: "POST",
                body: JSON.stringify({
                  burn_captions: burn,
                  ...(aiDisclosure && burnLabel ? { burn_ai_label: true } : {}),
                  ...(needsTrack ? { caption_track_id: Number(trackId) } : {}),
                }),
              })
            }
          >
            Queue export
          </button>
          {error ? <ErrorAlert error={error} /> : null}
        </section>

        {record ? (
          <section role="status" className="card space-y-3">
            <h2 className="panel-title">Export status: {record.status}</h2>
            {record.error_message ? <p className="text-sm text-danger">{record.error_message}</p> : null}
            <div className="flex flex-wrap gap-2">
              <button className="btn" disabled={busy} onClick={() => void run(`/exports/${record.id}/`, {})}>
                Refresh status
              </button>
              {record.video_available ? <a className="btn btn-primary" href={`/api/exports/${record.id}/video/`}>Download video</a> : null}
              {record.subtitles_available ? <a className="btn" href={`/api/exports/${record.id}/subtitles/`}>Download subtitles</a> : null}
            </div>
          </section>
        ) : null}
      </div>
    </AppShell>
  );
}
