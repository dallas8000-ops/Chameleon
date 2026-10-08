import React, { useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { ExportRecord } from "../../lib/api/types";
import { useProjectDetail } from "../studio/use-project-detail";

export function ExportPage() {
  const { id } = useParams();
  const { sessionStatus, state, canWrite, retry } = useProjectDetail(id);
  const [trackId, setTrackId] = useState("");
  const [burn, setBurn] = useState(true);
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
      <main className="mx-auto max-w-3xl p-6">
        {state.status === "error" ? <ErrorAlert error={state.error} onRetry={retry} /> : <p role="status">Loading export…</p>}
      </main>
    );
  }
  const captions = state.project.captions;
  const needsTrack = captions.length > 1;

  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="text-3xl font-semibold">Export</h1>
      <Link to={`/app/projects/${id}/studio`}>Back to studio</Link>
      <label className="mt-4 block">
        <input type="checkbox" checked={burn} onChange={(event) => setBurn(event.target.checked)} /> Burn in captions
      </label>
      {needsTrack && (
        <label className="mt-2 block">
          Caption track
          <select className="block border p-1" value={trackId} onChange={(event) => setTrackId(event.target.value)}>
            <option value="">Select a caption track…</option>
            {captions.map((track) => (
              <option key={track.id} value={track.id}>
                {track.language}
              </option>
            ))}
          </select>
        </label>
      )}
      {!canWrite && <p className="text-sm text-gray-600">You have read-only access; exports cannot be queued.</p>}
      <button
        disabled={busy || !canWrite || (needsTrack && trackId === "")}
        onClick={() =>
          void run(`/projects/${encodeURIComponent(id ?? "")}/exports/`, {
            method: "POST",
            body: JSON.stringify({ burn_captions: burn, ...(needsTrack ? { caption_track_id: Number(trackId) } : {}) }),
          })
        }
      >
        Queue export
      </button>
      {record ? (
        <section role="status" className="mt-4">
          <h2 className="font-medium">Export status: {record.status}</h2>
          {record.error_message ? <p>{record.error_message}</p> : null}
          <button disabled={busy} onClick={() => void run(`/exports/${record.id}/`, {})}>
            Refresh status
          </button>
          {record.video_available ? <a href={`/api/exports/${record.id}/video/`}>Download video</a> : null}
          {record.subtitles_available ? <a href={`/api/exports/${record.id}/subtitles/`}>Download subtitles</a> : null}
        </section>
      ) : null}
      {error ? <ErrorAlert error={error} /> : null}
    </main>
  );
}

