import React, { useState } from "react";

import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { Project } from "../../lib/api/types";

type Props = {
  projectId: number;
  checked: boolean;
  canWrite: boolean;
  onChanged: (value: boolean) => void;
};

export function AiDisclosureToggle({ projectId, checked, canWrite, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function change(value: boolean) {
    setBusy(true);
    setError(null);
    try {
      const updated = await apiRequest<Project>(`/projects/${projectId}/`, { method: "PATCH", body: JSON.stringify({ ai_disclosure: value }) });
      onChanged(updated.ai_disclosure === true);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-2">
      <label className="flex items-center gap-2 text-sm text-muted">
        <input type="checkbox" className="h-4 w-4 accent-brand" checked={checked} disabled={!canWrite || busy} onChange={(e) => void change(e.target.checked)} />
        This project contains AI-generated people
      </label>
      {error ? <div className="mt-2"><ErrorAlert error={error} /></div> : null}
    </div>
  );
}
