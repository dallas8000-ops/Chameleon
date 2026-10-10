import React, { useState } from "react";

import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { Asset } from "../../lib/api/types";
import { assetSourceLabel } from "./asset-source";

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
    <section aria-label="Media assets" className="card">
      <h2 className="panel-title">Media assets</h2>
      <p className="mt-1 text-sm text-muted">Upload images or videos to use in scenes. Uploads stay private to this workspace.</p>
      {assets.length === 0 ? <p className="mt-4 rounded-lg border border-dashed border-line p-4 text-center text-sm text-muted">No private assets yet.</p> : null}
      <ul className="mt-4 space-y-2">
        {assets.map((asset) => (
          <li key={asset.id} className="flex items-center gap-3 rounded-lg border border-line bg-canvas px-3 py-2">
            <span aria-hidden="true" className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-raised text-xs text-muted">
              {asset.asset_type === "video" ? "▶" : "▢"}
            </span>
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium">{asset.name}</span>
              <span className="block text-xs text-muted">
                {asset.asset_type} · {assetSourceLabel(asset)}
              </span>
            </span>
          </li>
        ))}
      </ul>
      {canWrite ? (
        <div className="mt-4 space-y-3 border-t border-line pt-4">
          <label className="field-label">
            Upload media
            <input
              type="file"
              accept="image/*,video/*"
              className="input file:mr-3 file:rounded-md file:border-0 file:bg-raised file:px-3 file:py-1 file:text-sm file:text-ink"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <button className="btn btn-primary w-full" disabled={busy || !file} onClick={() => void upload()}>
            Upload asset
          </button>
        </div>
      ) : null}
      {error ? <div className="mt-3"><ErrorAlert error={error} /></div> : null}
    </section>
  );
}
