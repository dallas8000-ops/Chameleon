import React, { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";

import { AppShell } from "../../components/AppShell";
import { AssetImage } from "../../components/AssetImage";
import { ErrorAlert } from "../../components/ErrorAlert";
import { useSessionStore } from "../../lib/auth/session-store";
import { useAssets } from "../studio/use-assets";
import { useCharacters } from "../studio/use-characters";
import { CharacterForm } from "./CharacterForm";

export function CharactersPage() {
  const status = useSessionStore((state) => state.status);
  const ensureSession = useSessionStore((state) => state.ensureSession);

  useEffect(() => {
    void ensureSession();
  }, [ensureSession]);

  if (status === "anonymous") {
    return <Navigate to="/login" replace />;
  }
  return (
    <AppShell wide>
      {status === "authenticated" ? <CharacterLibrary /> : <p role="status" className="text-muted">Loading characters…</p>}
    </AppShell>
  );
}

function CharacterLibrary() {
  const workspaceId = useSessionStore((state) => state.activeWorkspaceId);
  const role = useSessionStore((state) => state.workspaces.find((w) => w.id === state.activeWorkspaceId)?.role);
  const canWrite = role === "owner" || role === "editor";
  const characters = useCharacters(workspaceId);
  const assets = useAssets(workspaceId ?? 0);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selected = characters.characters.find((character) => character.id === selectedId) ?? null;

  if (workspaceId === null) {
    return <p className="text-muted">You are not a member of any workspace yet.</p>;
  }
  return (
    <>
      <header className="mb-6">
        <h1 className="text-title">Characters</h1>
        <p className="mt-1 text-sm text-muted">
          Keep one master reference image and prompt per character, then assign them to scenes so faces stay consistent.
        </p>
      </header>
      {characters.error ? <ErrorAlert error={characters.error} onRetry={characters.retry} /> : null}
      <div className="grid gap-6 lg:grid-cols-[1fr_28rem]">
        <section aria-labelledby="character-list-heading">
          <h2 id="character-list-heading" className="mb-4 text-heading">
            Library
          </h2>
          {characters.characters.length === 0 ? (
            <p className="card text-center text-muted">No characters yet.</p>
          ) : (
            <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {characters.characters.map((character) => (
                <li key={character.id}>
                  <button
                    type="button"
                    aria-pressed={character.id === selectedId}
                    onClick={() => setSelectedId(character.id)}
                    className={`card w-full text-left transition ${character.id === selectedId ? "border-brand" : "hover:border-faint"}`}
                  >
                    {character.reference_asset_id !== null ? (
                      <AssetImage assetId={character.reference_asset_id} className="mb-3 aspect-[3/4] w-full rounded-lg border border-line" />
                    ) : (
                      <div className="mb-3 grid aspect-[3/4] w-full place-items-center rounded-lg border border-dashed border-line text-xs text-faint">
                        No reference image
                      </div>
                    )}
                    <span className="block truncate font-medium">{character.name}</span>
                    {character.role ? <span className="block truncate text-xs text-muted">{character.role}</span> : null}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
        <CharacterForm
          key={selected?.id ?? "new"}
          workspaceId={workspaceId}
          assets={assets.assets}
          character={selected}
          canWrite={canWrite}
          onSaved={(saved) => {
            characters.upsert(saved);
            setSelectedId(saved.id);
          }}
          onDeleted={(id) => {
            characters.remove(id);
            setSelectedId(null);
          }}
          onUploaded={assets.add}
          onNew={() => setSelectedId(null)}
        />
      </div>
    </>
  );
}
