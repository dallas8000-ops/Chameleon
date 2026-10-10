from django.test import SimpleTestCase

from apps.studio.models import Character, Project, Scene
from apps.studio.script_import import ScriptImportError, match_character, parse_script
from apps.studio.tests.fixtures import StudioFixture

SAMPLE = """# Sample Series — Scripts

## Character bible
Character

Who they are

Role in the series

Ada Quinn

Lighthouse keeper, 50s

Lead. Calm and dry.

Bo

Ferry captain, 30s

Sidekick.

**Ada visual reference**

The master image is the studio look. Use this prompt:

```
Character reference: Woman in her fifties, grey bob, weathered smile. Wearing a yellow raincoat and boots. Rocky harbour at dawn, photorealistic, vertical 9:16.
```
**Bo** (ferry captain)

```
Character reference: Man in his thirties, short beard, quick grin, wearing a blue wool cap and an orange life vest. On a ferry deck, daylight.
```
**The gull** (episode 1 only)

```
Character reference: Seagull with one grey wing, wearing a tiny red scarf. On a pier rail.
```
If your tool has a negative or avoid field, add: "cartoon, blurry, extra fingers".

For Ada only, also add "sunglasses, hat" to the negative field.

## Episodes 1–2: Arrival

### Ep 1 — "The Light Goes Out"
**Hook (on screen):** The lamp died at midnight.

**Scene: the lighthouse gallery, night.**

ADA (to camera, calm): Forty years and it never blinked.

A gull lands on the rail.

GULL: Squawk.

BO (laughing): That bird has opinions.

**Twist:** Ada finds the fuse box was unplugged.

ADA: Lesson logged.

**Closer:** Word of the day: Fuse = small safety switch. Comment: Worst blackout?

### Ep 2 — "Ferry Day" (finale)
**Hook:** Nobody rides the ferry in fog.

**Scene: the pier.**

ARMAND: Two tickets.

**Closing voiceover:** The fog lifted at noon.

## Production notes
Ignore this section. ADA: not a scene.
"""


class ParserTests(SimpleTestCase):
    def test_parses_episodes_scenes_and_labels(self):
        episodes, _ = parse_script(SAMPLE)
        self.assertEqual([(e.number, e.title) for e in episodes], [(1, "The Light Goes Out"), (2, "Ferry Day")])
        first = episodes[0].scenes
        self.assertEqual([s.role for s in first], ["hook", "dialogue", "action", "dialogue", "dialogue", "twist", "dialogue", "end_card"])
        self.assertTrue(first[0].on_screen)
        self.assertEqual(first[1].speaker, "ADA")
        self.assertEqual(first[1].delivery, "to camera, calm")
        self.assertEqual(first[1].location, "the lighthouse gallery, night")
        self.assertEqual(first[1].title, "Ada: Forty years and it never blinked.")
        self.assertEqual(episodes[1].scenes[-1].title, "Closing voiceover")

    def test_parses_characters_with_faces_outfits_and_negatives(self):
        _, characters = parse_script(SAMPLE)
        by_name = {c.name: c for c in characters}
        self.assertEqual(list(by_name), ["Ada Quinn", "Bo", "The gull"])
        ada = by_name["Ada Quinn"]
        self.assertEqual(ada.role, "Lighthouse keeper, 50s")
        self.assertEqual(ada.face_prompt, "Woman in her fifties, grey bob, weathered smile")
        self.assertTrue(ada.description.startswith("Wearing a yellow raincoat and boots."))
        self.assertIn("Series role: Lead. Calm and dry.", ada.description)
        self.assertEqual(ada.negative_prompt, "sunglasses, hat, cartoon, blurry, extra fingers")
        self.assertEqual(by_name["Bo"].negative_prompt, "cartoon, blurry, extra fingers")
        self.assertEqual(by_name["Bo"].face_prompt, "Man in his thirties, short beard, quick grin")
        self.assertEqual(
            by_name["Bo"].description,
            "Wearing a blue wool cap and an orange life vest. On a ferry deck, daylight. Series role: Sidekick.",
        )
        self.assertEqual(by_name["The gull"].role, "Episode 1 only")

    def test_speaker_matching(self):
        names = ["Ada Quinn", "Bo", "The gull"]
        self.assertEqual(match_character("ADA", names), "Ada Quinn")
        self.assertEqual(match_character("BO", names), "Bo")
        self.assertEqual(match_character("GULL", names), "The gull")
        self.assertIsNone(match_character("ARMAND", names))

    def test_rejects_scripts_without_episodes_or_too_long(self):
        with self.assertRaises(ScriptImportError):
            parse_script("Just some text.")
        with self.assertRaises(ScriptImportError):
            parse_script("x" * 200_001)

    def test_duplicate_episode_numbers_rejected(self):
        with self.assertRaises(ScriptImportError):
            parse_script('### Ep 1 — "A"\nADA: Hi.\n### Ep 1 — "B"\nADA: Hi.\n')

    def test_runs_fast_on_large_input(self):
        big = "\n".join(f"**Label {i}**\n\ntext\n" for i in range(5000)) + SAMPLE
        episodes, _ = parse_script(big)
        self.assertEqual(len(episodes), 2)


