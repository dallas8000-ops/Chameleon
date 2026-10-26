# Models

Every model is checked for commercial-use terms before it is used. Weights are downloaded by the worker at
run time from Hugging Face; none are committed to this repository.

| Capability | Model | Licence | Commercial use | Notes |
| --- | --- | --- | --- | --- |
| `text_to_image` | [stabilityai/stable-diffusion-xl-base-1.0](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0) | CreativeML Open RAIL++-M | Allowed, subject to the licence's use restrictions (no unlawful, harmful or deceptive use) | Half precision, about 7 GB of weights. Fits a 16 GB card as is; on cards under 12 GB (this machine has an RTX 5060, 8 GB) the worker offloads the model part by part and tiles the VAE. |
| `text_to_image` (VAE) | [madebyollin/sdxl-vae-fp16-fix](https://huggingface.co/madebyollin/sdxl-vae-fp16-fix) | MIT | Allowed | Replaces the stock SDXL VAE, which can produce black images in half precision. |

Considered and not used yet:

- FLUX.1 [schnell] (Apache-2.0): better pictures, but its 12B transformer needs about 24 GB in bf16, so a
  16 GB card needs quantisation or slow sequential offloading. Revisit with an fp8 or NF4 build.
- SDXL Turbo: non-commercial licence.

The AI disclosure setting on each project applies to anything these models produce.
