import React, { useState } from "react";

import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { CaptionSegment, CaptionTrack } from "../../lib/api/types";

type CaptionEditorProps = {
  caption: CaptionTrack;
  canWrite?: boolean;
  onSaved: (caption: CaptionTrack) => void;
};

export function CaptionEditor({ caption, canWrite = true, onSaved }: CaptionEditorProps) {
  const [segments, setSegments] = useState<CaptionSegment[]>(caption.segments);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  function update(index: number, patch: Partial<CaptionSegment>) {
    setSaved(false);
    setSegments(segments.map((segment, i) => (i === index ? { ...segment, ...patch } : segment)));
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const updated = await apiRequest<CaptionTrack>(`/captions/${caption.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ segments }),
      });
      onSaved(updated);
      setSaved(true);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Captions" className="mt-6">
      <h2 className="text-xl font-semibold">Captions ({caption.language})</h2>
      {segments.length === 0 ? <p>No caption segments.</p> : null}
      {segments.map((segment, index) => (
        <div key={index} className="mb-2 flex gap-2">
          <input
            aria-label={`Segment ${index + 1} start`}
            type="number"
            step="0.1"
            min={0}
            value={segment.start}
            disabled={!canWrite}
            onChange={(e) => update(index, { start: Number(e.target.value) })}
          />
          <input
            aria-label={`Segment ${index + 1} end`}
            type="number"
            step="0.1"
            min={0}
            value={segment.end}
            disabled={!canWrite}
            onChange={(e) => update(index, { end: Number(e.target.value) })}
          />
          <input
            aria-label={`Segment ${index + 1} text`}
            maxLength={500}
            className="flex-1 border p-1"
            value={segment.text}
            disabled={!canWrite}
            onChange={(e) => update(index, { text: e.target.value })}
          />
        </div>
      ))}
      {canWrite ? (
        <button disabled={busy} onClick={() => void save()}>
          Save captions
        </button>
      ) : null}
      {saved ? <p role="status">Captions saved.</p> : null}
      {error ? <ErrorAlert error={error} /> : null}
    </section>
  );
}
