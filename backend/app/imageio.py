"""Data-URL <-> PIL helpers for the API."""
from __future__ import annotations

import base64
import io

from PIL import Image, ImageOps


def data_url_to_pil(data_url: str) -> Image.Image:
    """Accept 'data:image/...;base64,xxxx' or a bare base64 string."""
    if "," in data_url and data_url.strip().startswith("data:"):
        data_url = data_url.split(",", 1)[1]
    raw = base64.b64decode(data_url)
    img = Image.open(io.BytesIO(raw))
    return ImageOps.exif_transpose(img).convert("RGB")


def pil_to_data_url(img: Image.Image, fmt: str = "PNG", quality: int = 92) -> str:
    buf = io.BytesIO()
    if fmt.upper() in ("JPEG", "JPG"):
        img.convert("RGB").save(buf, format="JPEG", quality=quality)
        mime = "image/jpeg"
    else:
        img.save(buf, format=fmt)
        mime = "image/png"
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:{mime};base64,{b64}"
