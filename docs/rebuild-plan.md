# Chameleon rebuild plan

Goal: one app that does what HeyGen and Magic Hour do together, without using either service, with a
better design and better performance. Generation runs on open-source models on a serverless GPU
service (RunPod or Modal). Railway has no GPUs, so the backend calls the GPU worker over an API.

## Phase 1: Clean-out and design foundation (done, merged in PR #2)

- [x] Remove Magic Hour and the provider-shaped job pipeline (`jobs` and `providers` apps, webhook, quoting, usage ledger). A migration drops the old tables.
- [x] Remove the competitor research and the old specs and plans.
- [x] Tailwind design tokens, dark theme and a layout shell (sidebar, top bar, responsive grid).
- [x] Rebuild the landing page, auth screens, dashboard and studio (scene preview frame, scene timeline, asset library, captions, export). The studio's "Generate media" panel says plainly that generation is not available yet.
- Done: the new UI was reviewed live in the browser and approved.

Kept: accounts and workspaces, projects and scenes, uploads, captions, FFmpeg export, Railway setup.

## Phase 1b: Script-to-timeline tools (approved 2026-10-10, no GPU needed)

Goal: build Episode 1 of the "Muzungu? I'm Black!" series by hand from its script and shot list, using uploaded media. Nothing here generates media.

Delivered as three PRs, in this order:

1. **Characters, asset previews and scene editing** (in progress)
   - [ ] Character library: name, role, face prompt, negative prompt, voice notes, master reference image; Characters page; assign a character to a scene.
   - [ ] Authorized asset content endpoint (workspace members only) used for thumbnails and a real preview frame.
   - [ ] Scene reorder, delete and edit.
2. **Script import**
   - [ ] Paste a series script, preview episodes and scenes, then create one project per episode (or the whole season). Deterministic parser, no AI. Dialogue speakers map to characters. Warn above the 20-scene export limit.
3. **Export features**
   - [ ] Trim video clips and set image durations.
   - [ ] Timed text overlays (hook, end card) drawn through the subtitle path, with a bundled open-licence font.
   - [ ] Audio assets and a voice track per scene, mixed with the clip's own sound.
   - [ ] AI-generated-people project setting, export checklist and copy-ready bio text.

Acceptance test: the 9-shot Episode 1 list built in the UI with stand-in clips and exported. Checks: 1080x1920 H.264 + AAC, total length equals the sum of trimmed shots, hook text and end card visible in pulled frames, a voice track audible over shot 6, and a second user cannot read any of it. Each PR is also walked through live in the browser before merging.

Not in 1b: text-to-image, voices, talking presenters, image-to-video, a project-wide sound bed and colour filter (Phases 3 and 4).

Private character test images live in `local-fixtures/` (git-ignored) and are never committed.

## Phase 2: Inference service

- Separate GPU worker on RunPod or Modal, called only from the backend. Keys only in Railway environment variables.
- New `generation` app: job queue with progress, retries, cost per run and honest failure states.
- Generated files saved to private storage, then added to the project as scenes.
- Done when a test job round-trips from the studio to the GPU and back.

## Phase 3: Generation features (each tested end to end before the next)

| Order | Feature | Model families to benchmark |
| --- | --- | --- |
| 1 | Text-to-image, editing, upscale, background removal | FLUX or SDXL, Real-ESRGAN, BiRefNet |
| 2 | Text-to-speech, voice cloning, transcription | Kokoro or XTTS, Whisper |
| 3 | Talking photo and script-to-presenter video | LivePortrait, MuseTalk or SadTalker |
| 4 | Image-to-video and text-to-video | Wan 2.x or similar |
| 5 | Translation and dubbing with lip-sync | Whisper, an LLM, then 2 and 3 |

## Phase 4: Polish and performance

Streaming previews, caching, lazy loading, mobile layout, accessibility, recorded speed benchmarks and
Playwright tests for every flow. Sample outputs are shown before any quality claims.

## Rules

- Original UI and copy. No HeyGen or Magic Hour branding, assets or code.
- No fake output: unavailable features say so plainly.
- Verify each phase in the live app before moving on.
