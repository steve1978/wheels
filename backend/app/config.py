"""Shared config: model IDs, paths, and HF cache location.

Import this FIRST (before transformers/diffusers) so HF_HOME is set before those
libraries read it.
"""
import os
from pathlib import Path

# --- Paths -------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent      # <repo>/backend
PROJECT_DIR = BACKEND_DIR.parent                          # <repo>
MODELS_DIR = PROJECT_DIR / "models"
SAMPLES_DIR = BACKEND_DIR / "samples"
OUTPUTS_DIR = BACKEND_DIR / "outputs"
WHEEL_CATALOG_DIR = BACKEND_DIR / "wheel_catalog"   # real product wheels, per brand

for _d in (MODELS_DIR, SAMPLES_DIR, OUTPUTS_DIR, WHEEL_CATALOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Cache all HuggingFace downloads under the project (keeps them off C:).
os.environ.setdefault("HF_HOME", str(MODELS_DIR))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

# Reduce CUDA memory fragmentation (we run close to the 24GB ceiling) so edits don't
# spill into slow shared system memory. Must be set before torch initializes CUDA.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

# --- Model IDs ---------------------------------------------------------------
# Qwen-Image-Edit-2511 — instruction-based editor (recolor + wheel work).
# Transformer loaded from a GGUF quant; the rest from the official repo.
QWEN_EDIT_MODEL = "Qwen/Qwen-Image-Edit-2511"
QWEN_GGUF_REPO = "unsloth/Qwen-Image-Edit-2511-GGUF"
QWEN_GGUF_FILE = "qwen-image-edit-2511-Q4_K_S.gguf"   # ~12GB, fits 24GB w/ cpu offload
QWEN_GGUF_PATH = MODELS_DIR / QWEN_GGUF_FILE          # direct download target (curl)

# Lightning step-distillation LoRA: 4-step inference at cfg=1 (~15x fewer forward
# passes than 30 steps + true-CFG). Massive speedup with minimal quality loss.
QWEN_LORA_REPO = "lightx2v/Qwen-Image-Edit-2511-Lightning"
QWEN_LORA_FILE = "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors"
QWEN_LORA_PATH = MODELS_DIR / QWEN_LORA_FILE

# --- Inference defaults ------------------------------------------------------
DTYPE = "bfloat16"        # modern NVIDIA cards support bf16
DEVICE = "cuda"
