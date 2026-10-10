"""Deterministic parser for series scripts written in the "Ep N" markdown format. No AI is involved."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_SCRIPT_CHARS = 200_000
MAX_EPISODES = 30
MAX_SCENES_PER_EPISODE = 100
EXPORT_SCENE_LIMIT = 20


class ScriptImportError(Exception):
    pass


@dataclass
class ParsedScene:
    title: str
    text: str
    role: str
    speaker: str = ""
    delivery: str = ""
    location: str = ""
    on_screen: bool = False


@dataclass
class ParsedEpisode:
    number: int
    title: str
    scenes: list[ParsedScene] = field(default_factory=list)


@dataclass
class ParsedCharacter:
    name: str
    role: str = ""
    description: str = ""
    face_prompt: str = ""
    negative_prompt: str = ""


EPISODE_RE = re.compile(r"^###\s+Ep(?:isode)?\s+(\d+)\s*[—–:-]\s*(.+?)\s*$")
HEADING_RE = re.compile(r"^#{1,3}\s")
SCENE_RE = re.compile(r"^\*\*Scene:\s*(.+?)\*\*\s*$")
LABEL_RE = re.compile(r"^\*\*([A-Za-z][A-Za-z ]*?)(?:\s*\(([^)]*)\))?:\*\*\s*(.*)$")
DIALOGUE_RE = re.compile(r"^([A-Z][A-Z0-9'’ .-]*[A-Z0-9])(?:\s*\(([^)]*)\))?:\s*(.+)$")
LABELS = {
    "hook": ("Hook", "hook"),
    "twist": ("Twist", "twist"),
    "closer": ("Closer", "end_card"),
    "closing voiceover": ("Closing voiceover", "voiceover"),
}


def _short(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _episode_title(rest: str) -> str:
    quoted = re.search(r"[\"“](.+?)[\"”]", rest)
    return (quoted.group(1) if quoted else rest).strip()


def parse_episodes(script: str) -> list[ParsedEpisode]:
    episodes: list[ParsedEpisode] = []
    current: ParsedEpisode | None = None
    location = ""
    for raw in script.splitlines():
        line = raw.strip()
        header = EPISODE_RE.match(line)
        if header:
            current = ParsedEpisode(number=int(header.group(1)), title=_episode_title(header.group(2)))
            episodes.append(current)
            location = ""
            continue
        if HEADING_RE.match(line):
            current = None
            continue
        if current is None or not line:
            continue
        scene_header = SCENE_RE.match(line)
        if scene_header:
            location = scene_header.group(1).strip().rstrip(".")
            continue
        label = LABEL_RE.match(line)
        if label and label.group(1).strip().lower() in LABELS:
            title, role = LABELS[label.group(1).strip().lower()]
            text = label.group(3).strip()
            if text:
                current.scenes.append(ParsedScene(
                    title=title, text=text, role=role, location=location,
                    on_screen="on screen" in (label.group(2) or "").lower() or role == "end_card",
                ))
            continue
        dialogue = DIALOGUE_RE.match(line)
        if dialogue:
            speaker = dialogue.group(1).strip()
            current.scenes.append(ParsedScene(
                title=f"{speaker.title()}: {_short(dialogue.group(3), 70)}", text=dialogue.group(3).strip(),
                role="dialogue", speaker=speaker, delivery=(dialogue.group(2) or "").strip(), location=location,
            ))
            continue
        current.scenes.append(ParsedScene(title=_short(line, 80), text=line, role="action", location=location))
    seen: set[int] = set()
    for episode in episodes:
        if episode.number in seen:
            raise ScriptImportError(f"Episode {episode.number} appears more than once.")
        seen.add(episode.number)
        if len(episode.scenes) > MAX_SCENES_PER_EPISODE:
            raise ScriptImportError(f"Episode {episode.number} has more than {MAX_SCENES_PER_EPISODE} lines.")
    return episodes


def _character_table(script: str) -> list[tuple[str, str, str]]:
    lines = script.splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(r"^##\s+Character bible", line.strip(), re.I)), None)
    if start is None:
        return []
    cells: list[str] = []
    for line in lines[start + 1:]:
        stripped = line.strip()
        if stripped.startswith("**") or stripped.startswith("#"):
            break
        if stripped:
            cells.append(stripped)
    if [c.lower() for c in cells[:3]] == ["character", "who they are", "role in the series"]:
        cells = cells[3:]
    if not cells or len(cells) % 3:
        return []
    return [(cells[i], cells[i + 1], cells[i + 2]) for i in range(0, len(cells), 3)]


def _split_reference(body: str) -> tuple[str, str]:
    body = " ".join(body.split())
    body = re.sub(r"^Character reference:\s*", "", body, flags=re.I)
    parts = re.split(r"(?:(?<=\.)\s+|,\s+)(?=[Ww]earing\b)", body, maxsplit=1)
    description = parts[1].strip() if len(parts) > 1 else ""
    return parts[0].strip().rstrip(".,"), (description[:1].upper() + description[1:])


LABEL_LINE_RE = re.compile(r"^\*\*([^*]+?)\*\*\s*(?:\(([^)]*)\))?\s*$")


def _reference_blocks(script: str) -> list[tuple[str, str, str]]:
    """Finds a bold label line followed (before any other label or heading) by a fenced "Character reference:" block."""
    lines = script.splitlines()
    found: list[tuple[str, str, str]] = []
    for index, line in enumerate(lines):
        label = LABEL_LINE_RE.match(line.strip())
        if not label:
            continue
        cursor = index + 1
        while cursor < len(lines) and not lines[cursor].strip().startswith(("```", "**", "#")):
            cursor += 1
        if cursor >= len(lines) or not lines[cursor].strip().startswith("```"):
            continue
        body: list[str] = []
        cursor += 1
        while cursor < len(lines) and not lines[cursor].strip().startswith("```"):
            body.append(lines[cursor])
            cursor += 1
        text = "\n".join(body).strip()
        if text.lower().startswith("character reference:"):
            name = re.sub(r"\s+visual reference$", "", label.group(1).strip(), flags=re.I)
            found.append((name, (label.group(2) or "").strip(), text))
    return found


def parse_characters(script: str) -> list[ParsedCharacter]:
    table = _character_table(script)
    visuals = _reference_blocks(script)
    common = re.search(r"negative or avoid field, add: \"([^\"]+)\"", script)
    extra = re.search(r"For (\w+) only, also add \"([^\"]+)\"", script)

    characters: list[ParsedCharacter] = []
    used: set[int] = set()
    for name, who, series_role in table:
        character = ParsedCharacter(name=name, role=who, description="")
        for index, (visual_name, _hint, body) in enumerate(visuals):
            if index not in used and visual_name.lower() in (name.lower(), name.split()[0].lower()):
                used.add(index)
                character.face_prompt, character.description = _split_reference(body)
                break
        extras = f"Series role: {series_role}"
        character.description = f"{character.description} {extras}".strip()
        characters.append(character)
    for index, (visual_name, hint, body) in enumerate(visuals):
        if index in used:
            continue
        face, outfit = _split_reference(body)
        characters.append(ParsedCharacter(
            name=visual_name, role=(hint[:1].upper() + hint[1:]) if hint else "", face_prompt=face, description=outfit,
        ))
    for character in characters:
        negatives = []
        if extra and character.name.split()[0].lower() == extra.group(1).lower():
            negatives.append(extra.group(2))
        if common:
            negatives.append(common.group(1))
        character.negative_prompt = ", ".join(negatives)
    return characters


def match_character(speaker: str, names: list[str]) -> str | None:
    wanted = speaker.strip().lower()
    for name in names:
        lowered = name.lower()
        if wanted == lowered or wanted == lowered.split()[0] or lowered == f"the {wanted}":
            return name
    return None


def parse_script(script: str) -> tuple[list[ParsedEpisode], list[ParsedCharacter]]:
    script = script.replace("\r\n", "\n").lstrip("\ufeff")
    if len(script) > MAX_SCRIPT_CHARS:
        raise ScriptImportError("The script is too long to import at once.")
    episodes = parse_episodes(script)
    episodes = [episode for episode in episodes if episode.scenes]
    if not episodes:
        raise ScriptImportError('No episodes found. Episodes start with a line like: ### Ep 1 — "Title".')
    if len(episodes) > MAX_EPISODES:
        raise ScriptImportError(f"At most {MAX_EPISODES} episodes can be imported at once.")
    return episodes, parse_characters(script)
