"""Auto-describe every catalog wheel's design using the on-disk vision model.

  .venv\\Scripts\\python.exe caption_wheels.py            # only wheels without a desc
  .venv\\Scripts\\python.exe caption_wheels.py --all      # redo everything
  .venv\\Scripts\\python.exe caption_wheels.py --limit 8  # quick test run

Why: the swap prompt sends the product photo AND a one-line geometry description;
bold simple designs (e.g. five flat spokes) only transfer faithfully when the
geometry is also spelled out in words. This reuses the app's own Qwen2.5-VL text
encoder (4-bit) as a captioner — no extra downloads.

NEEDS THE GPU: stop the app first (stop.bat). Run via caption.bat.
Saves are incremental (every 25 wheels), so interrupting is safe.
"""
import argparse
import json
import socket
import sys
import time

from app import config  # sets HF_HOME before transformers import

PROMPT = (
    "Look at this alloy wheel product photo. Describe its design in ONE short line "
    "for an image-generation prompt. Start with the exact spoke count — count "
    "carefully (for split/twin spokes phrase it like 'five pairs of twin spokes'). "
    "Then spoke shape and thickness. Then AT MOST TWO distinctive features, and "
    "ONLY if clearly visible in the photo — e.g. a deep dish, a polished lip, "
    "cross-lace mesh, holes in the spokes, lettering on the face, a directional "
    "curve. Most wheels have NO such features: do not list features you cannot "
    "actually see. Example: 'exactly five wide flat solid spokes forming a bold "
    "star, chunky retro rally style'. No brand names, no colours, no preamble."
)


def app_running() -> bool:
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect(("127.0.0.1", 8000))
        s.close()
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="re-describe wheels that already have a desc")
    ap.add_argument("--limit", type=int, default=0, help="max wheels this run (0 = no limit)")
    args = ap.parse_args()

    if app_running():
        print("The Wheels app is running and holds the GPU. Run stop.bat first, then retry.")
        sys.exit(1)

    # Load every manifest once; collect entries that need a description.
    manifests = {}  # path -> list
    work = []       # (path, entry-dict)
    for mp in sorted(config.WHEEL_CATALOG_DIR.glob("*/manifest.json")):
        m = json.loads(mp.read_text())
        manifests[mp] = m
        for w in m:
            if (args.all or not w.get("desc")) and (config.WHEEL_CATALOG_DIR / w["file"]).exists():
                work.append((mp, w))

    print(f"{len(work)} wheels need a description", flush=True)
    if not work:
        return
    if args.limit:
        work = work[: args.limit]
        print(f"limited to {len(work)} this run", flush=True)

    print("loading the vision model (4-bit, ~1 min)...", flush=True)
    import torch
    from PIL import Image
    from transformers import AutoProcessor, BitsAndBytesConfig, Qwen2_5_VLForConditionalGeneration

    bnb = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16
    )
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        config.QWEN_EDIT_MODEL,
        subfolder="text_encoder",
        quantization_config=bnb,
        torch_dtype=torch.bfloat16,
        device_map={"": 0},
    )
    processor = AutoProcessor.from_pretrained(config.QWEN_EDIT_MODEL, subfolder="processor")
    print("model ready", flush=True)

    def save(paths):
        for p in paths:
            p.write_text(json.dumps(manifests[p], indent=1))

    t0 = time.time()
    dirty = set()
    for n, (mp, w) in enumerate(work, 1):
        try:
            img = Image.open(config.WHEEL_CATALOG_DIR / w["file"]).convert("RGB")
            img.thumbnail((640, 640))
            messages = [
                {
                    "role": "user",
                    "content": [{"type": "image", "image": img}, {"type": "text", "text": PROMPT}],
                }
            ]
            text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = processor(text=[text], images=[img], return_tensors="pt").to("cuda")
            with torch.inference_mode():
                out = model.generate(**inputs, max_new_tokens=60, do_sample=False)
            desc = processor.batch_decode(
                out[:, inputs.input_ids.shape[1] :], skip_special_tokens=True
            )[0]
            desc = " ".join(desc.split()).strip().strip('"').rstrip(".")[:220]
            if desc:
                w["desc"] = desc
                dirty.add(mp)
        except Exception as e:
            print(f"  !! {w['id']}: {e}", flush=True)
            continue

        rate = (time.time() - t0) / n
        eta_min = int(rate * (len(work) - n) / 60)
        print(f"[{n}/{len(work)} ~{eta_min}m left] {w['brand']} {w['model']}: {desc[:80]}", flush=True)
        if n % 25 == 0:
            save(dirty)
            dirty.clear()

    save(dirty)
    print(f"DONE: {len(work)} wheels described in {int((time.time()-t0)/60)} min", flush=True)
    print("Start the app again (start.bat) to use the new descriptions.", flush=True)


if __name__ == "__main__":
    main()
