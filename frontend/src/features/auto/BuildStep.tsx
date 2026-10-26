import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { AssetImage } from "../../components/AssetImage";
import { ErrorAlert } from "../../components/ErrorAlert";
import { apiRequest } from "../../lib/api/client";
import type { Character, GenerationCapabilities, GenerationJob, ProjectDetail, Scene } from "../../lib/api/types";
import { useCharacters } from "../studio/use-characters";

export const POLL_MS = 3000;
const STYLE = "cinematic film still, natural light, sharp focus, high detail";
const NEGATIVE = "text, caption, watermark, logo, blurry, deformed, extra fingers, low quality";
const FINISHED: GenerationJob["status"][] = ["completed", "failed", "canceled"];

type Props = {
  project: ProjectDetail;
  onSceneUpdated: (scene: Scene) => void;
  onDone: () => void;
};

type Progress = { status: GenerationJob["status"] | "starting"; error?: string };

export const hasMedia = (scene: Scene) => typeof scene.config.asset_id === "number";

/** Builds the picture description from the character's face prompt, the scene's place and its line. */
export function picturePrompt(scene: Scene, character: Character | undefined) {
  const location = typeof scene.config.location === "string" ? scene.config.location : "";
  const prompt = [character?.face_prompt, location, scene.script_text, STYLE]
    .map((part) => (part ?? "").trim())
    .filter(Boolean)
    .join(". ")
    .slice(0, 2000);
  const negative = [character?.negative_prompt?.trim(), NEGATIVE].filter(Boolean).join(", ").slice(0, 2000);
  return { prompt, negative_prompt: negative };
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Step 4: make a picture on the GPU for every scene that has no picture or clip yet. */
export function BuildStep({ project, onSceneUpdated, onDone }: Props) {
  const characters = useCharacters(project.workspace_id);
  const [capabilities, setCapabilities] = useState<GenerationCapabilities | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [progress, setProgress] = useState<Record<number, Progress>>({});
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const stopped = useRef(false);

  useEffect(() => {
    stopped.current = false;
    apiRequest<GenerationCapabilities>(`/generation/capabilities/?workspace_id=${project.workspace_id}`).then(setCapabilities, setLoadError);
    return () => {
      stopped.current = true;
    };
  }, [project.workspace_id]);

  const missing = project.scenes.filter((scene) => !hasMedia(scene));
  const pictures = capabilities?.capabilities.find((item) => item.capability === "text_to_image");
  const canGenerate = pictures?.available === true;

  async function makeOne(scene: Scene) {
    const character = characters.characters.find((item) => item.id === scene.character_id);
    setProgress((current) => ({ ...current, [scene.id]: { status: "starting" } }));
    let job = await apiRequest<GenerationJob>("/generation/jobs/", {
      method: "POST",
      body: JSON.stringify({
        workspace_id: project.workspace_id,
        capability: "text_to_image",
        params: { ...picturePrompt(scene, character), size: project.format === "16:9" ? "landscape" : "portrait" },
        project_id: project.id,
        scene_id: scene.id,
      }),
    });
    while (!FINISHED.includes(job.status)) {
      setProgress((current) => ({ ...current, [scene.id]: { status: job.status } }));
      await wait(POLL_MS);
      if (stopped.current) {
        return false;
      }
      job = await apiRequest<GenerationJob>(`/generation/jobs/${job.id}/`);
    }
    if (job.status !== "completed" || job.result_asset_id === null) {
      setProgress((current) => ({ ...current, [scene.id]: { status: job.status, error: job.error_message || "The picture was not made." } }));
      return false;
    }
    const updated = await apiRequest<Scene>(`/scenes/${scene.id}/`, {
      method: "PATCH",
      body: JSON.stringify({ kind: "image", config: { ...scene.config, asset_id: job.result_asset_id } }),
    });
    setProgress((current) => ({ ...current, [scene.id]: { status: "completed" } }));
    onSceneUpdated(updated);
    return true;
  }

  async function makeAll() {
    setRunning(true);
    setError(null);
    try {
      // One at a time: a single graphics card runs one model job at once.
      for (const scene of missing) {
        if (stopped.current || !(await makeOne(scene))) {
          break;
        }
      }
    } catch (caught) {
      setError(caught);
    } finally {
      if (!stopped.current) {
        setRunning(false);
      }
    }
  }

  return (
    <section className="space-y-4" aria-labelledby="build-heading">
      <div className="card space-y-2">
        <h2 id="build-heading" className="text-heading">
          Step 4: Build
        </h2>
        <p className="text-sm text-muted">
          Every scene needs a picture or clip. The app makes a picture for each scene that is missing one, using the character's face
          description and the scene's line.
        </p>
      </div>
      {loadError ? <ErrorAlert error={loadError} /> : null}
      {capabilities && !canGenerate ? (
        <div className="card border-warn/40 bg-warn-soft space-y-2 text-sm">
          <p className="font-medium text-warn">Picture making is not connected.</p>
          <p>
            Start the GPU worker with <code>run-gpu.ps1</code>, then reload this page. You can also add your own pictures or clips in the
            studio.
          </p>
          {capabilities.missing.length > 0 ? <p className="text-muted">Missing settings: {capabilities.missing.join(", ")}</p> : null}
        </div>
      ) : null}

      <ol className="space-y-2">
        {project.scenes.map((scene, index) => {
          const state = progress[scene.id];
          return (
            <li key={scene.id} className="card flex items-center gap-3 py-3">
              {hasMedia(scene) ? (
                <AssetImage assetId={Number(scene.config.asset_id)} className="h-16 w-12 shrink-0 rounded border border-line" />
              ) : (
                <div className="h-16 w-12 shrink-0 rounded border border-dashed border-line" aria-hidden="true" />
              )}
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">
                  {index + 1}. {scene.title}
                </span>
                <span className={`block text-xs ${state?.error ? "text-danger" : "text-muted"}`}>
                  {sceneStatus(scene, state)}
                </span>
              </span>
            </li>
          );
        })}
      </ol>
      {error ? <ErrorAlert error={error} /> : null}
      {missing.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn btn-primary" disabled={!canGenerate || running} onClick={() => void makeAll()}>
            {running ? "Making pictures…" : `Make ${missing.length} ${missing.length === 1 ? "picture" : "pictures"}`}
          </button>
          <Link to={`/app/projects/${project.id}/studio`} className="btn btn-ghost">
            Add my own in the studio
          </Link>
        </div>
      ) : (
        <button type="button" className="btn btn-primary w-full" onClick={onDone}>
          Continue to export
        </button>
      )}
    </section>
  );
}

function sceneStatus(scene: Scene, state: Progress | undefined) {
  if (state?.error) {
    return `Failed: ${state.error}`;
  }
  if (hasMedia(scene)) {
    return "Ready";
  }
  switch (state?.status) {
    case "starting":
    case "queued":
      return "Starting…";
    case "submitted":
      return "Waiting for the graphics card…";
    case "running":
      return "Making the picture…";
    default:
      return "Needs a picture";
  }
}
