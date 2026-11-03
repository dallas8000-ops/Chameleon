# Models

Every model is checked for commercial-use terms before it is used. Weights are downloaded by the worker at
run time from Hugging Face; none are committed to this repository.

| Capability | Model | Licence | Commercial use | Notes |
| --- | --- | --- | --- | --- |
| `text_to_image` | [stabilityai/stable-diffusion-xl-base-1.0](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0) | CreativeML Open RAIL++-M | Allowed, subject to the licence's use restrictions (no unlawful, harmful or deceptive use) | Half precision, about 7 GB of weights. Fits a 16 GB card as is; on cards under 12 GB (this machine has an RTX 5060, 8 GB) the worker offloads the model part by part and tiles the VAE. |
| `text_to_image` (VAE) | [madebyollin/sdxl-vae-fp16-fix](https://huggingface.co/madebyollin/sdxl-vae-fp16-fix) | MIT | Allowed | Replaces the stock SDXL VAE, which can produce black images in half precision. |

| `voice` | [ResembleAI/chatterbox](https://huggingface.co/ResembleAI/chatterbox) | MIT | Allowed | Zero-shot voice cloning from a short reference clip (`audio_prompt_path`). Every output carries Resemble AI's imperceptible Perth watermark, which survives MP3 compression. Only clone voices you own or have permission to use. |

Considered and not used yet:

- FLUX.1 [schnell] (Apache-2.0): better pictures, but its 12B transformer needs about 24 GB in bf16, so a
  16 GB card needs quantisation or slow sequential offloading. Revisit with an fp8 or NF4 build.
- SDXL Turbo: non-commercial licence.
- Character faces in pictures: [h94/IP-Adapter](https://huggingface.co/h94/IP-Adapter) `ip-adapter-plus-face_sdxl_vit-h` with its ViT-H image encoder (Apache-2.0), loaded into the `text_to_image` pipeline. A scene picture of a character with a reference photo keeps that face (`TEXT_TO_IMAGE_FACE_SCALE`, default 0.6). Only use photos of people who agreed to it.
- Synthetic reference voices for characters without a real voice: [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache-2.0) via `make-voices.ps1`. Its English phonemizer falls back to espeak-ng (GPL-3.0), loaded as a separate library; fine for local use, review before shipping it inside a distributed product.
- XTTS-v2 (Coqui Public Model License) and the F5-TTS pretrained weights (CC-BY-NC): non-commercial, so not used for voices.

The AI disclosure setting on each project applies to anything these models produce.
