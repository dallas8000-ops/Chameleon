"""Speaks one line in a cloned voice. Runs inside .venv-voice; called by chameleon_worker.voice.

Usage: python voice_cli.py sample.wav output.wav "text to speak"
"""
import sys

import soundfile
from chatterbox.tts import ChatterboxTTS

sample, output, text = sys.argv[1], sys.argv[2], sys.argv[3]
model = ChatterboxTTS.from_pretrained(device="cuda")
wav = model.generate(text, audio_prompt_path=sample)
soundfile.write(output, wav.squeeze(0).detach().cpu().numpy(), model.sr)
