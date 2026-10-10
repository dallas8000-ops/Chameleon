import React from "react";
import { Link } from "react-router-dom";

import { Logo } from "../components/Logo";

const FEATURES = [
  {
    title: "Scenes and timeline",
    body: "Build a project from ordered scenes, each with its own script, image or video.",
    status: "Available",
  },
  {
    title: "Captions",
    body: "Write and edit timed caption tracks per language and burn them into the export.",
    status: "Available",
  },
  {
    title: "Private media library",
    body: "Upload images and videos to your workspace. Files stay private and are served only to members.",
    status: "Available",
  },
  {
    title: "MP4 export",
    body: "Assemble scenes into a vertical or horizontal MP4 with subtitles, rendered by FFmpeg.",
    status: "Available",
  },
  {
    title: "Image generation",
    body: "Text-to-image, editing, upscaling and background removal on open-source models.",
    status: "Planned",
  },
  {
    title: "Presenters and voice",
    body: "Talking presenters from a script, voiceover, translation and dubbing.",
    status: "Planned",
  },
];

export default function Home() {
  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5 sm:px-6">
        <Logo />
        <nav aria-label="Account" className="flex items-center gap-2">
          <Link to="/login" className="btn btn-ghost">
            Sign in
          </Link>
          <Link to="/register" className="btn btn-primary">
            Get started
          </Link>
        </nav>
      </header>

      <main>
        <section className="mx-auto max-w-6xl px-4 pb-16 pt-14 text-center sm:px-6 sm:pt-24">
          <p className="badge badge-brand mx-auto mb-6">One studio for video, images and voice</p>
          <h1 className="mx-auto max-w-4xl text-4xl font-bold leading-[1.05] tracking-tight sm:text-display">
            <span className="gradient-text">Chameleon</span> turns a script into a finished video
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-muted">
            Plan scenes, add your media and captions, and export a finished MP4 from one workspace. Generated images,
            presenters and voice are being built on open-source models and are not available yet.
          </p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Link to="/register" className="btn btn-primary px-5 py-2.5 text-base shadow-glow">
              Create your workspace
            </Link>
          </div>
        </section>

        <section aria-labelledby="features-heading" className="mx-auto max-w-6xl px-4 pb-24 sm:px-6">
          <h2 id="features-heading" className="mb-6 text-title">
            What works today and what is next
          </h2>
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((feature) => (
              <li key={feature.title} className="card">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <h3 className="panel-title">{feature.title}</h3>
                  <span className={feature.status === "Available" ? "badge badge-brand" : "badge badge-accent"}>
                    {feature.status}
                  </span>
                </div>
                <p className="text-sm leading-relaxed text-muted">{feature.body}</p>
              </li>
            ))}
          </ul>
        </section>
      </main>

      <footer className="border-t border-line py-6 text-center text-xs text-faint">
        Chameleon is under active development.
      </footer>
    </div>
  );
}
