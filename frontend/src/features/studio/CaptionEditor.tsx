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
            disabled={!canWrite || busy}
            onChange={(e) => update(index, { start: Number(e.target.value) })}
          />
          <input
            aria-label={`Segment ${index + 1} end`}
            type="number"
            step="0.1"
            min={0}
            value={segment.end}
            disabled={!canWrite || busy}
            onChange={(e) => update(index, { end: Number(e.target.value) })}
          />
          <input
            aria-label={`Segment ${index + 1} text`}
            maxLength={500}
            className="flex-1 border p-1"
            value={segment.text}
            disabled={!canWrite || busy}
            onChange={(e) => update(index, { text: e.target.value })}
          />
          {canWrite ? (
            <button type="button" disabled={busy} onClick={() => removeSegment(index)}>
              Remove segment {index + 1}
            </button>
          ) : null}
        </div>
      ))}
      {canWrite ? (
        <div className="flex gap-2">
          <button type="button" disabled={busy} onClick={addSegment}>
            Add segment
          </button>
          <button type="button" disabled={busy} onClick={() => void save()}>
            Save captions
          </button>
        </div>
      ) : null}
      {validation ? (
        <p role="alert" className="text-sm text-red-800">
          {validation}
        </p>
      ) : null}
      {saved ? <p role="status">Captions saved.</p> : null}
      {error ? <ErrorAlert error={error} /> : null}
    </section>
  );
}

