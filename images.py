import os
import torch
from diffusers import AutoencoderKL, StableDiffusionXLPipeline
from options import styles, bad

# sdxl draws much better faces than stable diffusion 1.5
imgmodel = os.environ.get("imgmodel", "stabilityai/stable-diffusion-xl-base-1.0")
size = int(os.environ.get("imgsize", "1024"))
steps = int(os.environ.get("imgsteps", "28"))


def loadimager():
    vae = AutoencoderKL.from_pretrained("madebyollin/sdxl-vae-fp16-fix", torch_dtype=torch.float16)
    pipe = StableDiffusionXLPipeline.from_pretrained(
        imgmodel, vae=vae, torch_dtype=torch.float16, variant="fp16", use_safetensors=True
    )
    pipe.enable_model_cpu_offload()
    return pipe


def drawscene(pipe, character, scene, style, seed):
    # same character in every scene helps the hero look similar
    prompt = f"{character}, {scene['image']}, {styles[style]}"
    gen = torch.Generator("cpu").manual_seed(seed)
    out = pipe(
        prompt=prompt,
        negative_prompt=bad,
        num_inference_steps=steps,
        guidance_scale=6.5,
        height=size,
        width=size,
        generator=gen,
    )
    return out.images[0]
