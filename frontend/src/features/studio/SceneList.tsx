import React, { useState } from "react";

import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { Asset, Scene, SceneKind } from "../../lib/api/types";

type SceneListProps = {
  projectId: number;
  scenes: Scene[];
  assets: Asset[];
  canWrite?: boolean;
  onAdded: (scene: Scene) => void;
};

const KINDS: SceneKind[] = ["script", "image", "video"];

export function SceneList({ projectId, scenes, assets, canWrite = true, onAdded }: SceneListProps) {
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<SceneKind>("script");
  const [script, setScript] = useState("");
  const [assetId, setAssetId] = useState("");
  const [duration, setDuration] = useState("5");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const needsAsset = kind === "image" || kind === "video";
  const choices = assets.filter((asset) => asset.asset_type === kind);

  async function add(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const config: Record<string, unknown> = {};
    if (needsAsset) {
      config.asset_id = Number(assetId);
    }
    if (kind === "image" && duration.trim() !== "") {
      config.duration_seconds = Number(duration);
    }
    try {
      const scene = await apiRequest<Scene>(`/projects/${projectId}/scenes/`, {
        method: "POST",
        body: JSON.stringify({ kind, title, script_text: script, config }),
      });
      onAdded(scene);
      setTitle("");
      setScript("");
      setAssetId("");
      setDuration("5");
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Scenes" className="mt-6">
      <h2 className="text-xl font-semibold">Scenes</h2>
      {scenes.length === 0 ? <p>No scenes yet.</p> : null}
      <ol className="list-decimal pl-5">
        {scenes.map((scene) => (
          <li key={scene.id}>
            {scene.title} <span className="text-sm text-gray-600">({scene.kind})</span>
          </li>
        ))}
      </ol>
      {canWrite ? (
        <form onSubmit={(event) => void add(event)} className="mt-3">
          <label className="block">
            Scene title
            <input required maxLength={120} className="block border p-1" value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label className="block">
            Scene kind
            <select className="block border p-1" value={kind} onChange={(e) => { setKind(e.target.value as SceneKind); setAssetId(""); }}>
              {KINDS.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            Script
            <textarea className="block w-full border p-1" value={script} onChange={(e) => setScript(e.target.value)} />
          </label>
          {needsAsset && (
            <label className="block">
              Media asset
              <select className="block border p-1" value={assetId} onChange={(e) => setAssetId(e.target.value)}>
                <option value="">Select a private {kind}…</option>
                {choices.map((asset) => (
                  <option key={asset.id} value={asset.id}>
                    {asset.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {kind === "image" && (
            <label className="block">
              Duration (seconds, 1-120; blank uses 5)
              <input
                className="block border p-1"
                type="number"
                min={1}
                max={120}
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
              />
            </label>
          )}
          <button type="submit" disabled={busy || title.trim() === "" || (needsAsset && assetId === "")}>
            Add scene
          </button>
        </form>
      ) : (
        <p className="text-sm text-gray-600">You have read-only access to this project.</p>
      )}
      {error ? <ErrorAlert error={error} /> : null}
    </section>
  );
}

