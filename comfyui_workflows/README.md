# ComfyUI Workflow — Flux Canny ControlNet

The pipeline uses **Flux Canny ControlNet** to generate backgrounds. A Cinema 4D greyscale render is used as the ControlNet image — Canny edge detection extracts the structural lines from the C4D render, and Flux uses those edges to ensure the generated background matches the scene composition.

---

## Active Workflow File

**`flux_canny_model_example.json`** — this is the workflow used for both US backgrounds and international backgrounds.

Export from ComfyUI in **API format** (not the default save format). In ComfyUI, go to Settings → enable Dev Mode → use "Save (API Format)".

---

## How It Works

```
C4D render (PNG)
       ↓
  /upload/image  ← uploaded via ComfyUI REST API
       ↓
  LoadImage (node 17)
       ↓
  Canny edge detection (node 18) — extracts structural outlines
       ↓
  Flux Canny ControlNet
       ↓
  Sampler (node 3) ← guided by canny edges + text prompt (node 23)
       ↓
  SaveImage (node 9) → output PNG
```

The Canny edge map preserves the spatial composition of the C4D scene — floor plane, perspective, object placement — while Flux generates the photorealistic background freely within those constraints.

---

## Node Map

| Node ID | Type | Purpose | Injected by Python? |
|---------|------|---------|-------------------|
| `3` | KSampler / SamplerCustom | Runs diffusion, seed set per job | ✅ seed, steps |
| `9` | SaveImage | Saves output PNG | ✅ filename_prefix |
| `17` | LoadImage | Loads the C4D render | ✅ image filename |
| `18` | Canny | Extracts edges from C4D render | ✅ low_threshold, high_threshold |
| `23` | CLIPTextEncode | Scene description prompt | ✅ text |
| `26` | FluxGuidance / BasicGuider | Guidance scale | — |

---

## Canny Threshold Settings

The pipeline uses these values (set in `02a_generate_intl_backgrounds.py` and `02_generate_backgrounds.py`):

```python
low_threshold  = 0.05   # picks up fine detail edges
high_threshold = 0.1    # keeps lines without too much noise
```

Lower values = more edges captured = tighter compositional constraint.
Higher values = fewer edges = more creative freedom for Flux.

---

## C4D Source Renders (ControlNet inputs)

Three C4D renders are used as ControlNet inputs, one per scene family:

| Scene | C4D Render File |
|-------|----------------|
| Saxophone | `F:/Adobe_FDE Take-Home/Assets/renders/saxophone_model1_16x9_014.png` |
| Piano | `F:/Adobe_FDE Take-Home/Assets/renders/piano_grand_16x9_008.png` |
| Guitar | `F:/Adobe_FDE Take-Home/Assets/renders/guitar_16x9_001.png` |

These are the greyscale staged renders from Cinema 4D — no colour, no textures. The clean structure gives Canny clean edges to work with.

---

## US Backgrounds vs International Backgrounds

### US (27 images)

- Script: `scripts/02_generate_backgrounds.py`
- One background per `{product_id}_{ratio}` combo
- Prompt: the `comfyui_prompt` from `variants.json` (written by Claude based on brief scene direction)
- Output: `output/backgrounds/{product_id}_{ratio}.png`

### International (9 images)

- Script: `scripts/02a_generate_intl_backgrounds.py`
- One background per scene per market: `{scene}_{market}_16x9.png`
- Prompt: US scene prompt + market `visual_culture` from `brief.json`
- C4D render uploaded fresh for each job
- Output: `output/backgrounds/sax_JP_16x9.png`, `piano_DE_16x9.png`, etc.
- `--market JP` flag to run a single market only
- `--force` flag to regenerate even if file exists

---

## Running from the Dashboard

Step 2 in the dashboard has two tabs:
- **US Backgrounds** — previews current US backgrounds, button to regenerate
- **International Backgrounds** — per-market tabs with previews and "Generate new variation" button

The "Generate new variation" button deletes the existing files for that market and re-runs `02a_generate_intl_backgrounds.py --market {mkt}` to get fresh Flux outputs.

---

## Required ComfyUI Setup

### Model
Flux must be installed and loaded. The workflow references Flux model files — verify these are in your ComfyUI `models/` folder.

### Canny ControlNet
The Flux Canny ControlNet model must be installed. The workflow references it by name — check your `models/controlnet/` folder matches what's in `flux_canny_model_example.json`.

### Output directory
ComfyUI saves generated PNGs to its own output folder (set via `COMFYUI_OUTPUT_DIR` in `.env`, default: `G:/ComfyUI/output`). The pipeline uses `find_output(prefix)` to locate the latest file matching the job prefix and copies it to `output/backgrounds/`.

If your ComfyUI output directory is different, update `COMFYUI_OUTPUT_DIR` in `scripts/02a_generate_intl_backgrounds.py`.
