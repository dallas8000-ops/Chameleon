"""Makes one test picture on this computer's GPU and saves it, without the backend.

Usage: python try_picture.py [output.png]
"""
import sys
from pathlib import Path

from chameleon_worker import text_to_image

out = Path(sys.argv[1] if len(sys.argv) > 1 else "test-picture.png")
summary, png = text_to_image.run({
    "prompt": "a lighthouse keeper in a yellow raincoat on a rocky shore at dusk, cinematic film still, natural light, sharp focus",
    "negative_prompt": "text, watermark, blurry, deformed",
    "width": 768, "height": 1344, "steps": 30, "seed": 7,
})
out.write_bytes(png)
print(summary)
print(f"Saved {out.resolve()} ({len(png) // 1024} KB)")
