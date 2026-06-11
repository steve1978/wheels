"""Editing engine: turns API params into a Qwen instruction and runs it.

The 12GB model is loaded lazily on the first edit so the server boots instantly.
"""
from __future__ import annotations

from PIL import Image

# Named car colours for hex -> human description (Qwen follows names better than hex).
# Dense anchor table so arbitrary colour-wheel picks land on a sensible name.
_NAMED = {
    "racing red": (192, 24, 24), "deep red": (158, 27, 27), "crimson": (140, 20, 30),
    "candy red": (170, 10, 40), "burgundy": (110, 20, 35), "maroon": (90, 25, 30),
    "brick red": (160, 70, 50), "hot pink": (230, 60, 140), "rose pink": (225, 145, 165),
    "magenta": (200, 30, 160),
    "deep blue": (19, 53, 122), "royal blue": (40, 75, 190), "sky blue": (90, 150, 220),
    "baby blue": (160, 200, 235), "navy": (20, 30, 70), "midnight blue": (18, 24, 50),
    "miami blue": (0, 179, 199), "teal": (15, 94, 99), "turquoise": (45, 180, 175),
    "cyan": (60, 200, 220),
    "british racing green": (19, 68, 43), "forest green": (29, 58, 35),
    "emerald green": (20, 130, 80), "mint green": (150, 220, 180),
    "lime green": (120, 200, 40), "olive green": (110, 115, 50),
    "sunburst yellow": (232, 193, 0), "mustard yellow": (200, 160, 40),
    "cream": (240, 230, 200), "champagne": (203, 182, 130), "beige": (210, 190, 160),
    "tan": (180, 145, 100), "brown": (115, 80, 55), "chocolate brown": (75, 50, 35),
    "sunset orange": (224, 100, 27), "amber orange": (235, 140, 30),
    "copper": (180, 105, 60), "bronze": (156, 107, 63), "gold": (205, 164, 52),
    "royal purple": (91, 42, 134), "midnight purple": (46, 26, 71),
    "violet": (140, 90, 200), "lavender": (185, 165, 220),
    "jet black": (21, 23, 26), "charcoal grey": (40, 43, 47), "gunmetal grey": (58, 63, 69),
    "nardo grey": (110, 115, 120), "silver": (184, 188, 194), "chrome": (216, 221, 227),
    "pearl white": (238, 240, 242), "white": (252, 252, 252),
}

# Paint finishes -> (adjective, extra clause) woven into the instruction.
FINISHES = {
    "gloss": ("glossy", " with a deep glossy clearcoat"),
    "metallic": ("metallic", " with fine metal-flake sparkle under a glossy clearcoat"),
    "matte": ("matte", ", a completely flat non-reflective matte finish"),
    "satin": ("satin", " with a smooth soft-sheen satin finish"),
    "pearl": ("pearlescent", " with a subtle iridescent pearl shimmer"),
}


def describe_color(hex_str: str) -> str:
    h = hex_str.lstrip("#")
    if len(h) != 6:
        return "the chosen colour"
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    best, bestd = "the chosen colour", 1e9
    for name, (nr, ng, nb) in _NAMED.items():
        d = (r - nr) ** 2 + (g - ng) ** 2 + (b - nb) ** 2
        if d < bestd:
            best, bestd = name, d
    return best


import threading

_editor = None
_lock = threading.Lock()

# One GPU, one model: edits run strictly one-at-a-time. Concurrent requests queue
# here instead of racing the allocator into shared-memory spill.
_gpu_lock = threading.Lock()

# Live progress for the UI, polled via GET /api/progress.
PROGRESS = {"stage": "idle", "step": 0, "total": 4, "queued": 0}


def is_ready() -> bool:
    return _editor is not None


def get_editor():
    global _editor
    if _editor is None:
        with _lock:  # avoid double-load if requests race during warm-up
            if _editor is None:
                from .qwen_editor import QwenEditor
                _editor = QwenEditor()
    return _editor


# The model can't measure inches; pair the number with a strong directional cue
# (tyre-sidewall language moves the needle more than diameter words alone).
_SIZE_CUE = {
    17: "a compact diameter with a tall, chunky tyre sidewall",
    18: "a standard diameter with a normal tyre sidewall",
    19: "a slightly enlarged diameter with a slimmer tyre sidewall",
    20: "a clearly enlarged diameter with a low-profile tyre",
    21: "a much larger diameter with a very low-profile tyre",
    22: "a very large show-style diameter with rubber-band-thin tyres",
    23: "an extremely oversized diameter with paper-thin tyre sidewalls",
    24: "the most extreme oversized fitment possible, with virtually no tyre sidewall",
}


