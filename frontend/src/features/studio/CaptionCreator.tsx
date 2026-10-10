import React, { useState } from "react";

import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { CaptionTrack } from "../../lib/api/types";

type CaptionCreatorProps = {
  projectId: number;
  onCreated: (caption: CaptionTrack) => void;
};

export function CaptionCreator({ projectId, onCreated }: CaptionCreatorProps) {
  const [language, setLanguage] = useState("en");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      onCreated(
        await apiRequest<CaptionTrack>(`/projects/${projectId}/captions/`, {
          method: "POST",
          body: JSON.stringify({ language: language.trim(), segments: [] }),
        }),
      );
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="New caption track" className="card space-y-3">
      <label className="field-label">
        Caption language
        <input className="input" value={language} onChange={(e) => setLanguage(e.target.value)} />
      </label>
      <button className="btn w-full" disabled={busy || language.trim() === ""} onClick={() => void create()}>
        Create caption track
      </button>
      {error ? <ErrorAlert error={error} /> : null}
    </section>
  );
}
