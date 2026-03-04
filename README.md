# Yosuki Motion Graphics Pipeline

**Campaign:** Find Your Sound — Spring 2026 Performance Campaign
**Client:** Yosuki Musical Instrument Corporation

A fully automated Python pipeline that generates 112 localized video ad renders across 4 markets, 10 product variants, and 3 aspect ratios — driven from a single creative brief file and controlled through a Streamlit dashboard.

---

## What This Pipeline Does

```
Cinema 4D  →  ComfyUI Flux Canny  →  Claude API  →  After Effects  →  Google Drive
(C4D render)  (scene backgrounds)   (copy gen.)    (compositing)     (delivery)
```

| Step | Script | What It Does |
|------|--------|-------------|
| C4D Render | Manual / Dashboard | Renders greyscale scene reference images per product group |
| ComfyUI — US | `scripts/02_generate_backgrounds.py` | Generates 27 US backgrounds (1 per product+ratio) via Flux Canny ControlNet |
| ComfyUI — Intl | `scripts/02a_02a_generate_intl_backgrounds.py` | Generates 9 international backgrounds (3 scenes × 3 markets) |
| Copy Preview | `scripts/02b_generate_copy_preview.py` | Claude generates US CTAs + translates all copy to JP/DE/BR |
| Apply Copy | `scripts/02c_apply_copy_preview.py` | Writes approved copy to variants.json and creates 84 intl variants |
| AE Render | `scripts/03_populate_templates.py` | Populates templates + renders all variants in one aerender call |
| Deliver | `scripts/05_deliver.py` | Organizes output + uploads to Google Drive |

---

## Output

| Market | Language | Renders |
|--------|---------|---------|
| US | English | 28 |
| JP | Japanese | 28 |
| DE | German | 28 |
| BR | Brazilian Portuguese | 28 |
| **Total** | | **112** |

**Products:** Signature Saxophone · Grand / Upright / Digital Piano · Paulie / San Jose SJ / Stratoblaster Guitar (Black + Blue-burst)
**Ratios:** 970×250 Billboard · 16:9 · 1:1 *(pianos: billboard + 16:9 only)*

---

## Dashboard

The pipeline can be fully controlled from the Streamlit dashboard:

```bash
streamlit run dashboard.py
```

**Dashboard features:**
- Step-by-step pipeline controls (C4D → ComfyUI → Copy → AE Render → Deliver)
- **Run Full Pipeline** button — runs all selected steps in sequence with a progress bar
- ComfyUI background preview (US and international tabs per market)
- Copy preview table before applying
- Per-variant preview player
- All 112 variants in a searchable, filterable table

---

## Quick Start

### Prerequisites

- Python 3.10+
- After Effects 2026 (with `aerender.exe`)
- Cinema 4D 2026 (for C4D scene renders)
- ComfyUI running locally at `http://127.0.0.1:8188` with Flux + Canny ControlNet
- Claude API key (`https://console.anthropic.com`)

### Setup

```bash
# 1. Clone this repo
git clone https://github.com/YOUR_USERNAME/yosuki-pipeline.git
cd yosuki-pipeline

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Copy and fill in your API key
cp .env.example .env
# Edit .env:
#   ANTHROPIC_API_KEY=sk-ant-...
#   GOOGLE_DRIVE_FOLDER_ID=1abc...  (optional — leave blank to skip Drive upload)

# 4. Verify paths in config.py
#   AERENDER_PATH — path to aerender.exe (default is correct for AE 2026)
#   COMFYUI_URL   — default http://127.0.0.1:8188
```

### Build AE Templates (one-time manual step)

See `ae_templates/README.md` for layer naming requirements and animation structure.

### Export ComfyUI Workflow (one-time)

See `comfyui_workflows/README.md` for the Flux Canny ControlNet workflow setup.

### Run the Pipeline

**Via dashboard (recommended):**
```bash
streamlit run dashboard.py
```

**Via command line:**
```bash
# US market only (28 renders)
python run_pipeline.py --market US

# Full run — all 4 markets (112 renders)
python run_pipeline.py

# Resume from a specific step
python run_pipeline.py --from-step 03

# Skip Google Drive upload
python run_pipeline.py --no-drive
```

---

## File Structure

```
yosuki-pipeline/
├── brief.json                    ← Edit this per campaign (products, markets, copy rules)
├── config.py                     ← Edit once: paths + API config
├── dashboard.py                  ← Streamlit dashboard (run with: streamlit run dashboard.py)
├── run_pipeline.py               ← CLI entry point for the full pipeline
├── requirements.txt
│
├── scripts/
│   ├── 00_prep_assets.py             rembg background removal from product PNGs
│   ├── 01_generate_copy.py           Claude API copy generation (legacy single-step)
│   ├── 02_generate_backgrounds.py    ComfyUI US backgrounds (Flux Canny, 27 images)
│   ├── 02b_generate_copy_preview.py      Claude API copy preview (US CTAs + intl translation)
│   ├── 02c_apply_copy_preview.py         Apply preview → variants.json, create intl variants
│   ├── 02a_generate_intl_backgrounds.py  ComfyUI intl backgrounds (9 images, 3 scenes × 3 markets)
│   ├── 03_populate_templates.py      AE template population + aerender in one step
│   ├── 05_deliver.py                 Organize output + Google Drive upload
│   └── utils/
│       ├── logger.py                 Coloured terminal output
│       └── validate.py               brief.json validation
│
├── extendscript/
│   └── zz_yosuki_populate.jsx    Installed in AE Scripts/Startup — fires on every aerender call
│
├── ae_templates/
│   ├── landscape_16.9.aep        16:9 template (1920×1080)
│   ├── square_1x1.aep            1:1 template (1080×1080)
│   ├── billboard_970x250.aep     Billboard template (2910×750, 3× for sharpness)
│   └── README.md                 How to build and configure the templates
│
├── comfyui_workflows/
│   ├── flux_canny_model_example.json   Active workflow — Flux Canny ControlNet
│   └── README.md                       Workflow setup guide
│
├── assets/
│   └── product_cutouts/          Transparent PNGs from rembg (auto-filled by step 00)
│
└── output/
    ├── variants.json             Auto-generated — all 112 variants + status tracking
    ├── copy_preview.json         Temporary — generated copy awaiting review/apply
    ├── backgrounds/              ComfyUI-generated images (27 US + 9 intl = 36 total)
    ├── projects/                 Copied .aep files + data JSONs (one per variant)
    ├── renders/                  Raw MP4 renders (112 files)
    └── delivery/                 Final organized output
        ├── US/
        ├── JP/
        ├── DE/
        └── BR/
```

