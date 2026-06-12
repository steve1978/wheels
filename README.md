# Wheels 🚗🎨

**AI car colour & wheel visualizer — runs 100% locally on your own GPU.**

Upload a photo of a car (or pick a sample), then:

- 🎨 **Respray it any colour** — 16 presets or a full colour wheel, photorealistic
- ✨ **Pick a paint finish** — gloss, metallic, matte, satin or pearlescent
- 🛞 **Fit real alloy wheels** — 2,600+ genuine products across 50+ brands (BBS,
  OZ Racing, Rota, Borbet, Bola, Japan Racing…); the AI copies the actual wheel
  from its product photo onto your car
- 📏 **Wheel size slider (17–24")** — each size renders once, then scrubs instantly;
  one click pre-renders the whole range
- 🎲 **Roll the dice** — random colour + random wheels, instantly rendered
- 📱 Works on desktop and phones, with a before/after compare slider
- 🌍 Optional one-click public share link so friends can use it from anywhere

No cloud, no API keys, no subscriptions — your photos never leave your machine
(unless you turn on the share link).

## Requirements

| | |
|---|---|
| **GPU** | NVIDIA with **16GB+ VRAM** (24GB recommended, e.g. RTX 3090/4090/5090) |
| **OS** | Windows 10/11 with a current NVIDIA driver |
| **Disk** | ~40GB free (AI model ~30GB, downloaded automatically on first run) |
| **Software** | Python 3.10–3.12 and Node.js — *start.bat checks and offers to install both* |

## Quick start

```
git clone <this repo>
cd Wheels
```

**Double-click `start.bat`.** That's it. Three scripts run everything:

| Script | What it does |
|---|---|
| `start.bat` | Start the app locally (first run also installs everything) |
| `share.bat` | Add a public link to the running app (Cloudflare tunnel; never starts a second copy) |
| `stop.bat` | Switch everything off, including the public link |

On first run, `start.bat` will:

1. Check your GPU, Python and Node.js (offering to install what's missing)
2. Create the Python environment and install PyTorch + libraries (~3GB)
3. Build the web interface
4. Fetch the wheel catalog product images
5. Download the AI model from HuggingFace (~30GB — one time only)
6. Open the app at http://localhost:3000

Later runs skip all of that and start in seconds. **Double-click `stop.bat`** to
shut everything down.

## How it works

```
Next.js frontend ──proxy──> FastAPI backend ──> Qwen-Image-Edit-2511 (CUDA)
 colour wheel, finishes,     async render queue    GGUF Q4 transformer (~12GB)
 wheel catalog browser,      (FIFO, positions      4-bit text encoder
 compare slider, dice        shown in the UI)      Lightning 4-step LoRA
```

- **Instruction-based editing** — selections become an edit instruction like
  *“repaint the car body in matte deep blue, and replace the wheels with the BBS
  LeMans shown in the first image”*; no masks or manual selection needed.
- **Real-wheel swaps** use the model's multi-image mode: your car photo plus the
  wheel's product photo go in together and the design transfers across (~20-30s).
  Plain colour/finish edits take ~15s on an RTX 4090.
- **One render at a time** — a FIFO queue serializes GPU work; everyone sees
  their queue position live.

## Refreshing the wheel catalog

```powershell
cd backend
.venv\Scripts\python.exe scrape_all.py        # every brand on wheelmania.co.uk
# or one brand:
.venv\Scripts\python.exe scrape_catalog.py https://wheelmania.co.uk/alloy-wheels/rotiform/ rotiform "Rotiform"
```

Restart the backend and new brands appear in the dropdown.

## Notes & credits

- Wheel product imagery is fetched at setup time from [Wheelmania](https://wheelmania.co.uk)
  and remains the respective manufacturers'/retailer's copyright — it is **not**
  redistributed with this repo and is for personal/local use only.
- Model: [Qwen-Image-Edit-2511](https://huggingface.co/Qwen/Qwen-Image-Edit-2511)
  (Apache-2.0) with the [Lightning LoRA](https://huggingface.co/lightx2v/Qwen-Image-Edit-2511-Lightning)
  and [Unsloth GGUF quants](https://huggingface.co/unsloth/Qwen-Image-Edit-2511-GGUF).
- The optional share link uses a [Cloudflare quick tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/):
  no ports are opened on your router and the random URL rotates each start —
  but anyone who has the link can submit renders while it's up.

## License

MIT — see [LICENSE](LICENSE).
