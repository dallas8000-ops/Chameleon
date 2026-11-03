"""Produces a whole episode without the browser: pictures, voice lines, then the MP4. Run via produce.ps1.

PRODUCE_PROJECT: project id or part of its title. PRODUCE_MODE: "plan" (default, changes nothing) or "run".
The GPU worker (run-gpu.ps1) must be running for "run". Voices are only made for characters with a voice
sample; scenes without speech keep the export's default still duration.
"""
import os
import shutil
import sys
import time
from pathlib import Path

import django

django.setup()

from django.conf import settings  # noqa: E402
from django.core.files.storage import default_storage  # noqa: E402

from apps.accounts.models import WorkspaceMembership  # noqa: E402
from apps.generation.models import GenerationJob  # noqa: E402
from apps.generation.services import JobService  # noqa: E402
from apps.generation.tasks import advance_on_read, submit_job  # noqa: E402
from apps.studio.models import Character, Export, Project, Scene  # noqa: E402

STYLE = "cinematic film still, natural light, sharp focus, high detail"
NEGATIVE = "text, caption, watermark, logo, blurry, deformed, extra fingers, low quality"
WORDS_PER_SECOND = 2.5  # about 150 words a minute
FINISHED = (GenerationJob.Status.COMPLETED, GenerationJob.Status.FAILED, GenerationJob.Status.CANCELED)


def find_project(key: str) -> Project:
    if key.isdigit():
        return Project.objects.get(pk=int(key))
    matches = list(Project.objects.filter(title__icontains=key))
    if len(matches) > 1:  # "Ep 1" means "Ep 1: ...", not "Ep 10: ..." or "Sample: Ep 1 ..."
        matches = [p for p in matches if p.title.lower().startswith(f"{key.lower()}:")] or matches
    if len(matches) != 1:
        raise SystemExit(f"Expected one project matching {key!r}, found {[p.title for p in matches]}.")
    return matches[0]


def text(config: dict, key: str) -> str:
    return config.get(key) if isinstance(config.get(key), str) else ""


def picture_params(scene: Scene, character: Character | None, fmt: str) -> dict:
    # "shot" describes the picture when the spoken line alone would make a poor prompt.
    parts = [character.face_prompt if character else "", text(scene.config, "location"),
             text(scene.config, "shot") or scene.script_text, STYLE]
    prompt = ". ".join(p.strip() for p in parts if p and p.strip())[:2000]
    negative = ", ".join(p for p in [(character.negative_prompt.strip() if character else ""), NEGATIVE] if p)[:2000]
    params = {"prompt": prompt, "negative_prompt": negative, "size": "landscape" if fmt == "16:9" else "portrait"}
    if character and character.reference_asset_id:
        params["reference_asset_id"] = character.reference_asset_id
    return params


def shown(scene: Scene, characters: dict, character: Character | None) -> Character | None:
    """The character in the picture: config "shown" (a name, or "" for nobody) or else the speaker."""
    if "shown" not in scene.config:
        return character
    name = text(scene.config, "shown").lower()
    return next((c for c in characters.values() if c.name.lower() == name), None)


def run_job(user, project: Project, scene: Scene, capability: str, params: dict) -> int:
    job = JobService.create(user=user, workspace_id=project.workspace_id, capability_name=capability, params=params,
                            project_id=project.id, scene_id=scene.id)
    submit_job(job.id)
    started = time.monotonic()
    while True:
        job.refresh_from_db()
        job = advance_on_read(job)
        if job.status in FINISHED:
            break
        time.sleep(3)
    if job.status != GenerationJob.Status.COMPLETED or not job.result_asset_id:
        raise SystemExit(f"  {capability} failed for scene {scene.order_index + 1}: {job.error_message or job.status}")
    print(f"  {capability} done in {time.monotonic() - started:.0f}s", flush=True)
    return job.result_asset_id


