import React from "react";

const PLANNED = [
  "Text-to-image, image editing, upscaling and background removal",
  "Text-to-speech, voice cloning and transcription",
  "Talking photos and script-to-presenter video",
  "Image-to-video and text-to-video",
  "Translation and dubbing with lip-sync",
];

export function GenerationRoadmap() {
  return (
    <section aria-label="Generation roadmap" className="card">
      <div className="flex items-center justify-between gap-2">
        <h2 className="panel-title">Generate media</h2>
        <span className="badge badge-accent">Not available yet</span>
      </div>
      <p className="mt-2 text-sm text-muted">
        Generation on open-source models is planned and nothing here creates media yet. Planned next:
      </p>
      <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted">
        {PLANNED.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}
