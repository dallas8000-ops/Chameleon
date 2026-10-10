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
  const [validation, setValidation] = useState<string | null>(null);

  function update(index: number, patch: Partial<CaptionSegment>) {
    setSaved(false);
    setValidation(null);
    setSegments(segments.map((segment, i) => (i === index ? { ...segment, ...patch } : segment)));
  }

  function addSegment() {
    const start = segments.length ? segments[segments.length - 1].end : 0;
    setSaved(false);
    setValidation(null);
    setSegments([...segments, { start, end: Math.round((start + 2) * 1000) / 1000, text: "" }]);
  }

  function removeSegment(index: number) {
    setSaved(false);
    setValidation(null);
    setSegments(segments.filter((_, i) => i !== index));
  }

  function validate(): string | null {
    for (let i = 0; i < segments.length; i += 1) {
      const { start, end, text } = segments[i];
      const n = i + 1;
      if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0) {
        return `Segment ${n} start and end must be non-negative numbers.`;
      }
      if (end <= start) {
        return `Segment ${n} end must be after its start.`;
      }
      if (text.trim() === "") {
        return `Segment ${n} text is required.`;
      }
      if (i > 0 && start < segments[i - 1].end) {
        return `Segment ${n} must not overlap segment ${i}.`;
      }
    }
    return null;
  }

  async function save() {
    const problem = validate();
    setValidation(problem);
    setSaved(false);
    if (problem) {
      return;
    }
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
    <section aria-label="Captions" className="card">
      <h2 className="panel-title">Captions ({caption.language})</h2>
      {segments.length === 0 ? <p className="mt-3 text-sm text-muted">No caption segments.</p> : null}
      <div className="mt-3 space-y-3">
        {segments.map((segment, index) => (
          <div key={index} className="rounded-lg border border-line bg-canvas p-3">
            <div className="grid grid-cols-2 gap-2">
              <input
                aria-label={`Segment ${index + 1} start`}
                className="input mt-0"
                type="number"
                step="0.1"
                min={0}
                value={segment.start}
                disabled={!canWrite || busy}
                onChange={(e) => update(index, { start: Number(e.target.value) })}
              />
              <input
                aria-label={`Segment ${index + 1} end`}
                className="input mt-0"
                type="number"
                step="0.1"
                min={0}
                value={segment.end}
                disabled={!canWrite || busy}
                onChange={(e) => update(index, { end: Number(e.target.value) })}
              />
            </div>
            <input
              aria-label={`Segment ${index + 1} text`}
              maxLength={500}
              className="input"
              value={segment.text}
              disabled={!canWrite || busy}
              onChange={(e) => update(index, { text: e.target.value })}
            />
            {canWrite ? (
              <button type="button" className="btn btn-ghost mt-2 px-2 py-1 text-xs" disabled={busy} onClick={() => removeSegment(index)}>
                Remove segment {index + 1}
              </button>
            ) : null}
          </div>
        ))}
      </div>
      {canWrite ? (
        <div className="mt-4 flex gap-2">
          <button type="button" className="btn" disabled={busy} onClick={addSegment}>
            Add segment
          </button>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void save()}>
            Save captions
          </button>
        </div>
      ) : null}
      {validation ? (
        <p role="alert" className="mt-3 text-sm text-danger">
          {validation}
        </p>
      ) : null}
      {saved ? <p role="status" className="mt-3 text-sm text-brand">Captions saved.</p> : null}
      {error ? <div className="mt-3"><ErrorAlert error={error} /></div> : null}
    </section>
  );
}