def main() -> None:
    project = find_project(os.environ.get("PRODUCE_PROJECT", "Ep 1"))
    mode = os.environ.get("PRODUCE_MODE", "plan")
    scenes = list(project.scenes.order_by("order_index", "id"))
    characters = {c.id: c for c in Character.objects.filter(workspace_id=project.workspace_id)}
    narrator_name = os.environ.get("PRODUCE_NARRATOR", "").strip().lower()
    narrator = next((c for c in characters.values() if c.name.lower() == narrator_name), None)
    if narrator_name and narrator is None:
        raise SystemExit(f"No character named {narrator_name!r} to narrate.")
    print(f"{project.title} [{project.format}] - {len(scenes)} scenes")
    if mode == "show":
        for character in characters.values():
            print(f"[{character.name}] {character.role} - {character.description} | voice notes: {character.voice_notes}")
        for scene in scenes:
            who = characters[scene.character_id].name if scene.character_id in characters else "narration"
            print(f"\n{scene.order_index + 1}. {scene.title} ({who}) config={ {k: v for k, v in scene.config.items()} }")
            print(scene.script_text)
        return
    words = spoken = 0
    for scene in scenes:
        character = characters.get(scene.character_id)
        speaker = character or narrator
        count = len(scene.script_text.split())
        words += count
        voiced = bool(speaker and speaker.voice_sample_asset_id and count)
        spoken += count if voiced else 0
        media = "picture" if isinstance(scene.config.get("asset_id"), int) else "no picture"
        audio = "voice" if isinstance(scene.config.get("audio_asset_id"), int) else ("will speak" if voiced else "silent")
        who = character.name if character else (scene.config.get("speaker") or "narration/text")
        print(f" {scene.order_index + 1:>2}. {scene.title[:40]:<40} {who:<18} {count:>4} words  {media}, {audio}")
    print(f"\nScript: {words} words, about {words / WORDS_PER_SECOND / 60:.1f} min if every line is spoken.")
    print(f"Lines with a voice right now: {spoken} words, about {spoken / WORDS_PER_SECOND / 60:.1f} min.")
    if mode != "run":
        return

    owner = WorkspaceMembership.objects.filter(workspace_id=project.workspace_id, role="owner").select_related("user").first()
    if owner is None:
        raise SystemExit("The workspace has no owner to run the jobs as.")
    redo_pictures = os.environ.get("PRODUCE_REDO_PICTURES") == "1"
    for scene in scenes:
        character = characters.get(scene.character_id)
        print(f"Scene {scene.order_index + 1}: {scene.title}", flush=True)
        if redo_pictures or not isinstance(scene.config.get("asset_id"), int):
            asset = run_job(owner.user, project, scene, "text_to_image",
                            picture_params(scene, shown(scene, characters, character), project.format))
            scene.kind = Scene.Kind.IMAGE
            scene.config = {**scene.config, "asset_id": asset}
            scene.save()
        speaker = character or narrator
        if speaker and speaker.voice_sample_asset_id and scene.script_text.strip() and not isinstance(scene.config.get("audio_asset_id"), int):
            asset = run_job(owner.user, project, scene, "voice",
                            {"text": scene.script_text[:1000], "voice_sample_asset_id": speaker.voice_sample_asset_id})
            scene.config = {**scene.config, "audio_asset_id": asset, "fit_to_audio": True}
            scene.save()

    from apps.rendering.services import snapshot_export
    from apps.rendering.tasks import queue_export_job

    print("Rendering the video...", flush=True)
    output_format, export_settings, manifest = snapshot_export(
        project, {"burn_captions": project.captions.exists(), "burn_ai_label": bool(project.ai_disclosure)},
    )
    export = Export.objects.create(project=project, format=output_format, settings=export_settings, manifest=manifest)
    queue_export_job(project.id, export.id)
    for _ in range(600):
        export.refresh_from_db()
        if export.status in (Export.Status.COMPLETED, Export.Status.FAILED):
            break
        time.sleep(2)
    if export.status != Export.Status.COMPLETED:
        raise SystemExit(f"Export failed: {export.error_message or export.status}")
    target = Path(settings.BASE_DIR).parent / "local-fixtures" / "exports" / f"{project.title[:60].replace(':', '')}.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    with default_storage.open(export.output_path, "rb") as source, open(target, "wb") as out:
        shutil.copyfileobj(source, out)
    print(f"\nDone: {target}")


if __name__ == "__main__":
    sys.exit(main())
