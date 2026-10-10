import React, { useState } from "react";

import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { Asset, Character, Scene, SceneKind } from "../../lib/api/types";
import { assetSourceLabel } from "./asset-source";

type SceneListProps = {
  projectId: number;
  scenes: Scene[];
  assets: Asset[];
  characters?: Character[];
  canWrite?: boolean;
  selectedId?: number | null;
  onSelect?: (sceneId: number) => void;
  onAdded: (scene: Scene) => void;
};

const KINDS: SceneKind[] = ["script", "image", "video"];

export function SceneList({ projectId, scenes, assets, characters = [], canWrite = true, selectedId = null, onSelect, onAdded }: SceneListProps) {
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<SceneKind>("script");
  const [script, setScript] = useState("");
  const [assetId, setAssetId] = useState("");
  const [characterId, setCharacterId] = useState("");
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
        body: JSON.stringify({ kind, title, script_text: script, config, ...(characterId !== "" ? { character_id: Number(characterId) } : {}) }),
      });
      onAdded(scene);
      setTitle("");
      setScript("");
      setAssetId("");
      setCharacterId("");
      setDuration("5");
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Scenes" className="card">
      <h2 className="panel-title">Scenes</h2>
      {scenes.length === 0 ? (
        <p className="mt-3 rounded-lg border border-dashed border-line p-4 text-center text-sm text-muted">No scenes yet.</p>
      ) : (
        <ol className="mt-3 flex gap-3 overflow-x-auto pb-2">
          {scenes.map((scene, index) => (
            <li key={scene.id} className="shrink-0">
              <button
                type="button"
                aria-pressed={scene.id === selectedId}
                onClick={() => onSelect?.(scene.id)}
                className={`flex h-24 w-40 flex-col justify-between rounded-lg border p-3 text-left transition ${
                  scene.id === selectedId ? "border-brand bg-brand-soft" : "border-line bg-canvas hover:border-faint"
                }`}
              >
                <span className="text-xs text-faint">#{index + 1}</span>
                <span className="block truncate text-sm font-medium">{scene.title}</span>
                <span className="truncate text-xs text-muted">
                  {scene.kind}
                  {scene.character_id ? ` · ${characters.find((c) => c.id === scene.character_id)?.name ?? "character"}` : ""}
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
      {canWrite ? (
        <form onSubmit={(event) => void add(event)} className="mt-4 grid gap-4 border-t border-line pt-4 sm:grid-cols-2">
          <label className="field-label">
            Scene title
            <input required maxLength={120} className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label className="field-label">
            Scene kind
            <select className="input" value={kind} onChange={(e) => { setKind(e.target.value as SceneKind); setAssetId(""); }}>
              {KINDS.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label className="field-label sm:col-span-2">
            Script
            <textarea className="input min-h-20" value={script} onChange={(e) => setScript(e.target.value)} />
          </label>
          {characters.length > 0 && (
            <label className="field-label sm:col-span-2">
              Character
              <select className="input" value={characterId} onChange={(e) => setCharacterId(e.target.value)}>
                <option value="">None</option>
                {characters.map((character) => (
                  <option key={character.id} value={character.id}>
                    {character.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {needsAsset && (
            <label className="field-label">
              Media asset
              <select className="input" value={assetId} onChange={(e) => setAssetId(e.target.value)}>
                <option value="">Select a private {kind}…</option>
                {choices.map((asset) => (
                  <option key={asset.id} value={asset.id}>
                    {asset.name} — {assetSourceLabel(asset)}
                  </option>
                ))}
              </select>
            </label>
          )}
          {kind === "image" && (
            <label className="field-label">
              Duration (seconds, 1-120; blank uses 5)
              <input
                className="input"
                type="number"
                min={1}
                max={120}
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
              />
            </label>
          )}
          <div className="sm:col-span-2">
            <button className="btn btn-primary" type="submit" disabled={busy || title.trim() === "" || (needsAsset && assetId === "")}>
              Add scene
            </button>
          </div>
        </form>
      ) : (
        <p className="mt-3 text-sm text-muted">You have read-only access to this project.</p>
      )}
      {error ? <div className="mt-3"><ErrorAlert error={error} /></div> : null}
    </section>
  );
}
