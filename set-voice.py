"""Lists characters, and optionally gives one a voice sample from a local audio file. Run via set-voice.ps1.

VOICE_CHARACTER (name, case-insensitive) and VOICE_FILE select the character and the WAV/MP3/M4A to use.
Only use a voice you own or have permission to use.
"""
import os
import uuid
from pathlib import Path

import django

django.setup()

from django.core.files import File  # noqa: E402
from django.core.files.storage import default_storage  # noqa: E402

from apps.studio.models import Asset, Character  # noqa: E402
from apps.studio.services import AssetService  # noqa: E402

for character in Character.objects.select_related("workspace").order_by("workspace_id", "name"):
    voice = "voice ready" if character.voice_sample_asset_id else "no voice"
    print(f"[{character.workspace.name}] {character.name} ({character.role or 'no role'}) - {voice}")

name = os.environ.get("VOICE_CHARACTER", "").strip()
path = Path(os.environ.get("VOICE_FILE", ""))
if name:
    matches = list(Character.objects.filter(name__iexact=name))
    if len(matches) != 1:
        raise SystemExit(f"\nExpected one character named {name!r}, found {len(matches)}.")
    character = matches[0]
    with open(path, "rb") as handle:
        sniffed = AssetService.sniff(handle.read(16))
    if sniffed is None or sniffed[2] != Asset.AssetType.AUDIO:
        raise SystemExit(f"\n{path} is not a WAV, MP3 or M4A file.")
    content_type, extension, asset_type = sniffed
    key = f"workspaces/{character.workspace_id}/assets/{uuid.uuid4().hex}.{extension}"
    with open(path, "rb") as handle:
        saved = default_storage.save(key, File(handle))
    asset = Asset.objects.create(
        workspace_id=character.workspace_id, asset_type=asset_type, name=path.name, storage_key=saved,
        content_type=content_type, size_bytes=path.stat().st_size, provenance={"source": "upload"},
    )
    character.voice_sample_asset = asset
    character.save(update_fields=["voice_sample_asset", "updated_at"])
    print(f"\n{character.name} now speaks in the voice from {path.name} (asset {asset.id}).")