def _size_clause(size: int) -> str:
    cue = _SIZE_CUE.get(size, "a larger diameter")
    return (
        f", sized as {size}-inch wheels ({cue} for this car) with correspondingly "
        "lower-profile tyres so the wheel fills more of the arch"
    )


def apply_edit(
    image: Image.Image,
    body_color: str | None = None,
    body_finish: str | None = None,
    wheel_id: str | None = None,
    wheel_color: str | None = None,
    wheel_size: int | None = None,
    seed: int = 0,
) -> Image.Image:
    from . import library

    parts = []
    if body_color:
        adj, clause = FINISHES.get(body_finish or "gloss", FINISHES["gloss"])
        parts.append(f"repaint the car body in {adj} {describe_color(body_color)}{clause}")
    elif body_finish in FINISHES:
        adj, clause = FINISHES[body_finish]
        parts.append(
            f"change the car body paint to a {adj} finish{clause}, keeping the same colour"
        )

    ref_image = None
    cat = library.catalog_lookup(wheel_id)
    wheels_changing = bool(cat or wheel_color or wheel_size)
    if cat:
        ref_image = Image.open(cat["path"])
        seg = (
            f"replace the car's wheels with the {cat['brand']} {cat['model']} alloy wheel "
            "shown in the first image (the wheel product photo), copying its exact spoke design"
        )
        if wheel_color:
            seg += f" but finished in {describe_color(wheel_color)}"
        else:
            seg += f" and its {cat['finish']} finish"
        if wheel_size:
            seg += ", adapted to the car's angle and perspective" + _size_clause(wheel_size)
        else:
            seg += ", adapted to the car's wheel size, angle and perspective"
        parts.append(seg)
    elif wheel_color or wheel_size:
        # Recolour and/or resize the EXISTING wheels — the model loves to invent
        # a new spoke pattern, so the wording must be forceful and specific.
        actions = []
        if wheel_color:
            actions.append(f"repaint the car's existing wheel rims in {describe_color(wheel_color)}")
        if wheel_size:
            cue = _SIZE_CUE.get(wheel_size, "a larger diameter")
            actions.append(
                f"enlarge the car's existing wheels to {wheel_size}-inch ({cue} for "
                "this car) with correspondingly lower-profile tyres so the wheel "
                "fills more of the arch"
            )
        seg = ", and ".join(actions)
        seg += (
            ". CRITICAL: the wheels must remain IDENTICAL in design — the same number "
            "of spokes, the same spoke shape, the same centre cap"
        )
        if not wheel_size:
            seg += ", the same rim size"
        parts.append(seg)

    if not parts:
        return image

    keep = ["the exact same car", "same body shape", "same windows"]
    if not wheels_changing:
        keep.append("same wheels")
    elif (wheel_color or wheel_size) and not cat:
        keep.append("the same wheel design and spoke pattern")
    keep += ["same background", "same lighting, reflections and camera angle"]
    instruction = (
        "Edit this photo of a car: "
        + ", and ".join(parts)
        + ". Keep "
        + ", ".join(keep)
        + ". Photorealistic, only change what was asked."
    )
    negative = "different car, changed shape, distorted, deformed, artifacts, text, watermark, cartoon"
    if wheel_color and not cat:
        negative += ", different wheel design, new wheels, changed spoke pattern, redesigned wheels"

    PROGRESS["queued"] += 1
    with _gpu_lock:
        PROGRESS["queued"] -= 1
        editor = get_editor()
        PROGRESS.update(stage="rendering", step=0)

        def on_step(step, total):
            PROGRESS.update(step=step, total=total)

        import torch

        try:
            kw = dict(
                negative_prompt=negative, seed=seed, on_step=on_step, ref_image=ref_image
            )
            try:
                return editor.edit(image, instruction, **kw)
            except torch.cuda.OutOfMemoryError:
                # Transient pressure (fragmentation, desktop apps) — clear the cache
                # and retry once rather than letting the driver spill to system RAM.
                torch.cuda.empty_cache()
                PROGRESS.update(stage="rendering", step=0)
                return editor.edit(image, instruction, **kw)
        finally:
            PROGRESS.update(stage="idle", step=0)
            # Return cached allocator blocks to the driver so the desktop isn't
            # starved between edits (we run within ~2GB of the 24GB ceiling).
            torch.cuda.empty_cache()
