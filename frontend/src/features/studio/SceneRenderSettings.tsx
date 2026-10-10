import React from "react";

import type { Asset } from "../../lib/api/types";

export type SceneConfig = Record<string, unknown>;

export type Overlay = { text: string; start: number; end: number; position: "top" | "center" | "bottom"; size: "small" | "medium" | "large" };

type Props = {
  kind: string;
  config: SceneConfig;
  assets: Asset[];
  disabled: boolean;
  onChange: (config: SceneConfig) => void;
};

const num = (value: unknown): string => (typeof value === "number" ? String(value) : "");
const pct = (value: unknown): string => (typeof value === "number" ? String(Math.round(value * 100)) : "");

export function overlaysOf(config: SceneConfig): Overlay[] {
  return Array.isArray(config.overlays) ? (config.overlays as Overlay[]) : [];
}

export function SceneRenderSettings({ kind, config, assets, disabled, onChange }: Props) {
  const isImage = kind === "image";
  const isVideo = kind === "video";
  const media = assets.filter((asset) => asset.asset_type === kind);
  const voices = assets.filter((asset) => asset.asset_type === "audio");
  const overlays = overlaysOf(config);
  const hasVoice = typeof config.audio_asset_id === "number";

  function set(key: string, value: unknown) {
    const next = { ...config };
    if (value === undefined) {
      delete next[key];
    } else {
      next[key] = value;
    }
    onChange(next);
  }
  const setNumber = (key: string, text: string) => set(key, text.trim() === "" ? undefined : Number(text));
  const setPercent = (key: string, text: string) => set(key, text.trim() === "" ? undefined : Number(text) / 100);
  const setOverlay = (index: number, patch: Partial<Overlay>) =>
    set("overlays", overlays.map((overlay, i) => (i === index ? { ...overlay, ...patch } : overlay)));

  return (
    <div className="space-y-5 sm:col-span-2">
      {isImage || isVideo ? (
        <fieldset className="grid gap-4 sm:grid-cols-2" disabled={disabled}>
          <legend className="panel-title mb-2">Media</legend>
          <label className="field-label sm:col-span-2">
            Media for this scene
            <select
              className="input"
              value={typeof config.asset_id === "number" ? String(config.asset_id) : ""}
              onChange={(e) => set("asset_id", e.target.value === "" ? undefined : Number(e.target.value))}
            >
              <option value="">Select a {kind}…</option>
              {media.map((asset) => (
                <option key={asset.id} value={asset.id}>
                  {asset.name}
                </option>
              ))}
            </select>
          </label>
          {isImage ? (
            <>
              <label className="field-label">
                Show for (seconds)
                <input className="input" type="number" min={1} max={120} step="any" value={num(config.duration_seconds)} onChange={(e) => setNumber("duration_seconds", e.target.value)} />
              </label>
              <label className="flex items-center gap-2 self-end pb-2 text-sm">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-brand"
                  checked={config.fit_to_audio === true}
                  disabled={!hasVoice}
                  onChange={(e) => set("fit_to_audio", e.target.checked ? true : undefined)}
                />
                Match the voice track length
              </label>
            </>
          ) : (
            <>
              <label className="field-label">
                Trim start (seconds)
                <input className="input" type="number" min={0} step="any" value={num(config.trim_start)} onChange={(e) => setNumber("trim_start", e.target.value)} />
              </label>
              <label className="field-label">
                Trim end (seconds)
                <input className="input" type="number" min={0} step="any" value={num(config.trim_end)} onChange={(e) => setNumber("trim_end", e.target.value)} />
              </label>
            </>
          )}
        </fieldset>
      ) : null}

      {isImage || isVideo ? (
        <fieldset className="grid gap-4 sm:grid-cols-3" disabled={disabled}>
          <legend className="panel-title mb-2">Voice track</legend>
          <label className="field-label sm:col-span-3">
            Voice track audio
            <select
              className="input"
              value={hasVoice ? String(config.audio_asset_id) : ""}
              onChange={(e) => {
                const next = { ...config };
                if (e.target.value === "") {
                  delete next.audio_asset_id;
                  delete next.fit_to_audio;
                } else {
                  next.audio_asset_id = Number(e.target.value);
                }
                onChange(next);
              }}
            >
              <option value="">None</option>
              {voices.map((asset) => (
                <option key={asset.id} value={asset.id}>
                  {asset.name}
                </option>
              ))}
            </select>
          </label>
          {hasVoice ? (
            <>
              <label className="field-label">
                Voice volume (%)
                <input className="input" type="number" min={0} max={200} placeholder="100" value={pct(config.audio_volume)} onChange={(e) => setPercent("audio_volume", e.target.value)} />
              </label>
              <label className="field-label">
                Voice starts at (seconds)
                <input className="input" type="number" min={0} step="any" value={num(config.audio_start)} onChange={(e) => setNumber("audio_start", e.target.value)} />
              </label>
              {isVideo ? (
                <label className="field-label">
                  Original sound (%)
                  <input className="input" type="number" min={0} max={200} placeholder="100" value={pct(config.clip_volume)} onChange={(e) => setPercent("clip_volume", e.target.value)} />
                </label>
              ) : null}
            </>
          ) : null}
          {voices.length === 0 ? <p className="text-xs text-muted sm:col-span-3">Upload a WAV, MP3 or M4A file in Media assets to use it here.</p> : null}
        </fieldset>
      ) : null}

      <fieldset className="space-y-3" disabled={disabled}>
        <legend className="panel-title mb-2">Text on screen</legend>
        {overlays.map((overlay, index) => (
          <div key={index} className="grid gap-3 rounded-lg border border-line bg-canvas p-3 sm:grid-cols-6">
            <input
              aria-label={`Overlay ${index + 1} text`}
              className="input mt-0 sm:col-span-6"
              maxLength={140}
              placeholder="Text shown on the video"
              value={overlay.text}
              onChange={(e) => setOverlay(index, { text: e.target.value })}
            />
            <input aria-label={`Overlay ${index + 1} start`} className="input mt-0 sm:col-span-1" type="number" min={0} step="any" value={overlay.start} onChange={(e) => setOverlay(index, { start: Number(e.target.value) })} />
            <input aria-label={`Overlay ${index + 1} end`} className="input mt-0 sm:col-span-1" type="number" min={0} step="any" value={overlay.end} onChange={(e) => setOverlay(index, { end: Number(e.target.value) })} />
            <select aria-label={`Overlay ${index + 1} position`} className="input mt-0 sm:col-span-2" value={overlay.position} onChange={(e) => setOverlay(index, { position: e.target.value as Overlay["position"] })}>
              <option value="top">Top</option>
              <option value="center">Center</option>
              <option value="bottom">Bottom</option>
            </select>
            <select aria-label={`Overlay ${index + 1} size`} className="input mt-0 sm:col-span-1" value={overlay.size} onChange={(e) => setOverlay(index, { size: e.target.value as Overlay["size"] })}>
              <option value="small">Small</option>
              <option value="medium">Medium</option>
              <option value="large">Large</option>
            </select>
            <button type="button" className="btn btn-ghost px-2 py-1 text-xs sm:col-span-1" onClick={() => set("overlays", overlays.filter((_, i) => i !== index).length ? overlays.filter((_, i) => i !== index) : undefined)}>
              Remove overlay {index + 1}
            </button>
          </div>
        ))}
        <p className="text-xs text-muted">Start and end are seconds from the start of this scene.</p>
        <button
          type="button"
          className="btn"
          disabled={overlays.length >= 5}
          onClick={() => set("overlays", [...overlays, { text: "", start: 0, end: 2, position: "center", size: "medium" }])}
        >
          Add text overlay
        </button>
      </fieldset>
    </div>
  );
}
