# Chameleon rebuild plan

Goal: one app that does what HeyGen and Magic Hour do together, without using either service, with a
better design and better performance. Generation runs on open-source models on a serverless GPU
service (RunPod or Modal). Railway has no GPUs, so the backend calls the GPU worker over an API.

## Phase 1: Clean-out and design foundation (in progress)

- [x] Remove Magic Hour and the provider-shaped job pipeline (`jobs` and `providers` apps, webhook, quoting, usage ledger). A migration drops the old tables.
- [x] Remove the competitor research and the old specs and plans.
- [x] Tailwind design tokens, dark theme and a layout shell (sidebar, top bar, responsive grid).
- [x] Rebuild the landing page, auth screens, dashboard and studio (scene preview frame, scene timeline, asset library, captions, export). The studio's "Generate media" panel says plainly that generation is not available yet.
- Done when the new UI has been seen live in the browser and approved (awaiting approval).

Kept: accounts and workspaces, projects and scenes, uploads, captions, FFmpeg export, Railway setup.

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
