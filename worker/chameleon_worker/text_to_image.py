"""Text-to-image with Stable Diffusion XL base 1.0 (CreativeML Open RAIL++-M, commercial use allowed).

SDXL in half precision fits a 16 GB card such as the RTX 5080 as is; on an 8 GB card such as the RTX 5060
it is offloaded part by part, which is slower but fits. The model loads once, on
the first job, and stays in GPU memory. Run `python -m chameleon_worker.text_to_image --download` once to
fetch the weights (about 7 GB) before the first job, so that job does not spend its time limit downloading.
"""
from __future__ import annotations

import io
import os
import secrets
import sys
import threading
import time

MODEL_ID = os.environ.get("TEXT_TO_IMAGE_MODEL", "stabilityai/stable-diffusion-xl-base-1.0")
# The stock SDXL VAE overflows in half precision and can return black images; this fixed VAE (MIT) does not.
VAE_ID = os.environ.get("TEXT_TO_IMAGE_VAE", "madebyollin/sdxl-vae-fp16-fix")
# IP-Adapter Plus Face (Apache-2.0) keeps a character's face from a reference picture.
IP_ADAPTER_ID = os.environ.get("TEXT_TO_IMAGE_IP_ADAPTER", "h94/IP-Adapter")
IP_ADAPTER_WEIGHTS = "ip-adapter-plus-face_sdxl_vit-h.safetensors"
# How strongly the reference face steers the picture (0 ignores it); higher copies the photo more literally.
FACE_SCALE = float(os.environ.get("TEXT_TO_IMAGE_FACE_SCALE", "0.6"))
SIZES = {(768, 1344), (1344, 768), (1024, 1024)}
MAX_PROMPT = 2000
DEFAULT_STEPS = 30
GUIDANCE = 6.0
# Below this much graphics memory the model is offloaded part by part (slower, but it fits in 8 GB).
LOW_MEMORY_BYTES = 12 * 1024**3

_pipeline = None
_lock = threading.Lock()


class ParamError(ValueError):
    pass


def check_params(params: object) -> dict:
    if not isinstance(params, dict):
        raise ParamError("The picture settings were missing.")
    prompt = params.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT:
        raise ParamError("The picture needs a description of 1 to 2000 characters.")
    negative = params.get("negative_prompt", "")
    if not isinstance(negative, str) or len(negative) > MAX_PROMPT:
        raise ParamError("The negative prompt must be text of at most 2000 characters.")
    width, height = params.get("width", 1024), params.get("height", 1024)
    if (width, height) not in SIZES:
        raise ParamError("Unsupported picture size.")
    steps = params.get("steps", DEFAULT_STEPS)
    if isinstance(steps, bool) or not isinstance(steps, int) or not 10 <= steps <= 50:
        raise ParamError("Steps must be a whole number from 10 to 50.")
    seed = params.get("seed")
    if seed is None:
        seed = secrets.randbelow(2**31)
    elif isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**31:
        raise ParamError("The seed must be a whole number from 0 to 2147483647.")
    return {"prompt": prompt.strip(), "negative_prompt": negative.strip(), "width": width, "height": height, "steps": steps, "seed": seed}


def _load():
    global _pipeline
    with _lock:
        if _pipeline is None:
            import torch
            from diffusers import AutoencoderKL, StableDiffusionXLPipeline
            from transformers import CLIPVisionModelWithProjection

            if not torch.cuda.is_available():
                raise RuntimeError("No CUDA graphics card is available to this worker.")
            vae = AutoencoderKL.from_pretrained(VAE_ID, torch_dtype=torch.float16)
            image_encoder = CLIPVisionModelWithProjection.from_pretrained(
                IP_ADAPTER_ID, subfolder="models/image_encoder", torch_dtype=torch.float16,
            )
            pipeline = StableDiffusionXLPipeline.from_pretrained(
                MODEL_ID, vae=vae, image_encoder=image_encoder, torch_dtype=torch.float16, variant="fp16",
                use_safetensors=True,
            )
            # Loaded before offloading so the adapter is moved on and off the GPU with the rest of the model.
            pipeline.load_ip_adapter(IP_ADAPTER_ID, subfolder="sdxl_models", weight_name=IP_ADAPTER_WEIGHTS)
            if torch.cuda.get_device_properties(0).total_memory < LOW_MEMORY_BYTES:
                # 8 GB cards (for example an RTX 5060): keep only the active part of the model on the GPU.
                pipeline.enable_model_cpu_offload()
                # Newer diffusers moved tiling from the pipeline onto the VAE itself.
                pipeline.vae.enable_tiling()
            else:
                pipeline = pipeline.to("cuda")
            _pipeline = pipeline
    return _pipeline


def _reference_image(reference: bytes | None):
    from PIL import Image

    if reference is None:
        # With the adapter loaded every call needs an image; a blank one at scale 0 has no effect.
        return Image.new("RGB", (224, 224), (128, 128, 128)), 0.0
    try:
        image = Image.open(io.BytesIO(reference))
        image.load()
    except Exception as error:  # noqa: BLE001 - any unreadable file is the same failure to the user
        raise ParamError("The reference picture could not be read.") from error
    return image.convert("RGB"), FACE_SCALE


def run(params: object, reference: bytes | None = None) -> tuple[dict, bytes]:
    settings = check_params(params)
    face, scale = _reference_image(reference)
    import torch

    started = time.monotonic()
    pipeline = _load()
    loaded = time.monotonic()
    pipeline.set_ip_adapter_scale(scale)
    # A CPU generator works with and without offloading and gives the same picture for the same seed.
    generator = torch.Generator(device="cpu").manual_seed(settings["seed"])
    image = pipeline(
        prompt=settings["prompt"], negative_prompt=settings["negative_prompt"] or None,
        width=settings["width"], height=settings["height"], num_inference_steps=settings["steps"],
        guidance_scale=GUIDANCE, generator=generator, ip_adapter_image=face,
    ).images[0]
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    summary = {
        "model": MODEL_ID, "seed": settings["seed"], "steps": settings["steps"],
        "width": settings["width"], "height": settings["height"],
        "load_seconds": round(loaded - started, 2), "generate_seconds": round(time.monotonic() - loaded, 2),
        "gpu": torch.cuda.get_device_name(0), "face_reference": reference is not None,
    }
    return summary, buffer.getvalue()


if __name__ == "__main__" and "--download" in sys.argv:
    from huggingface_hub import snapshot_download

    sdxl = ["*.json", "*.txt", "*fp16.safetensors", "diffusion_pytorch_model.safetensors"]
    adapter = ["models/image_encoder/*", f"sdxl_models/{IP_ADAPTER_WEIGHTS}"]
    for repo, patterns in ((VAE_ID, sdxl), (MODEL_ID, sdxl), (IP_ADAPTER_ID, adapter)):
        try:
            # Already downloaded: use the local copy and do not touch the network.
            snapshot_download(repo, allow_patterns=patterns, local_files_only=True)
            print(f"{repo}: already downloaded.", flush=True)
        except Exception:  # noqa: BLE001 - any miss means fetch it
            print(f"Downloading {repo} ...", flush=True)
            snapshot_download(repo, allow_patterns=patterns)
    print("Model ready.", flush=True)
