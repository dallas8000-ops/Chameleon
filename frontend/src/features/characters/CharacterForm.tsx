import React, { useState } from "react";

import { AssetImage } from "../../components/AssetImage";
import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { Asset, Character, CharacterInput } from "../../lib/api/types";

type CharacterFormProps = {
  workspaceId: number;
  assets: Asset[];
  character: Character | null;
  canWrite: boolean;
  onSaved: (character: Character) => void;
  onDeleted: (id: number) => void;
  onUploaded: (asset: Asset) => void;
  onNew: () => void;
};

export function CharacterForm({ workspaceId, assets, character, canWrite, onSaved, onDeleted, onUploaded, onNew }: CharacterFormProps) {
  const [name, setName] = useState(character?.name ?? "");
  const [role, setRole] = useState(character?.role ?? "");
  const [description, setDescription] = useState(character?.description ?? "");
  const [facePrompt, setFacePrompt] = useState(character?.face_prompt ?? "");
  const [negativePrompt, setNegativePrompt] = useState(character?.negative_prompt ?? "");
  const [voiceNotes, setVoiceNotes] = useState(character?.voice_notes ?? "");
  const [referenceId, setReferenceId] = useState<number | null>(character?.reference_asset_id ?? null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const images = assets.filter((asset) => asset.asset_type === "image");

  async function uploadReference(file: File | undefined) {
    if (!file) {
      return;
    }
    setBusy(true);
    setError(null);
    const body = new FormData();
    body.append("workspace_id", String(workspaceId));
    body.append("file", file);
    try {
      const asset = await apiRequest<Asset>("/assets/", { method: "POST", body });
      onUploaded(asset);
      setReferenceId(asset.id);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const input: CharacterInput = {
      name: name.trim(),
      role,
      description,
      face_prompt: facePrompt,
      negative_prompt: negativePrompt,
      voice_notes: voiceNotes,
      reference_asset_id: referenceId,
    };
    try {
      const saved = character
        ? await apiRequest<Character>(`/characters/${character.id}/`, { method: "PATCH", body: JSON.stringify(input) })
        : await apiRequest<Character>("/characters/", { method: "POST", body: JSON.stringify({ workspace_id: workspaceId, ...input }) });
      onSaved(saved);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!character) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await apiRequest(`/characters/${character.id}/`, { method: "DELETE" });
      onDeleted(character.id);
    } catch (caught) {
      setError(caught);
      setBusy(false);
    }
  }

  const disabled = !canWrite || busy;
  return (
    <form onSubmit={(event) => void save(event)} className="card h-fit space-y-4" aria-label={character ? "Edit character" : "New character"}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="panel-title">{character ? "Edit character" : "New character"}</h2>
        {character ? (
          <button type="button" className="btn btn-ghost px-2 py-1 text-xs" onClick={onNew}>
            Start a new character
          </button>
        ) : null}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="field-label">
          Name
          <input required maxLength={120} className="input" value={name} disabled={disabled} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field-label">
          Role
          <input maxLength={120} className="input" value={role} disabled={disabled} onChange={(e) => setRole(e.target.value)} />
        </label>
      </div>
      <label className="field-label">
        Description
        <textarea maxLength={5000} className="input min-h-16" value={description} disabled={disabled} onChange={(e) => setDescription(e.target.value)} />
      </label>
      <label className="field-label">
        Face prompt
        <textarea maxLength={5000} className="input min-h-24" value={facePrompt} disabled={disabled} onChange={(e) => setFacePrompt(e.target.value)} />
      </label>
      <label className="field-label">
        Negative prompt
        <textarea maxLength={2000} className="input min-h-16" value={negativePrompt} disabled={disabled} onChange={(e) => setNegativePrompt(e.target.value)} />
      </label>
      <label className="field-label">
        Voice notes
        <textarea maxLength={2000} className="input min-h-16" value={voiceNotes} disabled={disabled} onChange={(e) => setVoiceNotes(e.target.value)} />
      </label>
      <div className="space-y-3 rounded-lg border border-line bg-canvas p-3">
        <div className="flex items-start gap-3">
          {referenceId !== null ? (
            <AssetImage assetId={referenceId} className="h-24 w-20 shrink-0 rounded-md border border-line" />
          ) : (
            <div className="grid h-24 w-20 shrink-0 place-items-center rounded-md border border-dashed border-line text-xs text-faint">No image</div>
          )}
          <div className="min-w-0 flex-1 space-y-3">
            <label className="field-label">
              Reference image
              <select
                className="input"
                value={referenceId ?? ""}
                disabled={disabled}
                onChange={(e) => setReferenceId(e.target.value === "" ? null : Number(e.target.value))}
              >
                <option value="">None</option>
                {images.map((asset) => (
                  <option key={asset.id} value={asset.id}>
                    {asset.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-label">
              Upload reference image
              <input
                type="file"
                accept="image/*"
                disabled={disabled}
                className="input file:mr-3 file:rounded-md file:border-0 file:bg-raised file:px-3 file:py-1 file:text-sm file:text-ink"
                onChange={(e) => {
                  void uploadReference(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
            </label>
          </div>
        </div>
      </div>
      {canWrite ? (
        <div className="flex flex-wrap items-center gap-2">
          <button type="submit" className="btn btn-primary" disabled={busy || name.trim() === ""}>
            {character ? "Save character" : "Create character"}
          </button>
          {character ? (
            confirmDelete ? (
              <>
                <button type="button" className="btn btn-danger" disabled={busy} onClick={() => void remove()}>
                  Confirm delete
                </button>
                <button type="button" className="btn btn-ghost" onClick={() => setConfirmDelete(false)}>
                  Keep character
                </button>
              </>
            ) : (
              <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => setConfirmDelete(true)}>
                Delete character
              </button>
            )
          ) : null}
        </div>
      ) : (
        <p className="text-sm text-muted">You have read-only access to this workspace.</p>
      )}
      {error ? <ErrorAlert error={error} /> : null}
    </form>
  );
}