---

## Configuration

All machine-specific paths live in `config.py`:

```python
AERENDER_PATH = r"C:\Program Files\Adobe\Adobe After Effects 2026\Support Files\aerender.exe"
COMFYUI_URL   = "http://127.0.0.1:8188"
AE_MAIN_COMP_NAME  = "MAIN_COMP"
AE_OUTPUT_MODULE   = "H.264 - Match Render Settings - 15 Mbps"
```

API keys go in `.env` (never commit this file):
```
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_DRIVE_FOLDER_ID=1abc...   # Optional — leave blank to skip Drive upload
```

---

## How Copy Generation Works

### US Market — Locked taglines, Claude generates CTA

Taglines for the US market are locked in `brief.json` under the `families` key:

| Family | Locked US Tagline |
|--------|------------------|
| Saxophone | Own the stage |
| Pianos | Crafted for Generations |
| Guitars | Play Loud |

Claude generates only the **CTA** for US. This keeps brand voice consistent across all US variants.

### International Markets — Claude translates + culturally adapts

For JP, DE, BR: Claude receives the locked US tagline + CTA and produces a **culturally adapted** version — not a literal translation. Each market has a `visual_culture` and `tone` defined in `brief.json` that guides this.

| Market | Tone |
|--------|------|
| JP | Respectful, refined, craftsmanship-focused |
| DE | Precision, engineering excellence. Shorter phrasing (compound words). |
| BR | Emotional, energetic, expressive |

The two-step copy flow (preview → apply) lets you review the copy before it gets written into `variants.json`.

---

## How Backgrounds Work

### US backgrounds (27 images)
One background per product+ratio combo. Generated via Flux Canny ControlNet using the product's C4D render as the ControlNet input. Prompt comes from `comfyui_prompt` in `variants.json` (written by Claude based on the brief's scene direction).

### International backgrounds (9 images)
One background per **scene family** per market: `{scene}_{market}_16x9.png`

| Scene | C4D Source Render | Markets |
|-------|------------------|---------|
| `sax` | `saxophone_model1_16x9_014.png` | JP, DE, BR |
| `piano` | `piano_grand_16x9_008.png` | JP, DE, BR |
| `guitar` | `guitar_16x9_001.png` | JP, DE, BR |

Each intl background uses the same C4D ControlNet input as US but appends the market's `visual_culture` from `brief.json` to the prompt (e.g. "Japanese minimalist aesthetic, soft diffused natural light...").

International backgrounds are **shared across all products in that scene family** — e.g. `guitar_JP_16x9.png` is used for all 6 guitar variants in the JP market.

**Fallback:** If an international background doesn't exist, `03_populate_templates.py` automatically falls back to the US product background.

---

## How AE Rendering Works

`03_populate_templates.py` combines template population and rendering into one `aerender.exe` call:

1. Copies the correct `.aep` template to `output/projects/{variant_id}.aep`
2. Writes `output/projects/{variant_id}_data.json` (copy + asset paths)
3. Calls `aerender.exe -project ... -comp MAIN_COMP -output ...`
4. `zz_yosuki_populate.jsx` (in AE's Scripts/Startup) fires automatically when the project opens
5. The JSX reads the data JSON, sets text layers, relinks footage, then aerender renders

**Why combined in one call:** Separating populate and render into two aerender calls would cause AE to re-resolve footage from the original template paths when loading the saved file. The combined approach modifies footage in memory and renders before AE ever touches the file system again.

---

## Crash Recovery

Every script updates a `status` field in `output/variants.json`:

| Status | Meaning |
|--------|---------|
| `pending` | Copy not yet generated |
| `copy_generated` | Copy applied and ready to render |
| `rendered` | MP4 render complete |
| `delivered` | File copied to output/delivery/ and uploaded to Drive |

If the pipeline stops, re-run the same command — completed variants are automatically skipped. To force a market to re-render (even if already rendered), use `--market JP` which resets that market's status before rendering.

---

## Architecture Notes

**Why backgrounds are shared across markets:**
The visual background (e.g. the jazz club for saxophone) looks the same regardless of whether the copy says "Own the stage" or "舞台に立て". 27 US backgrounds + 9 international backgrounds serve all 112 renders.

**Why international has its own backgrounds:**
International backgrounds get the market's `visual_culture` appended to the prompt, subtly adapting the scene (e.g. Japanese market gets cooler, more minimalist lighting; Brazilian market gets warmer, more saturated tones).

**Why ExtendScript instead of MOGRT:**
After Effects Essential Graphics (MOGRTs) cannot relink footage files programmatically — only text. `zz_yosuki_populate.jsx` uses ExtendScript to both set text AND relink the background and product images in one pass, without needing to save and reload the project.

**Why Python as orchestrator:**
No server to run (unlike n8n/Make), plain text files readable on GitHub, all tools (ComfyUI, aerender, Claude API) have Python support built-in.
