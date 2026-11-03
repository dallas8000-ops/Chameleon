import React, { useEffect, useRef, useState } from "react";

import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { ExportRecord, ProjectDetail } from "../../lib/api/types";
import { POLL_MS } from "./BuildStep";

const BIO_LINE = "AI-generated character";
const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Step 5: confirm the posting checklist, then render the video and offer the download. */
export function ExportStep({ project }: { project: ProjectDetail }) {
  const aiPeople = project.ai_disclosure === true;
  const hasCaptions = project.captions.length > 0;
  const [burnCaptions, setBurnCaptions] = useState(true);
  const [burnLabel, setBurnLabel] = useState(aiPeople);
  const [confirmed, setConfirmed] = useState(!aiPeople);
  const [record, setRecord] = useState<ExportRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const stopped = useRef(false);

  useEffect(() => {
    stopped.current = false;
    return () => {
      stopped.current = true;
    };
  }, []);

  async function render() {
    setBusy(true);
    setError(null);
    try {
      let current = await apiRequest<ExportRecord>(`/projects/${project.id}/exports/`, {
        method: "POST",
        body: JSON.stringify({
          burn_captions: hasCaptions && burnCaptions,
          ...(aiPeople && burnLabel ? { burn_ai_label: true } : {}),
          ...(project.captions.length > 1 ? { caption_track_id: project.captions[0].id } : {}),
        }),
      });
      setRecord(current);
      while (current.status === "queued" || current.status === "processing") {
        await wait(POLL_MS);
        if (stopped.current) {
          return;
        }
        current = await apiRequest<ExportRecord>(`/exports/${current.id}/`);
        setRecord(current);
      }
    } catch (caught) {
      setError(caught);
    } finally {
      if (!stopped.current) {
        setBusy(false);
      }
    }
  }

  return (
    <section className="space-y-4" aria-labelledby="export-heading">
      <div className="card space-y-3">
        <h2 id="export-heading" className="text-heading">
          Step 5: Export
        </h2>
        <p className="text-sm text-muted">
          All {project.scenes.length} {project.scenes.length === 1 ? "scene has" : "scenes have"} a picture or clip. The app joins them into one MP4.
        </p>
        {hasCaptions ? (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="h-4 w-4 accent-brand" checked={burnCaptions} onChange={(e) => setBurnCaptions(e.target.checked)} />
            Show captions on the video
          </label>
        ) : null}
      </div>

      {aiPeople ? (
        <div className="card space-y-3" aria-label="Posting checklist">
          <h3 className="panel-title">Before you post: AI disclosure</h3>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            <li>Turn on each platform's AI-generated content label when you upload.</li>
            <li>
              Add <code className="rounded border border-line bg-canvas px-1">{BIO_LINE}</code> to your bio or description.
            </li>
            <li>Only use faces and names you own or have permission to use.</li>
          </ul>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="h-4 w-4 accent-brand" checked={burnLabel} onChange={(e) => setBurnLabel(e.target.checked)} />
            Add a small AI-generated label to the video
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="h-4 w-4 accent-brand" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
            I will label this video as AI-generated when I post it
          </label>
        </div>
      ) : null}

      <button type="button" className="btn btn-primary w-full" disabled={busy || !confirmed} onClick={() => void render()}>
        {busy ? "Making the video…" : record?.status === "completed" ? "Make the video again" : "Make the video"}
      </button>
      {error ? <ErrorAlert error={error} /> : null}

      {record ? (
        <div role="status" className="card space-y-3">
          <p className="panel-title">
            {record.status === "completed"
              ? "Your video is ready"
              : record.status === "failed"
                ? "The video could not be made"
                : "Making the video…"}
          </p>
          {record.error_message ? <p className="text-sm text-danger">{record.error_message}</p> : null}
          <div className="flex flex-wrap gap-2">
            {record.video_available ? (
              <a className="btn btn-primary" href={`/api/exports/${record.id}/video/`}>
                Download video
              </a>
            ) : null}
            {record.subtitles_available ? (
              <a className="btn" href={`/api/exports/${record.id}/subtitles/`}>
                Download subtitles
              </a>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
