import React, { useState } from "react";

import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { Character, Scene } from "../../lib/api/types";

type SceneDetailsProps = {
  scene: Scene;
  index: number;
  total: number;
  characters: Character[];
  canWrite: boolean;
  onUpdated: (scene: Scene) => void;
  onMoved: (sceneId: number, newIndex: number) => void;
  onDeleted: (sceneId: number) => void;
};

export function SceneDetails({ scene, index, total, characters, canWrite, onUpdated, onMoved, onDeleted }: SceneDetailsProps) {
  const [title, setTitle] = useState(scene.title);
  const [script, setScript] = useState(scene.script_text);
  const [characterId, setCharacterId] = useState(scene.character_id ? String(scene.character_id) : "");
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  const save = (event: React.FormEvent) => {
    event.preventDefault();
    setSaved(false);
    void run(async () => {
      const updated = await apiRequest<Scene>(`/scenes/${scene.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ title: title.trim(), script_text: script, character_id: characterId === "" ? null : Number(characterId) }),
      });
      onUpdated(updated);
      setSaved(true);
    });
  };

  const move = (target: number) =>
    void run(async () => {
      await apiRequest<Scene>(`/scenes/${scene.id}/`, { method: "PATCH", body: JSON.stringify({ order_index: target }) });
      onMoved(scene.id, target);
    });

  const remove = () =>
    void run(async () => {
      await apiRequest(`/scenes/${scene.id}/`, { method: "DELETE" });
      onDeleted(scene.id);
    });

  return (
    <section aria-label="Scene details" className="card">
      <h2 className="panel-title">Scene {index + 1} details</h2>
      {canWrite ? (
        <form onSubmit={save} className="mt-3 grid gap-4 sm:grid-cols-2">
          <label className="field-label">
            Rename this scene
            <input required maxLength={120} className="input" value={title} disabled={busy} onChange={(e) => { setTitle(e.target.value); setSaved(false); }} />
          </label>
          <label className="field-label">
            Cast member for this scene
            <select className="input" value={characterId} disabled={busy} onChange={(e) => { setCharacterId(e.target.value); setSaved(false); }}>
              <option value="">None</option>
              {characters.map((character) => (
                <option key={character.id} value={character.id}>
                  {character.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field-label sm:col-span-2">
            Text for this scene
            <textarea className="input min-h-20" value={script} disabled={busy} onChange={(e) => { setScript(e.target.value); setSaved(false); }} />
          </label>
          <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
            <button type="submit" className="btn btn-primary" disabled={busy || title.trim() === ""}>
              Save scene
            </button>
            <button type="button" className="btn" disabled={busy || index === 0} onClick={() => move(index - 1)}>
              Move earlier
            </button>
            <button type="button" className="btn" disabled={busy || index >= total - 1} onClick={() => move(index + 1)}>
              Move later
            </button>
            {confirmDelete ? (
              <>
                <button type="button" className="btn btn-danger" disabled={busy} onClick={remove}>
                  Confirm delete scene
                </button>
                <button type="button" className="btn btn-ghost" onClick={() => setConfirmDelete(false)}>
                  Keep scene
                </button>
              </>
            ) : (
              <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => setConfirmDelete(true)}>
                Delete scene
              </button>
            )}
            {saved ? <span role="status" className="text-sm text-brand">Scene saved.</span> : null}
          </div>
        </form>
      ) : (
        <p className="mt-3 text-sm text-muted">You have read-only access to this project.</p>
      )}
      {error ? <div className="mt-3"><ErrorAlert error={error} /></div> : null}
    </section>
  );
}
