import React, { useState } from "react";

import { AssetImage } from "../../components/AssetImage";
import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { Asset, Character, ProjectDetail } from "../../lib/api/types";
import { useCharacters } from "../studio/use-characters";

type Props = {
  project: ProjectDetail;
  onDone: () => void;
};

/** Step 3: for each character in this project's scenes, ask only for what is missing. */
export function CharactersStep({ project, onDone }: Props) {
  const characters = useCharacters(project.workspace_id);
  const castIds = new Set(project.scenes.map((scene) => scene.character_id).filter((id): id is number => typeof id === "number"));
  const cast = characters.characters.filter((character) => castIds.has(character.id));
  const unlinked = [
    ...new Set(
      project.scenes
        .filter((scene) => scene.character_id == null && typeof scene.config.speaker === "string" && scene.config.speaker !== "")
        .map((scene) => String(scene.config.speaker)),
    ),
  ];
  const missingImages = cast.filter((character) => character.reference_asset_id === null).length;
  const loaded = characters.characters.length > 0 || castIds.size === 0;

  return (
    <section className="space-y-4" aria-labelledby="characters-heading">
      <div className="card space-y-2">
        <h2 id="characters-heading" className="text-heading">
          Step 3: Characters
        </h2>
        <p className="text-sm text-muted">
          Each character needs one reference image so their face stays the same in every scene. Voice notes are optional.
        </p>
      </div>
      {characters.error ? <ErrorAlert error={characters.error} onRetry={characters.retry} /> : null}
      {!loaded && !characters.error ? <p role="status" className="text-muted">Loading characters…</p> : null}
      {loaded && cast.length === 0 ? <p className="card text-muted">No characters speak in this project, so there is nothing to add.</p> : null}
      <ul className="space-y-3">
        {cast.map((character) => (
          <li key={character.id}>
            <CastMember character={character} onSaved={characters.upsert} />
          </li>
        ))}
      </ul>
      {unlinked.length > 0 ? (
        <p className="card border-warn/40 bg-warn-soft text-sm">
          These speakers are not linked to a character: {unlinked.join(", ")}. You can link them in the studio later.
        </p>
      ) : null}
      <button type="button" className="btn btn-primary w-full" disabled={!loaded || missingImages > 0} onClick={onDone}>
        {missingImages > 0 ? `Add ${missingImages} more reference ${missingImages === 1 ? "image" : "images"} to continue` : "Continue to build"}
      </button>
    </section>
  );
}

function CastMember({ character, onSaved }: { character: Character; onSaved: (character: Character) => void }) {
  const [voiceNotes, setVoiceNotes] = useState(character.voice_notes);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function patch(input: Partial<Character>) {
    const saved = await apiRequest<Character>(`/characters/${character.id}/`, { method: "PATCH", body: JSON.stringify(input) });
    onSaved(saved);
  }

  async function uploadAs(file: File | undefined, field: "reference_asset_id" | "voice_sample_asset_id") {
    if (!file) {
      return;
    }
    setBusy(true);
    setError(null);
    const body = new FormData();
    body.append("workspace_id", String(character.workspace_id));
    body.append("file", file);
    try {
      const asset = await apiRequest<Asset>("/assets/", { method: "POST", body });
      await patch({ [field]: asset.id });
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  async function saveVoiceNotes() {
    setBusy(true);
    setError(null);
    try {
      await patch({ voice_notes: voiceNotes });
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  const hasImage = character.reference_asset_id !== null;
  return (
    <div className="card flex flex-col gap-4 sm:flex-row">
      {hasImage ? (
        <AssetImage assetId={character.reference_asset_id!} className="h-32 w-24 shrink-0 rounded-md border border-line" />
      ) : (
        <div className="grid h-32 w-24 shrink-0 place-items-center rounded-md border border-dashed border-warn text-center text-xs text-warn">
          Image needed
        </div>
      )}
      <div className="min-w-0 flex-1 space-y-3">
        <p>
          <span className="font-medium">{character.name}</span>
          {character.role ? <span className="text-sm text-muted"> · {character.role}</span> : null}
        </p>
        <label className="field-label">
          {hasImage ? `Replace reference image for ${character.name}` : `Reference image for ${character.name}`}
          <input
            type="file"
            accept="image/*"
            disabled={busy}
            className="input file:mr-3 file:rounded-md file:border-0 file:bg-raised file:px-3 file:py-1 file:text-sm file:text-ink"
            onChange={(e) => {
              void uploadAs(e.target.files?.[0], "reference_asset_id");
              e.target.value = "";
            }}
          />
        </label>
        <label className="field-label">
          {character.voice_sample_asset_id ? `Replace voice sample for ${character.name}` : `Voice sample for ${character.name} (optional)`}
          <span className="block text-xs font-normal text-muted">
            {character.voice_sample_asset_id
              ? "Voice ready: this character's lines will be spoken in this voice."
              : "10 to 30 seconds of clear speech (WAV, MP3 or M4A). Only use a voice you own or have permission to use."}
          </span>
          <input
            type="file"
            accept="audio/*,.wav,.mp3,.m4a"
            disabled={busy}
            className="input file:mr-3 file:rounded-md file:border-0 file:bg-raised file:px-3 file:py-1 file:text-sm file:text-ink"
            onChange={(e) => {
              void uploadAs(e.target.files?.[0], "voice_sample_asset_id");
              e.target.value = "";
            }}
          />
        </label>
        <label className="field-label">
          Voice notes for {character.name} (optional)
          <textarea
            maxLength={2000}
            className="input min-h-16"
            value={voiceNotes}
            disabled={busy}
            placeholder="For example: warm, low voice, slow and calm"
            onChange={(e) => setVoiceNotes(e.target.value)}
          />
        </label>
        {voiceNotes !== character.voice_notes ? (
          <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => void saveVoiceNotes()}>
            Save voice notes
          </button>
        ) : null}
        {error ? <ErrorAlert error={error} /> : null}
      </div>
    </div>
  );
}
