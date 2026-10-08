import React, { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { ExportRecord } from "../../lib/api/types";

export function ExportPage() {
  const { id } = useParams();
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

  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="text-3xl font-semibold">Export</h1>
      <Link to={`/app/projects/${id}/studio`}>Back to studio</Link>
      <label className="mt-4 block">
        <input type="checkbox" checked={burn} onChange={(event) => setBurn(event.target.checked)} /> Burn in captions
      </label>
      <button
        disabled={busy}
        onClick={() =>
          void run(`/projects/${encodeURIComponent(id ?? "")}/exports/`, {
            method: "POST",
            body: JSON.stringify({ burn_captions: burn }),
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
