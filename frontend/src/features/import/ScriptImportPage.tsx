import React, { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { AppShell } from "../../components/AppShell";
import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { ProjectFormat, ScriptImportResult, ScriptPreview } from "../../lib/api/types";
import { useSessionStore } from "../../lib/auth/session-store";

export function ScriptImportPage() {
  const status = useSessionStore((state) => state.status);
  const ensureSession = useSessionStore((state) => state.ensureSession);

  useEffect(() => {
    void ensureSession();
  }, [ensureSession]);

  if (status === "anonymous") {
    return <Navigate to="/login" replace />;
  }
  return <AppShell>{status === "authenticated" ? <ImportWorkflow /> : <p role="status" className="text-muted">Loading…</p>}</AppShell>;
}

function ImportWorkflow() {
  const workspaceId = useSessionStore((state) => state.activeWorkspaceId);
  const role = useSessionStore((state) => state.workspaces.find((w) => w.id === state.activeWorkspaceId)?.role);
  const canWrite = role === "owner" || role === "editor";
  const [script, setScript] = useState("");
  const [format, setFormat] = useState<ProjectFormat>("9:16");
  const [preview, setPreview] = useState<ScriptPreview | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [createCharacters, setCreateCharacters] = useState(true);
  const [result, setResult] = useState<ScriptImportResult | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (workspaceId === null) {
    return <p className="text-muted">You are not a member of any workspace yet.</p>;
  }

  function edit(value: string) {
    setScript(value);
    setPreview(null);
    setResult(null);
  }

  async function loadFile(file: File | undefined) {
    if (file) {
      edit(await file.text());
    }
  }

  async function runPreview() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const data = await apiRequest<ScriptPreview>("/projects/import-script/", {
        method: "POST",
        body: JSON.stringify({ workspace_id: workspaceId, script, format, dry_run: true }),
      });
      setPreview(data);
      setSelected(new Set(data.episodes.map((episode) => episode.number)));
    } catch (caught) {
      setPreview(null);
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  async function runImport() {
    setBusy(true);
    setError(null);
    try {
      setResult(
        await apiRequest<ScriptImportResult>("/projects/import-script/", {
          method: "POST",
          body: JSON.stringify({
            workspace_id: workspaceId,
            script,
            format,
            dry_run: false,
            create_characters: createCharacters,
            episodes: [...selected].sort((a, b) => a - b),
          }),
        }),
      );
      setPreview(null);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  function toggle(number: number) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(number)) {
        next.delete(number);
      } else {
        next.add(number);
      }
      return next;
    });
  }

  const newCharacters = preview?.characters.filter((character) => !character.exists) ?? [];
  return (
    <>
      <header className="mb-6">
        <h1 className="text-title">Import a script</h1>
        <p className="mt-1 text-sm text-muted">
          Paste a series script. Each episode becomes a project with one scene per line, and speakers are matched to your characters.
          Nothing is created until you confirm.
        </p>
      </header>

      <div className="card space-y-4">
        <label className="field-label">
          Script
          <textarea
            className="input min-h-64 font-mono text-xs"
            value={script}
            disabled={!canWrite || busy}
            onChange={(e) => edit(e.target.value)}
            placeholder={'### Ep 1 — "Title"\n**Hook:** …\nMARCUS (to camera): …'}
          />
        </label>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="field-label">
            Load a script file
            <input
              type="file"
              accept=".md,.txt,text/plain,text/markdown"
              disabled={!canWrite || busy}
              className="input file:mr-3 file:rounded-md file:border-0 file:bg-raised file:px-3 file:py-1 file:text-sm file:text-ink"
              onChange={(e) => {
                void loadFile(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
          </label>
          <label className="field-label">
            Project format
            <select className="input" value={format} disabled={!canWrite || busy} onChange={(e) => setFormat(e.target.value as ProjectFormat)}>
              <option value="9:16">9:16</option>
              <option value="16:9">16:9</option>
            </select>
          </label>
        </div>
        {canWrite ? (
          <button type="button" className="btn btn-primary" disabled={busy || script.trim() === ""} onClick={() => void runPreview()}>
            Preview import
          </button>
        ) : (
          <p className="text-sm text-muted">You have read-only access to this workspace.</p>
        )}
        {error ? <ErrorAlert error={error} /> : null}
      </div>

      {preview ? (
        <section aria-label="Import preview" className="mt-6 space-y-6">
          {preview.warnings.length > 0 ? (
            <div className="card border-warn/40 bg-warn-soft">
              <h2 className="panel-title text-warn">Check before importing</h2>
              <ul className="mt-2 list-disc pl-5 text-sm">
                {preview.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {preview.characters.length > 0 ? (
            <div className="card">
              <h2 className="panel-title">Characters found</h2>
              <ul className="mt-3 divide-y divide-line">
                {preview.characters.map((character) => (
                  <li key={character.name} className="flex items-start justify-between gap-3 py-2 text-sm">
                    <span className="min-w-0">
                      <span className="block font-medium">{character.name}</span>
                      <span className="block truncate text-xs text-muted">{character.role}</span>
                    </span>
                    <span className={character.exists ? "badge" : "badge badge-brand"}>{character.exists ? "Already in library" : "New"}</span>
                  </li>
                ))}
              </ul>
              {newCharacters.length > 0 ? (
                <label className="mt-3 flex items-center gap-2 text-sm">
                  <input type="checkbox" className="h-4 w-4 accent-brand" checked={createCharacters} onChange={(e) => setCreateCharacters(e.target.checked)} />
                  Create the {newCharacters.length} new characters with their prompts
                </label>
              ) : null}
            </div>
          ) : null}

          <div className="card">
            <h2 className="panel-title">Episodes</h2>
            <ul className="mt-3 space-y-2">
              {preview.episodes.map((episode) => (
                <li key={episode.number} className="rounded-lg border border-line bg-canvas p-3">
                  <label className="flex items-center gap-3 text-sm">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-brand"
                      aria-label={`Import episode ${episode.number}`}
                      checked={selected.has(episode.number)}
                      onChange={() => toggle(episode.number)}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="font-medium">Ep {episode.number}: {episode.title}</span>
                    </span>
                    <span className="badge">{episode.scene_count} scenes</span>
                    {episode.over_export_limit ? <span className="badge badge-accent">Over the 20-scene export limit</span> : null}
                  </label>
                  <details className="mt-2 text-xs text-muted">
                    <summary className="cursor-pointer">Show scenes</summary>
                    <ol className="mt-2 list-decimal space-y-1 pl-5">
                      {episode.scenes.map((scene, index) => (
                        <li key={index}>
                          {scene.title}
                          {scene.character ? <span className="text-brand"> · {scene.character}</span> : null}
                        </li>
                      ))}
                    </ol>
                  </details>
                </li>
              ))}
            </ul>
            <button type="button" className="btn btn-primary mt-4" disabled={busy || selected.size === 0} onClick={() => void runImport()}>
              Import {selected.size} {selected.size === 1 ? "episode" : "episodes"}
            </button>
          </div>
        </section>
      ) : null}

      {result ? (
        <section role="status" aria-label="Import result" className="card mt-6">
          <h2 className="panel-title">Imported {result.projects.length} {result.projects.length === 1 ? "project" : "projects"}</h2>
          {result.characters_created.length > 0 ? (
            <p className="mt-1 text-sm text-muted">New characters: {result.characters_created.join(", ")}. Add their reference images on the Characters page.</p>
          ) : null}
          <ul className="mt-3 space-y-1 text-sm">
            {result.projects.map((project) => (
              <li key={project.id}>
                <Link to={`/app/projects/${project.id}/studio`}>{project.title}</Link> <span className="text-muted">({project.scene_count} scenes)</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}
