"""Replaces a project's scenes with a longer script from content/muzungu/*.json. Run via load-episode.ps1.

EPISODE_FILE is the JSON file: {"project": "Ep 1", "scenes": [{"title", "speaker", "text", "location", "shot",
"shown"?, "on_screen_text"?}]}. A scene whose speaker and line are unchanged keeps its picture and voice.
"""
import json
import os
import sys
from pathlib import Path

import django

django.setup()

from django.db import transaction  # noqa: E402

from apps.studio.models import Character, Scene  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from produce import WORDS_PER_SECOND, find_project  # noqa: E402

KEEP = ("asset_id", "audio_asset_id", "fit_to_audio")


def main() -> None:
    data = json.loads(Path(os.environ["EPISODE_FILE"]).read_text(encoding="utf-8"))
    project = find_project(data["project"])
    characters = {c.name.lower(): c for c in Character.objects.filter(workspace_id=project.workspace_id)}
    old = {(s.character_id, s.script_text.strip()): s for s in project.scenes.all()}
    scenes = []
    for index, item in enumerate(data["scenes"]):
        speaker = characters.get((item.get("speaker") or "").lower())
        if item.get("speaker") and speaker is None:
            raise SystemExit(f"Scene {index + 1}: no character named {item['speaker']!r}.")
        config = {"source": "expanded_script", "episode_file": Path(os.environ["EPISODE_FILE"]).name}
        for key in ("location", "shot", "shown", "on_screen_text"):
            if key in item:
                config[key] = item[key]
        previous = old.get((speaker.id if speaker else None, item["text"].strip()))
        kind = Scene.Kind.SCRIPT
        if previous is not None:
            config.update({k: previous.config[k] for k in KEEP if k in previous.config})
            kind = previous.kind
        scenes.append(Scene(project=project, order_index=index, kind=kind, title=item["title"][:120],
                            script_text=item["text"].strip(), config=config, character=speaker))
    with transaction.atomic():
        project.scenes.all().delete()
        Scene.objects.bulk_create(scenes)
    words = sum(len(s.script_text.split()) for s in scenes)
    print(f"{project.title}: {len(scenes)} scenes, {words} words, about {words / WORDS_PER_SECOND / 60:.1f} min spoken.")


if __name__ == "__main__":
    main()
