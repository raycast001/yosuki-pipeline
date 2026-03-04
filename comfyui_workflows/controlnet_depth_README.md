# Flux Canny ControlNet — C4D Digital Twin Pipeline

This documents the ControlNet approach used to generate backgrounds from Cinema 4D renders.

The pipeline uses **Canny edge detection** (not depth maps) as the ControlNet conditioning signal. The C4D render's structural outlines guide Flux to generate a background that respects the scene composition — perspective, floor plane, object placement.

---

## How It Works

```
Cinema 4D                    ComfyUI                         After Effects
─────────────────────        ──────────────────────────────  ─────────────────────
Greyscale scene render  →    Upload via /upload/image     →  BG_IMAGE_PLACEHOLDER
(no textures, no colour)     ↓                               relinked to output
                             Canny edge extraction (node 18)
                             ↓
                             Flux ControlNet generation
                             guided by canny edges + prompt
                             ↓
                             SaveImage → output/backgrounds/
```

1. **Cinema 4D** renders a clean greyscale staged scene (no product, no textures — just lighting + geometry)
2. The render is uploaded to ComfyUI via the `/upload/image` API endpoint
3. **Canny edge detection** (node 18) extracts structural outlines from the C4D render
4. **Flux Canny ControlNet** uses those edges to constrain background generation to match the scene layout
5. The generated background is saved and linked into After Effects as `BG_IMAGE_PLACEHOLDER`

---

## Canny vs Depth — Why Canny

An earlier version of this pipeline explored **Flux Depth ControlNet** (DepthAnythingV2), which extracts a spatial depth map from the C4D render. While depth provides strong spatial structure, Canny was adopted instead because:

- Canny edges are directly readable from the greyscale C4D renders without preprocessing
- The pipeline does not need to install `ComfyUI-ControlNet-Aux` custom nodes
- Results are more consistent across the 3 scene types (jazz club, concert hall, warehouse)
- Canny thresholds are easy to tune (low: 0.05, high: 0.1 = crisp structural lines without noise)

---

## Workflow File

**`flux_canny_model_example.json`** — export from ComfyUI in API format.

### Node Map

| Node ID | Type | Role | Set by Python |
|---------|------|------|--------------|
| `3` | KSampler | Runs diffusion | ✅ seed, steps |
| `9` | SaveImage | Saves output PNG | ✅ filename_prefix |
| `17` | LoadImage | Loads C4D render | ✅ image filename |
| `18` | Canny | Extracts edges from C4D render | ✅ low_threshold (0.05), high_threshold (0.1) |
| `23` | CLIPTextEncode | Scene description prompt | ✅ text |
| `26` | FluxGuidance | Guidance conditioning | — |

---

## C4D Render Requirements

The C4D renders used as ControlNet inputs:

| Scene | File |
|-------|------|
| Saxophone | `F:/Adobe_FDE Take-Home/Assets/renders/saxophone_model1_16x9_014.png` |
| Piano | `F:/Adobe_FDE Take-Home/Assets/renders/piano_grand_16x9_008.png` |
| Guitar | `F:/Adobe_FDE Take-Home/Assets/renders/guitar_16x9_001.png` |

**Best practices for C4D renders used with Canny ControlNet:**
- Render at 1920×1080 (16:9) — Flux handles this resolution natively
- Remove all textures — solid greyscale geometry gives Canny the cleanest edges
- Keep the product out of the render — only the stage/environment geometry
- Use the same camera angle as your AE composition

---

## Tuning Canny Thresholds

`low_threshold` and `high_threshold` control how many edges Canny picks up:

| low / high | Effect |
|-----------|--------|
| 0.03 / 0.08 | More edges — very tight spatial constraint, detailed structure |
| **0.05 / 0.10** | **Default — balanced: clear structure, room for Flux creativity** |
| 0.10 / 0.20 | Fewer edges — looser constraint, more creative variation |
| 0.15 / 0.30 | Very loose — only the strongest lines retained |

These are set in `02a_generate_intl_backgrounds.py`:
```python
wf[NODE["canny"]]["inputs"]["low_threshold"]  = 0.05
wf[NODE["canny"]]["inputs"]["high_threshold"] = 0.1
```

---

## Known Constraints

**Flux image dimensions**
Flux requires both width and height to be divisible by 8 (some versions require 16). The pipeline generates at 1920×1080 which satisfies this. If you encounter generation errors, try 1920×1088.

**ComfyUI output directory**
The pipeline looks for completed images in the path set by `COMFYUI_OUTPUT_DIR` (defaults to `G:/ComfyUI/output`). If your ComfyUI saves elsewhere, set `COMFYUI_OUTPUT_DIR` in your `.env` file.

**Upload deduplication**
ComfyUI's `/upload/image` endpoint accepts `overwrite: true`. The pipeline uploads the same C4D render for every job in a batch (e.g. sax_JP, sax_DE, sax_BR all use the same C4D render). The overwrite flag ensures the latest upload is always used.
