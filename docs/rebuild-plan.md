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

1. **Characters, asset previews and scene editing** (built, awaiting review)
   - [x] Character library: name, role, face prompt, negative prompt, voice notes, master reference image; Characters page; assign a character to a scene.
   - [x] Authorized asset content endpoint (workspace members only) used for thumbnails and a real preview frame (images; video playback comes later).
   - [x] Scene delete, edit (title, text, character) and reorder (move earlier or later).
2. **Script import** (built, awaiting review)
   - [x] Paste a series script, preview episodes and scenes, then create one project per episode (or the whole season). Deterministic parser, no AI. Dialogue speakers map to characters. Warn above the 20-scene export limit.
   - [x] Also reads the character bible and "Character reference:" blocks to create characters with face prompt, outfit, role and negative prompts. Existing characters are never overwritten.
3. **Export features** (built, awaiting review)
   - [x] Trim video clips and set image durations (images can also match a voice track's length).
   - [x] Timed text overlays (hook, end card) drawn through libass, with DejaVu Sans installed in the Docker image. Text is stripped of override codes and never placed in the FFmpeg command line.
   - [x] Audio assets (WAV, MP3, M4A) and a voice track per scene, delayed and mixed with the clip's own sound.
   - [x] AI-generated-people project setting, export checklist, copy-ready bio text, and an optional small burned-in label.

Acceptance test: the 9-shot Episode 1 list built in the UI with stand-in clips and exported. Checks: 1080x1920 H.264 + AAC, total length equals the sum of trimmed shots, hook text and end card visible in pulled frames, a voice track audible over shot 6, and a second user cannot read any of it. Each PR is also walked through live in the browser before merging.

Not in 1b: text-to-image, voices, talking presenters, image-to-video, a project-wide sound bed and colour filter (Phases 3 and 4).

Private character test images live in `local-fixtures/` (git-ignored) and are never committed.

## Phase 2: Inference service (in progress)

Design decisions:
- **RunPod Serverless, one endpoint, one worker image** (`worker/`). The worker routes on `input.capability`. Endpoints scale to zero, so idle time costs nothing.
- **Django `generation` app** owns jobs. A job is submitted to RunPod by a Celery task, polled until it ends, and its status, run time and queue delay are recorded so credit use is visible.
- **Results come back by upload, not through RunPod's response.** RunPod caps response size (about 10 MB), and clips are bigger. The backend gives the worker a one-time, signed, expiring upload URL for that job. The worker PUTs the file to it, Django sniffs the type, stores it privately and adds it to the library as an asset marked as generated. No separate object storage is needed.
- **Credit protection:** a cap on active jobs per workspace, execution and queue time limits sent with every job, and a clear "not configured" state when keys are missing. Nothing is ever faked.
- **Secrets** only in Railway environment variables: `RUNPOD_API_KEY`, `RUNPOD_ENDPOINT_ID`, `GENERATION_PUBLIC_URL`.
- **Phase 2 ships one capability, `diagnostic`:** the worker reports the GPU model and memory and returns a test image through the full path. It proves the round trip before any real model is added.
- **Model licences:** every Phase 3 model is checked for commercial-use terms and recorded in `docs/models.md` before it is used.

Build order: (a) backend app, API, tasks, signed upload, tests; (b) worker image and handler, tested locally against a fake backend; (c) studio panel and deployment checks; (d) RunPod setup guide.

Untested until credits exist (smoke test list): the worker image on a real RunPod GPU, RunPod's real response shapes, cold-start time, and the upload from RunPod to Railway.

Done when a diagnostic job round-trips from the studio to the GPU and back.

## Phase 3: Generation features (each tested end to end before the next)

| Order | Feature | Model families to benchmark |
| --- | --- | --- |
| 1 | Text-to-image, editing, upscale, background removal | FLUX or SDXL, Real-ESRGAN, BiRefNet |
| 2 | Text-to-speech, voice cloning, transcription | Kokoro or XTTS, Whisper |
| 3 | Talking photo and script-to-presenter video | LivePortrait, MuseTalk or SadTalker |
| 4 | Image-to-video and text-to-video | Wan 2.x or similar |
| 5 | Translation and dubbing with lip-sync | Whisper, an LLM, then 2 and 3 |

## Automatic mode (approved 2026-10-25)

Goal: the app asks for what it needs, one step at a time, then builds the video by itself. It sits
alongside the studio (new route `/app/auto`); the studio stays for hand editing.

Order the app asks in:

1. **Basics** (built): title, format, and whether it shows AI-generated people (no default; the user must answer).
2. **Script** (built): paste the script; the existing deterministic parser splits it into scenes, and one episode's scenes are added to this project (`project_id` on script import; refused if the project already has scenes).
3. **Characters** (built): created from the script; for each character in this project's scenes the app asks only for what is missing. A reference image is required to continue; voice notes are optional. Unlinked speakers are listed.
4. **Automatic build** (pictures built): every scene without media gets a picture from `text_to_image` (SDXL), one job at a time, prompted from the character's face prompt, the scene's location and its line. Voice tracks and clips come with the Phase 3 voice and video models.
5. **Review and export** (built): the AI disclosure checklist must be confirmed, then the render runs and the download appears.

Local GPU: `run-gpu.ps1` runs the worker on this computer's NVIDIA card (this machine reports an RTX 5060 with 8 GB, driver 621.01; the model has not yet run on it) behind a
RunPod-shaped API on 127.0.0.1, so the backend uses the same client. `run-local.ps1` starts it when `nvidia-smi` exists.
Models and licences are recorded in `docs/models.md`.

Each step must be complete before the next opens, and progress is saved so a run can be resumed. Any
project, including ones started in the studio, opens at its first unfinished step from "Continue automatically" on the dashboard.

- The build step reads `/api/generation/capabilities/`. A capability that is not available stops the run at that point with a plain message. Nothing is faked; until Phase 3 models exist the run ends after step 3.
- A backend run record drives the build with Celery, one generation job per scene and capability, inside the existing per-workspace job cap and time limits.

## Phase 4: Polish and performance

Streaming previews, caching, lazy loading, mobile layout, accessibility, recorded speed benchmarks and
Playwright tests for every flow. Sample outputs are shown before any quality claims.

## Rules

- Original UI and copy. No HeyGen or Magic Hour branding, assets or code.
- No fake output: unavailable features say so plainly.
- Verify each phase in the live app before moving on.
