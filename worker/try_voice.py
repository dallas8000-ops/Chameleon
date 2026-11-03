"""Reads one line in a cloned voice on this computer's GPU and saves it. Runs in .venv-voice (Chatterbox, MIT).

Usage: python try_voice.py reference.wav output.wav ["text to speak"]
Only clone a voice you own or have permission to use. Chatterbox watermarks every output (Resemble AI Perth).
"""
import sys
import time

import soundfile
import torch
from chatterbox.tts import ChatterboxTTS

DEFAULT_TEXT = (
    "They called me Muzungu on my very first day in Kampala. "
    "I just laughed, because I'm Black, and I had no idea what was coming next."
)

reference, output = sys.argv[1], sys.argv[2]
text = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_TEXT

started = time.monotonic()
model = ChatterboxTTS.from_pretrained(device="cuda")
loaded = time.monotonic()
torch.cuda.reset_peak_memory_stats()
wav = model.generate(text, audio_prompt_path=reference)
spoken = time.monotonic()
audio = wav.squeeze(0).detach().cpu().numpy()
soundfile.write(output, audio, model.sr)

print(f"GPU: {torch.cuda.get_device_name(0)}")
print(f"Load {loaded - started:.1f}s | speak {spoken - loaded:.1f}s | audio {len(audio) / model.sr:.1f}s")
print(f"Peak GPU memory {torch.cuda.max_memory_allocated() / 1024**3:.1f} GB")
print(f"Saved {output}")