class ImportApiTests(StudioFixture):
    url = "/api/projects/import-script/"

    def body(self, **extra):
        return {"workspace_id": self.workspace.id, "script": SAMPLE, **extra}

    def test_preview_does_not_write_and_reports_matches_and_warnings(self):
        self.client.force_login(self.editor)
        response = self.post(self.url, self.body())
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual([e["number"] for e in data["episodes"]], [1, 2])
        self.assertEqual([c["exists"] for c in data["characters"]], [False, False, False])
        gull = next(s for s in data["episodes"][0]["scenes"] if s["speaker"] == "GULL")
        self.assertEqual(gull["character"], "The gull")
        self.assertTrue(any("ARMAND" in w for w in data["warnings"]))
        self.assertEqual(Project.objects.filter(title__startswith="Ep ").count(), 0)
        self.assertEqual(Character.objects.count(), 0)

    def test_import_creates_projects_scenes_and_characters(self):
        self.client.force_login(self.editor)
        response = self.post(self.url, self.body(dry_run=False, format="16:9"))
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data["characters_created"], ["Ada Quinn", "Bo", "The gull"])
        self.assertEqual([p["title"] for p in data["projects"]], ["Ep 1: The Light Goes Out", "Ep 2: Ferry Day"])
        project = Project.objects.get(pk=data["projects"][0]["id"])
        self.assertEqual(project.format, "16:9")
        self.assertEqual(project.workspace_id, self.workspace.id)
        scenes = list(Scene.objects.filter(project=project))
        self.assertEqual([s.order_index for s in scenes], list(range(len(scenes))))
        ada_line = scenes[1]
        self.assertEqual(ada_line.character.name, "Ada Quinn")
        self.assertEqual(ada_line.config["delivery"], "to camera, calm")
        self.assertEqual(ada_line.config["source"], "script_import")
        self.assertEqual(scenes[0].config["on_screen_text"], "The lamp died at midnight.")
        self.assertEqual(scenes[-1].config["role"], "end_card")
        armand = Scene.objects.get(project_id=data["projects"][1]["id"], config__speaker="ARMAND")
        self.assertIsNone(armand.character_id)

    def test_import_selected_episodes_and_existing_characters_are_kept(self):
        existing = Character.objects.create(workspace=self.workspace, name="Ada Quinn", face_prompt="mine")
        self.client.force_login(self.owner)
        data = self.post(self.url, self.body(dry_run=False, episodes=[2], create_characters=True)).json()
        self.assertEqual([p["title"] for p in data["projects"]], ["Ep 2: Ferry Day"])
        self.assertEqual(data["characters_created"], ["Bo", "The gull"])
        existing.refresh_from_db()
        self.assertEqual(existing.face_prompt, "mine")

    def test_import_without_characters_leaves_them_unassigned(self):
        self.client.force_login(self.owner)
        data = self.post(self.url, self.body(dry_run=False, create_characters=False)).json()
        self.assertEqual(data["characters_created"], [])
        self.assertEqual(Character.objects.count(), 0)
        self.assertFalse(Scene.objects.exclude(character=None).exists())

    def test_invalid_requests(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.post(self.url, self.body(script="no episodes here")).status_code, 400)
        self.assertEqual(self.post(self.url, self.body(dry_run=False, episodes=[9])).status_code, 400)
        self.assertEqual(self.post(self.url, self.body(format="1:1")).status_code, 400)
        self.assertEqual(self.post(self.url, {"workspace_id": self.workspace.id}).status_code, 400)
        self.assertEqual(Project.objects.filter(title__startswith="Ep ").count(), 0)

    def test_roles_and_isolation(self):
        self.client.force_login(self.reviewer)
        self.assertEqual(self.post(self.url, self.body(dry_run=False)).status_code, 403)
        self.assertEqual(self.post(self.url, self.body()).status_code, 403)
        self.client.force_login(self.outsider)
        self.assertEqual(self.post(self.url, self.body(dry_run=False)).status_code, 404)
        self.client.logout()
        self.assertIn(self.post(self.url, self.body()).status_code, (401, 403))
        self.assertEqual(Project.objects.filter(title__startswith="Ep ").count(), 0)
