import React, { useState } from "react";

import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { Asset } from "../../lib/api/types";

type AssetPanelProps = {
  workspaceId: number;
  assets: Asset[];
  canWrite: boolean;
  onUploaded: (asset: Asset) => void;
};

export function AssetPanel({ workspaceId, assets, canWrite, onUploaded }: AssetPanelProps) {
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function upload() {
    if (!file) {
      return;
    }
    setBusy(true);
    setError(null);
    const body = new FormData();
    body.append("workspace_id", String(workspaceId));
    body.append("file", file);
    try {
      onUploaded(await apiRequest<Asset>("/assets/", { method: "POST", body }));
      setFile(null);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Media assets" className="mt-6">
      <h2 className="text-xl font-semibold">Media assets</h2>
      {assets.length === 0 ? <p>No private assets yet.</p> : null}
      <ul className="list-disc pl-5">
        {assets.map((asset) => (
          <li key={asset.id}>
            {asset.name} <span className="text-sm text-gray-600">({asset.asset_type})</span>
          </li>
        ))}
      </ul>
      {canWrite ? (
        <div className="mt-2">
          <label className="block">
            Upload media
            <input type="file" accept="image/*,video/*" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          </label>
          <button disabled={busy || !file} onClick={() => void upload()}>
            Upload asset
          </button>
        </div>
      ) : null}
      {error ? <ErrorAlert error={error} /> : null}
    </section>
  );
}
