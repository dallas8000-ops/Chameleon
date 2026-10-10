import React from "react";

import type { Asset, ProjectFormat, Scene } from "../../lib/api/types";

type ScenePreviewProps = {
  format: string;
  scene: Scene | null;
  sceneNumber: number;
  assets: Asset[];
};

/** A framed view of the selected scene's details. It is not a media player: playback comes after export. */
export function ScenePreview({ format, scene, sceneNumber, assets }: ScenePreviewProps) {
  const portrait = (format as ProjectFormat) === "9:16";
  const assetId = scene && typeof scene.config.asset_id === "number" ? scene.config.asset_id : null;
  const hasAsset = assetId !== null && assets.some((asset) => asset.id === assetId);
  const duration = scene && typeof scene.config.duration_seconds === "number" ? scene.config.duration_seconds : null;

  return (
    <section aria-label="Scene preview" className="card flex flex-col items-center">
      <div className="mb-3 flex w-full items-center justify-between">
        <h2 className="panel-title">Preview</h2>
        <span className="badge">{format}</span>
      </div>
      <div
        className={`relative grid place-items-center overflow-hidden rounded-xl border border-line bg-canvas ${
          portrait ? "aspect-[9/16] h-[26rem] max-h-[60vh]" : "aspect-video w-full max-w-2xl"
        }`}
        style={{ backgroundImage: "linear-gradient(160deg, rgb(52 211 153 / 0.08), transparent 55%, rgb(167 139 250 / 0.1))" }}
      >
        {scene ? (
          <div className="max-w-[85%] text-center">
            <p className="text-xs uppercase tracking-widest text-faint">
              Scene {sceneNumber} · {scene.kind}
            </p>
            {scene.script_text ? <p className="mt-3 text-sm leading-relaxed text-ink">{scene.script_text}</p> : null}
            <p className="mt-3 text-xs text-muted">
              {hasAsset ? "Media attached" : scene.kind === "script" ? "Script only" : "No media attached"}
              {duration !== null ? ` · ${duration}s` : ""}
            </p>
          </div>
        ) : (
          <p className="px-6 text-center text-sm text-muted">Add a scene to see it here.</p>
        )}
      </div>
      <p className="mt-3 text-center text-xs text-faint">Rendered video is available from Export.</p>
    </section>
  );
}
