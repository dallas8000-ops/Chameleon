"""Makes a short synthetic reference clip per character with Kokoro, for Chatterbox to speak their lines in.

Run in .venv-voice: python make_voice_samples.py <output dir>. These are fully synthetic voices (Kokoro-82M,
Apache-2.0), not clones of a real person.
"""
import sys
from pathlib import Path

import numpy as np
import soundfile
from kokoro import KPipeline

SAMPLE_RATE = 24000
LINE = ("Every morning the market wakes up before the sun. People call out to each other, the boda bodas "
        "hum past, and somebody is always laughing. I have lived here all my life, and I still love it.")
# Character name -> (Kokoro voice, language code: "a" American, "b" British, speed).
VOICES = {
    "Kato": ("am_michael", "a", 1.0),
    "Mama Grace": ("bf_isabella", "b", 0.9),
    "Nakato": ("af_bella", "a", 1.0),
    "Sarah": ("af_heart", "a", 1.0),
    "The boy": ("af_nicole", "a", 1.1),
}


def main() -> None:
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    pipelines = {}
    for name, (voice, lang, speed) in VOICES.items():
        pipeline = pipelines.setdefault(lang, KPipeline(lang_code=lang))
        chunks = [np.asarray(audio) for _, _, audio in pipeline(LINE, voice=voice, speed=speed)]
        target = out_dir / f"{name}.wav"
        soundfile.write(target, np.concatenate(chunks), SAMPLE_RATE)
        print(f"{name}: {target}", flush=True)


if __name__ == "__main__":
    main()
