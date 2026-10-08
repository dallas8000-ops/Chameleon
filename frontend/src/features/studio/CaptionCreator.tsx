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
    <section aria-label="New caption track" className="mt-6">
      <label className="block">
        Caption language
        <input className="block border p-1" value={language} onChange={(e) => setLanguage(e.target.value)} />
      </label>
      <button disabled={busy || language.trim() === ""} onClick={() => void create()}>
        Create caption track
      </button>
      {error ? <ErrorAlert error={error} /> : null}
    </section>
  );
}
