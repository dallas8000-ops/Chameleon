import React, { useState } from "react";

import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { ProjectDetail, ScriptImportResult, ScriptPreview } from "../../lib/api/types";

type Props = {
  project: ProjectDetail;
  /** Called once the scenes are saved, so the page can reload the project and open the next step. */
  onDone: () => void;
};

/** Step 2: paste the script, check the scenes it found, then add one episode's scenes to this project. */
export function ScriptStep({ project, onDone }: Props) {
  const [script, setScript] = useState("");
  const [preview, setPreview] = useState<ScriptPreview | null>(null);
  const [episode, setEpisode] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  function edit(value: string) {
    setScript(value);
    setPreview(null);
  }

  async function loadFile(file: File | undefined) {
    if (file) {
      edit(await file.text());
    }
  }

  async function runPreview() {
    setBusy(true);
    setError(null);
    try {
      const data = await apiRequest<ScriptPreview>("/projects/import-script/", {
        method: "POST",
        body: JSON.stringify({ workspace_id: project.workspace_id, script, format: project.format, dry_run: true }),
      });
      setPreview(data);
      setEpisode(data.episodes[0]?.number ?? null);
    } catch (caught) {
      setPreview(null);
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  async function addScenes() {
    setBusy(true);
    setError(null);
    try {
      await apiRequest<ScriptImportResult>("/projects/import-script/", {
        method: "POST",
        body: JSON.stringify({
          workspace_id: project.workspace_id,
          script,
          format: project.format,
          dry_run: false,
          create_characters: true,
          episodes: [episode],
          project_id: project.id,
        }),
      });
      onDone();
    } catch (caught) {
      setError(caught);
      setBusy(false);
    }
  }

  const chosen = preview?.episodes.find((item) => item.number === episode) ?? null;
  return (
    <section className="space-y-6" aria-labelledby="script-heading">
      <div className="card space-y-4">
        <h2 id="script-heading" className="text-heading">
          Step 2: Script
        </h2>
        <label className="field-label">
          Paste your script
          <textarea
            className="input min-h-64 font-mono text-xs"
            value={script}
            disabled={busy}
            onChange={(e) => edit(e.target.value)}
            placeholder={'### Ep 1 — "Title"\n**Hook:** …\nMARCUS (to camera): …'}
          />
        </label>
        <label className="field-label">
          Or load a script file
          <input
            type="file"
            accept=".md,.txt,text/plain,text/markdown"
            disabled={busy}
            className="input file:mr-3 file:rounded-md file:border-0 file:bg-raised file:px-3 file:py-1 file:text-sm file:text-ink"
            onChange={(e) => {
              void loadFile(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
        </label>
        <button type="button" className="btn btn-primary" disabled={busy || script.trim() === ""} onClick={() => void runPreview()}>
          Find scenes
        </button>
        {error ? <ErrorAlert error={error} /> : null}
      </div>

      {preview ? (
        <div className="card space-y-4" aria-label="Scenes found">
          {preview.warnings.length > 0 ? (
            <ul className="list-disc space-y-1 rounded-lg border border-warn/40 bg-warn-soft p-3 pl-8 text-sm">
              {preview.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}
          {preview.episodes.length > 1 ? (
            <fieldset className="space-y-2">
              <legend className="field-label">This script has {preview.episodes.length} episodes. Which one is this video?</legend>
              {preview.episodes.map((item) => (
                <label key={item.number} className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="episode"
                    className="h-4 w-4 accent-brand"
                    checked={episode === item.number}
                    onChange={() => setEpisode(item.number)}
                  />
                  Ep {item.number}: {item.title} ({item.scene_count} scenes)
                </label>
              ))}
            </fieldset>
          ) : null}
          {chosen ? (
            <>
              <h3 className="panel-title">
                Ep {chosen.number}: {chosen.title} · {chosen.scene_count} scenes
              </h3>
              <ol className="list-decimal space-y-1 pl-5 text-sm">
                {chosen.scenes.map((scene, index) => (
                  <li key={index}>
                    {scene.title}
                    {scene.character ? <span className="text-brand"> · {scene.character}</span> : null}
                  </li>
                ))}
              </ol>
              {chosen.over_export_limit ? <p className="text-sm text-warn">Over the 20-scene export limit.</p> : null}
              <button type="button" className="btn btn-primary w-full" disabled={busy} onClick={() => void addScenes()}>
                Add {chosen.scene_count} {chosen.scene_count === 1 ? "scene" : "scenes"} and continue
              </button>
            </>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
