"""Instruction-based image editing with Qwen-Image-Edit-2511.

Transformer is loaded from a GGUF quant (~12GB) so the 20B model fits a 24GB card
with model-cpu-offload. No masking needed — edits are driven by a text instruction.
"""
from __future__ import annotations

import torch
from PIL import Image

from . import config

_DTYPE = {"bfloat16": torch.bfloat16, "float16": torch.float16, "float32": torch.float32}


def _resize_to_max(img: Image.Image, max_side: int = 1024, mult: int = 16) -> Image.Image:
    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    nw, nh = max(mult, round(w * scale)), max(mult, round(h * scale))
    nw -= nw % mult
    nh -= nh % mult
    return img.resize((nw, nh), Image.LANCZOS)


class QwenEditor:
    def __init__(self, dtype: str = config.DTYPE):
        from diffusers import (
            GGUFQuantizationConfig,
            QwenImageEditPlusPipeline,
            QwenImageTransformer2DModel,
        )
        from transformers import BitsAndBytesConfig, Qwen2_5_VLForConditionalGeneration

        self.dtype = _DTYPE[dtype]
        # Prefer the directly-downloaded local GGUF; fall back to the HF cache.
        if config.QWEN_GGUF_PATH.exists():
            gguf_path = str(config.QWEN_GGUF_PATH)
        else:
            from huggingface_hub import hf_hub_download

            gguf_path = hf_hub_download(config.QWEN_GGUF_REPO, config.QWEN_GGUF_FILE)

        print("Loading Qwen transformer (GGUF)...", flush=True)
        transformer = QwenImageTransformer2DModel.from_single_file(
            gguf_path,
            quantization_config=GGUFQuantizationConfig(compute_dtype=self.dtype),
            config=config.QWEN_EDIT_MODEL,
            subfolder="transformer",
            torch_dtype=self.dtype,
        )
        # Text encoder in 4-bit so it fits alongside the transformer with NO cpu-offload
        # (offload streams ~28GB per edit and is far too slow interactively).
        print("Loading 4-bit text encoder...", flush=True)
        bnb_cfg = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=self.dtype
        )
        text_encoder = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            config.QWEN_EDIT_MODEL,
            subfolder="text_encoder",
            quantization_config=bnb_cfg,
            torch_dtype=self.dtype,
            device_map={"": 0},
        )

        print("Assembling pipeline...", flush=True)
        self.pipe = QwenImageEditPlusPipeline.from_pretrained(
            config.QWEN_EDIT_MODEL,
            transformer=transformer,
            text_encoder=text_encoder,
            torch_dtype=self.dtype,
        )
        self.pipe.set_progress_bar_config(disable=True)
        self.pipe.transformer.to("cuda")
        self.pipe.vae.to("cuda")  # text_encoder already on cuda (4-bit)
        # The decode-time VRAM spike is what pushes us over the 24GB ceiling into
        # shared-memory spill. Tiling/slicing live on the VAE object — the
        # pipeline-level enable_vae_tiling helpers do NOT exist on this pipeline.
        self.pipe.vae.enable_tiling()
        self.pipe.vae.enable_slicing()

        # Lightning LoRA -> 4-step inference. Falls back gracefully if it won't load
        # onto the GGUF-quantized transformer.
        self.lightning = False
        if config.QWEN_LORA_PATH.exists():
            print("Loading Lightning 4-step LoRA...", flush=True)
            try:
                self.pipe.load_lora_weights(str(config.QWEN_LORA_PATH))
                self.lightning = True
            except Exception as e:
                print(f"LoRA load failed ({e}); using full-step inference.", flush=True)

        # Fail fast instead of spilling: cap the torch allocator below the point
        # where Windows starts paging VRAM into system RAM. Over-budget edits then
        # raise OOM (caught upstream and retried smaller) rather than running 10x slow.
        torch.cuda.set_per_process_memory_fraction(0.93)
        print(f"Qwen editor ready (lightning={self.lightning}).", flush=True)

    def edit(
        self,
        image: Image.Image,
        prompt: str,
        negative_prompt: str = " ",
        steps: int | None = None,
        true_cfg_scale: float | None = None,
        seed: int = 0,
        max_side: int = 1280,  # input detail cap; generation runs at ~1Mpix regardless
        on_step=None,          # optional callback(step, total) for progress reporting
        ref_image: Image.Image | None = None,  # style reference (e.g. product wheel photo)
    ) -> Image.Image:
        # Lightning -> 4 steps, cfg=1 (no extra uncond pass). Otherwise full quality.
        if steps is None:
            steps = 4 if self.lightning else 30
        if true_cfg_scale is None:
            true_cfg_scale = 1.0 if self.lightning else 4.0
        # The pipeline re-buckets every input to ~1Mpix internally, so input size
        # affects detail, not compute — feed generously. ORDER MATTERS: the output
        # canvas is derived from the LAST image (pipeline line `image[-1].size`),
        # so the car must go last or a square wheel photo squares/crops the result.
        car = _resize_to_max(image.convert("RGB"), max_side)
        if ref_image is not None:
            images = [_resize_to_max(ref_image.convert("RGB"), 1024), car]
        else:
            images = [car]

        kwargs = {}
        if true_cfg_scale > 1.0:
            kwargs["negative_prompt"] = negative_prompt  # ignored (warns) at cfg<=1
        if on_step is not None:
            def _cb(pipe, i, t, cb_kwargs):
                try:
                    on_step(i + 1, steps)
                except Exception:
                    pass
                return cb_kwargs
            kwargs["callback_on_step_end"] = _cb

        # NOTE: never pass width/height here — the pipeline conditions on its own
        # ~1Mpix re-bucketed inputs, and an output canvas that disagrees with that
        # bucketing makes the model render a zoomed crop.
        out = self.pipe(
            image=images,  # [optional reference images..., car] — car drives the canvas
            prompt=prompt,
            num_inference_steps=steps,
            true_cfg_scale=true_cfg_scale,
            generator=torch.Generator(device="cpu").manual_seed(seed),
            **kwargs,
        ).images[0]
        return out

    # ----------------------------------------------------------- convenience
    def recolor_body(self, image: Image.Image, color: str, **kw) -> Image.Image:
        prompt = (
            f"Change the car's body paint color to {color}. Keep the exact same car, "
            "same wheels, same windows, same trim, same background, same lighting and "
            "reflections, same camera angle. Only repaint the body panels."
        )
        negative = "different car, changed shape, changed wheels, distorted, deformed, artifacts, text, watermark"
        return self.edit(image, prompt, negative_prompt=negative, **kw)
