# After Effects Templates

## Three Templates

| Filename | Dimensions | Use Case |
|----------|-----------|----------|
| `landscape_16.9.aep` | 1920 × 1080 px | 16:9 video ad |
| `square_1x1.aep` | 1080 × 1080 px | Square social ad |
| `billboard_970x250.aep` | 2910 × 750 px | Billboard (3× for sharpness — scales to 970×250) |

Build `landscape_16.9.aep` first and test it fully, then duplicate and resize for the others.

---

## Required: Exact Layer Names

The pipeline finds layers **by name**. These must be **exactly** as shown (case-sensitive):

| Layer Name | Layer Type | Phase Visible | Notes |
|-----------|-----------|--------------|-------|
| `BG_IMAGE_PLACEHOLDER` | Footage | All phases | Relinked to ComfyUI background (PNG or MP4) |
| `PRODUCT_IMAGE_PLACEHOLDER` | Footage | Phases 1–2 | Relinked to product cutout PNG |
| `PRODUCT_CONSTRAIN` | Solid | Not rendered | Red constraint box — guitars are scaled/positioned to fit inside this |
| `SERIES_TITLE_TEXT` | Text | Phase 2 only | e.g. "Signature Series Saxophone" |
| `TAGLINE_TEXT` | Text | Phase 2 only | e.g. "Own the stage" |
| `CTA_TEXT` | Text | Phase 3 only | e.g. "Find Your Sound" |
| `LOGO` | Footage | Phase 3 only | logo.png — static, not relinked |

**Main composition name:** `MAIN_COMP` — aerender and the JSX both look for this exact name.

---

## PRODUCT_CONSTRAIN Solid

Guitar products use a **constrain box** to control product placement. `PRODUCT_CONSTRAIN` is a coloured solid (typically red for visibility) that defines the safe area where the guitar image should sit. It is **not rendered** — the JSX reads its position and size at render time, then scales and centers `PRODUCT_IMAGE_PLACEHOLDER` to fit inside it.

Non-guitar products (saxophone, pianos) do not use the constrain box — the JSX scales them using a multiplier instead.

---

## 3-Phase Animation Structure

```
0s ─────────────── 2-3s ─────────────── 6-7s ─────────────── 9-10s
│                   │                    │                    │
│   PHASE 1         │    PHASE 2         │    PHASE 3         │
│   Scene Hold      │    Copy Reveal     │    CTA State       │
│                   │                    │                    │
│  BG + Product     │  BG + Product      │    Logo only       │
│  (no text)        │  + Tagline         │    + CTA text      │
│                   │  + Series Title    │    (product fades) │
```

### Phase 1 — Scene Hold (~2-3 seconds)
- Background image fills the frame
- Product animates in (scale/fade from nothing, or slide in)
- No text — let the image breathe

### Phase 2 — Copy Reveal (~3-4 seconds)
- `SERIES_TITLE_TEXT` fades/slides in
- `TAGLINE_TEXT` fades/slides in shortly after (stagger 3-5 frames)
- Product stays visible

### Phase 3 — CTA State (~2-3 seconds)
- Background and product animate out (fade or scale down)
- `LOGO` fades in
- `CTA_TEXT` fades in next to or below the logo
- Clean and minimal — this is the click moment

---

## How the JSX Population Works

**`zz_yosuki_populate.jsx`** lives in:
```
C:\Program Files\Adobe\Adobe After Effects 2026\Support Files\Scripts\Startup\
```

Because it's in AE's **Startup** folder, it runs automatically every time `aerender.exe` opens a project. It wraps `AddCompToRenderQueue` so it fires just before rendering begins.

What the JSX does for each render:
1. Finds the `{variant_id}_data.json` file sitting next to the opened `.aep`
2. Sets the source text on `SERIES_TITLE_TEXT`, `TAGLINE_TEXT`, and `CTA_TEXT`
3. Relinks `BG_IMAGE_PLACEHOLDER` to the background PNG/MP4
4. Relinks `PRODUCT_IMAGE_PLACEHOLDER` to the product cutout PNG
5. Scales and positions `PRODUCT_IMAGE_PLACEHOLDER`:
   - **Guitars:** fits inside `PRODUCT_CONSTRAIN` box (contain scaling + position snap + optional Y offset)
   - **Pianos:** applies `product_scale_multiplier` (1.1 = 10% larger than template default)
   - **Saxophone:** uses AE template default scale

The data JSON is written by `03_populate_templates.py` before aerender is called.

---

## Footage Placeholder Setup

For `BG_IMAGE_PLACEHOLDER` and `PRODUCT_IMAGE_PLACEHOLDER`:
1. Import any PNG as a placeholder (a solid or a dummy image works)
2. Name the imported footage item the same as the layer name for clarity
3. Add it to the comp — the JSX relinks it to the real asset at render time

For `LOGO`: import `fde_asset_bundle/logo.png` directly — this one is never relinked.

For `PRODUCT_CONSTRAIN`: add a coloured solid at the size and position where you want guitars to sit. The JSX reads `.width`, `.height`, `.position` from this layer.

---

## Testing the JSX Manually

To test one variant without running the full pipeline:

1. Copy a template to `output/projects/test_variant.aep`
2. Write a `test_variant_data.json` next to it (see any existing `_data.json` in that folder for the format)
3. Open After Effects
4. File → Scripts → Run Script File → select `extendscript/zz_yosuki_populate.jsx`

Or trigger via aerender to test the full pipeline path:
```
aerender.exe -project output/projects/test_variant.aep -comp MAIN_COMP -output output/renders/test_variant.mp4 -OMtemplate "H.264 - Match Render Settings - 15 Mbps" -v ERRORS
```

---

## Tips

- For the **billboard** (2910×750), text size should be proportionally larger — it's a long, thin format. Billboard-specific guitar scale overrides are set in `03_populate_templates.py`.
- If a font doesn't support Japanese characters, you'll see squares in JP renders. Test a JP variant first in AE manually before batch rendering.
- German text can produce long compound words — after rendering DE variants, spot-check that text isn't getting clipped.
