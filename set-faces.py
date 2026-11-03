"""Attaches each character's photo in local-fixtures/characters as their face reference. Run via set-faces.ps1.

Pictures of a character then keep this face (IP-Adapter). Marcus uses the HeyGen master image from the series bible.
"""
import uuid
from pathlib import Path

import django

django.setup()

from django.core.files import File  # noqa: E402
from django.core.files.storage import default_storage  # noqa: E402

from apps.studio.models import Asset, Character  # noqa: E402
from apps.studio.services import AssetService  # noqa: E402

FOLDER = Path(__file__).resolve().parent / "local-fixtures" / "characters"
FACES = {
    "Marcus Johnson": "marcus-master-cropped.jpeg",
    "Kato": "kato.jpeg",
    "Mama Grace": "mama-grace.jpeg",
    "Nakato": "nakato.jpeg",
    "Sarah": "sarah.jpeg",
    "The boy": "boy.jpeg",
}
# The series bible's master look for Marcus; replaces the older T-shirt and sunglasses description.
MARCUS_LOOK = (
    "Fit athletic Black American man in his early 50s, U.S. Army veteran with an upright military posture, "
    "lean muscular build, slim waist, clean-shaven, short black hair, no glasses, warm smile, "
    "wearing a fitted dark blazer over a light blue shirt. Natural daylight, Kampala, photorealistic, vertical 9:16."
)
# Keeps the face reference from drifting older or heavier than the character.
MARCUS_AVOID = "overweight, fat, chubby, heavy, double chin, elderly, old man, grey hair, wrinkles, glasses"

for name, filename in FACES.items():
    path = FOLDER / filename
    characters = list(Character.objects.filter(name__iexact=name))
    if not characters or not path.exists():
        print(f"{name}: skipped ({'no character' if not characters else f'{filename} missing'}).")
        continue
    with open(path, "rb") as handle:
        sniffed = AssetService.sniff(handle.read(16))
    if sniffed is None or sniffed[2] != Asset.AssetType.IMAGE:
        print(f"{name}: skipped ({filename} is not a PNG, JPEG or WebP picture).")
        continue
    content_type, extension, asset_type = sniffed
    for character in characters:
        key = f"workspaces/{character.workspace_id}/assets/{uuid.uuid4().hex}.{extension}"
        with open(path, "rb") as handle:
            saved = default_storage.save(key, File(handle))
        asset = Asset.objects.create(
            workspace_id=character.workspace_id, asset_type=asset_type, name=filename, storage_key=saved,
            content_type=content_type, size_bytes=path.stat().st_size, provenance={"source": "upload"},
        )
        character.reference_asset = asset
        fields = ["reference_asset", "updated_at"]
        if name == "Marcus Johnson":
            character.face_prompt = MARCUS_LOOK
            character.negative_prompt = MARCUS_AVOID
            fields += ["face_prompt", "negative_prompt"]
        character.save(update_fields=fields)
        print(f"{name}: face from {filename} (asset {asset.id}).")
