# Workflow Review & Discussion Guide — 20–30 Minutes
## Running and Explaining the Code

---

## Structure

| Block | Time | Focus |
|-------|------|-------|
| Repo tour | 3 min | Folder structure, how it's organised |
| config.py + brief.json | 4 min | The two files that drive everything |
| US pipeline walkthrough | 15 min | Each script for the US market, in order |
| Live run (skip flags) | 4 min | Actually run the pipeline, explain the flags |
| International extension | 3 min | How the same pipeline extends to JP/DE/BR |

---

## Block 1 — Repo Tour (3 min)

**Open the repo root and talk through the structure:**

```
yosuki-pipeline/
├── config.py               ← single source of truth for all paths
├── brief.json              ← creative brief — the only file you edit per campaign
├── run_pipeline.py         ← CLI runner for the full pipeline
├── dashboard.py            ← Streamlit UI
├── .env                    ← machine paths (gitignored)
├── .env.example            ← template for new machines
│
├── scripts/
│   ├── 00_prep_assets.py              ← rembg background removal (run once)    ← CORE
│   ├── 01_generate_copy.py            ← bootstraps variants.json from brief    ← CORE
│   ├── 02_generate_backgrounds.py     ← US backgrounds via ComfyUI             ← CORE
│   ├── 02b_generate_copy_preview.py   ← re-generate/preview copy via Claude    ← CORE
│   ├── 02c_apply_copy_preview.py      ← write approved copy to variants.json   ← CORE
│   ├── 03_populate_templates.py       ← AE population + aerender               ← CORE
│   ├── 05_deliver.py                  ← organise output                        ← CORE
│   │
│   ├── 02a_generate_intl_backgrounds.py  ← international extension
│   └── archive/                          ← dev experiments
│
├── ae_templates/           ← one .aep per aspect ratio (16x9, 1x1, billboard)
├── extendscript/           ← JSX scripts run inside After Effects
├── comfyui_workflows/      ← workflow JSON + documentation
│
└── output/
    ├── variants.json        ← tracked in git — 112 variant states + all copy
    ├── copy_preview.json    ← staging file for copy review
    ├── backgrounds/         ← gitignored (generated images)
    ├── projects/            ← gitignored (populated .aep copies)
    └── renders/             ← gitignored (final .mp4 files)
```

**Key point:**
> "The `output/` folder is mostly gitignored — the renders are too large for git. But `variants.json` and `copy_preview.json` are tracked, because they show the pipeline's state: all 112 variants, their copy in 4 languages, their render status. Anyone cloning the repo can see exactly what the pipeline produced."

---

## Block 2 — config.py + brief.json (4 min)

### config.py

Open `config.py` and walk through the pattern:

```python
# Every machine-specific value loads from .env, with a sensible fallback
AERENDER_PATH      = os.getenv("AERENDER_PATH", r"C:\Program Files\Adobe\...")
COMFYUI_OUTPUT_DIR = Path(os.getenv("COMFYUI_OUTPUT_DIR", "G:/ComfyUI/output"))
C4D_RENDERS = {
    "sax":   C4D_RENDERS_DIR / os.getenv("C4D_RENDER_SAX", "saxophone_...png"),
    "piano": C4D_RENDERS_DIR / os.getenv("C4D_RENDER_PIANO", "piano_...png"),
    "guitar":C4D_RENDERS_DIR / os.getenv("C4D_RENDER_GUITAR", "guitar_...png"),
}
```

> "config.py is the only file that knows about your machine. Every other script imports from here — no script has any hardcoded path. The pattern is: load from `.env`, fall back to a sensible default so the existing setup still works without a `.env`. New machine: copy `.env.example` → `.env`, fill in your paths, done."

### brief.json

Open `brief.json` and walk through the key sections:

```json
{
  "products": [
    {
      "product_id": "sax_alto_pro",
      "model": "Alto Pro",
      "series": "Prestige",
      "key_message": "...",
      "vibe": "...",
      "comfyui_prompt": "moody jazz club, stage lighting, warm amber..."
    }
  ],
  "families": [
    {
      "id": "saxophone",
      "label": "Prestige Saxophone Series",
      "us_tagline": "Own the Stage",
      "product_ids": ["sax_alto_pro", "sax_tenor_elite", ...]
    }
  ],
  "markets": [...],
  "brand_pillars": "Japanese craftsmanship, professional-grade performance..."
}
```

> "This is the creative brief as data. The `comfyui_prompt` on each product is the scene description for Flux. The `us_tagline` on each family is locked — that's the creative director's decision, Claude never touches it. The `brand_pillars` field gets passed to Claude in every copy prompt as brand guardrails."

> "If a new product launches, I add one object to the `products` array and one product_id to its family. Re-run. Done."

---

## Block 3 — US Pipeline Walkthrough (15 min)

Go through each script in pipeline order. **Stay on US market throughout.**

---

### 00_prep_assets.py — Product Cutouts (1 min)

> "Run once per product launch. It uses rembg — an open-source ML background removal library — to create transparent PNG cutouts from the product photos. The cutouts go into `assets/product_cutouts/`. After Effects then composites them over the generated backgrounds."

No need to run this live — just explain it exists and point to the cutouts folder.

---

### 01_generate_copy.py — Bootstrap variants.json (2 min)

This is the script that starts everything. Before it runs, there is no pipeline state — no list of variants, no copy, no statuses. After it runs, `variants.json` exists and every downstream script has something to work from.

**What it does in two phases:**

**Phase 1 — Build the variant list:**
```python
def build_variants_list(brief: dict) -> list[dict]:
    for product in brief["products"]:
        for ratio in product["aspect_ratios"]:
            for market in brief["markets"]:
                variants.append({
                    "variant_id":     f"{product_id}_{market_id}_{ratio}",
                    "product_id":     product["product_id"],
                    "market":         market["id"],
                    "ratio":          ratio,
                    "tagline":        "",   # filled in by Claude below
                    "cta":            "",
                    "comfyui_prompt": "",
                    "status":         "pending",
                })
```

> "It's a triple nested loop: every product × every ratio × every market. That's how you get from 10 products to 112 variants. Each variant starts with empty copy fields and status 'pending' — Claude fills those in next."

**Phase 2 — Fill copy via Claude:**
```python
# One API call for the whole batch — more efficient than one call per variant
prompt = build_claude_prompt(brief, variants)
response = claude.messages.create(model=CLAUDE_MODEL, messages=[{"role":"user","content":prompt}])
# Parse and validate — taglines over 6 words or CTAs over 4 words trigger a retry
```

> "One Claude API call for the entire batch — not one per variant. Claude gets the full brief, all 10 products, all 4 markets, and returns a JSON array with copy for every combination. Then there's a validation pass: if any tagline is over 6 words or any CTA is over 4 words, it retries just that row, up to 3 times. Validated copy gets written into variants.json."

**The relationship between 01 and 02b/02c:**

> "01_generate_copy.py runs once to bootstrap the pipeline. The 02b/02c scripts are for iteration — if you want to refine the copy after seeing it, or re-run just the CTAs, you use 02b to get a new Claude preview and 02c to apply it. They're not a replacement for 01, they're the edit layer on top of it."

---

### 02_generate_backgrounds.py — US Backgrounds (3 min)

Open the script. Show the two key functions:

**The upload step:**
```python
# Upload the C4D render to ComfyUI so the workflow can reference it
with open(c4d_render_path, "rb") as f:
    requests.post(f"{COMFYUI_URL}/upload/image",
                  files={"image": f},
                  data={"overwrite": "true"})
```

**The inject-and-queue step:**
```python
# Load the workflow JSON, inject job-specific values, POST to /prompt
wf = json.loads(workflow_template)
wf[NODE["prompt"]]["inputs"]["text"]               = prompt
wf[NODE["load_image"]]["inputs"]["image"]           = uploaded_filename
wf[NODE["canny"]]["inputs"]["low_threshold"]        = 0.05
wf[NODE["canny"]]["inputs"]["high_threshold"]       = 0.1
wf[NODE["save_image"]]["inputs"]["filename_prefix"] = prefix
requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": wf})
```

> "The ComfyUI workflow is just a JSON file — the graph exported in API format. The Python reads it, injects the values for this specific job — the Flux prompt, the C4D render filename, the Canny thresholds, the output prefix — and POSTs it to ComfyUI's REST API. No special SDK, just requests."

**Show `find_output()`:**
```python
# Poll ComfyUI's output directory until the file appears, then copy it
def find_output(prefix, timeout=300):
    deadline = time.time() + timeout
    while time.time() < deadline:
        matches = list(COMFYUI_OUTPUT_DIR.glob(f"{prefix}*.png"))
        if matches:
            return max(matches, key=lambda p: p.stat().st_mtime)
        time.sleep(2)
```

> "ComfyUI renders asynchronously — it queues jobs and saves outputs to its own folder. `find_output` polls that folder until a file with our job prefix appears, then copies it to `output/backgrounds/`. Simple file-watching."

**Why Canny ControlNet:**
> "Without ControlNet, Flux generates beautiful images but no two have the same spatial layout — different floor plane, different perspective, different camera angle. The product cutout would look pasted on. The C4D greyscale render gives Canny clean edges, and those edges constrain Flux to generate within the same composition every time. The thresholds 0.05/0.10 are the balance point — enough edges to lock the structure, loose enough for Flux to be creative with the surface."

---

### 02b_generate_copy_preview.py — US Copy (3 min)

> "Two Claude API calls. I'll walk through both."

**Call 1 — US CTAs:**
```python
cta_prompt = f"""You are a senior copywriter for Yosuki...
Each product family already has a LOCKED tagline.
Your job: write a CTA that feels like a powerful follow-through.
Rules:
- CTA: max 4 words. Action-oriented. No generic "Shop Now".
- Must complement the tagline — not repeat it.
- Return ONLY a valid JSON array: [{{"family":"...","cta":"..."}}]
PRODUCT FAMILIES:
{chr(10).join(cta_lines)}"""
```

> "The taglines are locked in brief.json — those are the creative director's lines. Claude only writes the CTAs. One call per product family, not per product — all saxophones share a CTA."

**The save-before-print pattern:**
```python
# Save to file FIRST — before printing to terminal
with open(COPY_PREVIEW_JSON, "w", encoding="utf-8") as f:
    json.dump(preview, f, ensure_ascii=False, indent=2)

# Then print — if this crashes on a Unicode character, data is safe
print(preview)
```

> "The output is saved to `copy_preview.json` before anything is printed to the terminal. So even if the print crashes on a Japanese character or a terminal encoding issue, the data isn't lost. Then you review it — if you like it, run 02c to apply it. If not, re-run 02b for a fresh Claude generation."

---

### 02c_apply_copy_preview.py — Apply Approved Copy (1 min)

> "This is the commit step. It reads the approved copy from `copy_preview.json`, updates the matching variants in `variants.json`, and resets their status to `copy_generated` so they re-render with the new copy on the next run."

```python
for v in us_variants:
    pid = v["product_id"]
    if pid in us_copy:
        v["tagline"] = us_copy[pid]["tagline"]
        v["cta"]     = us_copy[pid]["cta"]
        v["status"]  = "copy_generated"  # triggers re-render
```

> "The two-step preview → apply flow exists so a creative director can review copy before it's ever applied to a render. The pipeline never renders with unapproved copy."

---

### 03_populate_templates.py — AE Population + Render (5 min)

This is the core script — spend the most time here.

**Show the render loop:**
```python
for v in variants_to_render:
    # Step 1: Copy the .aep template to output/projects/
    shutil.copy(template_path, project_path)

    # Step 2: Run ExtendScript to inject background, product, copy
    subprocess.run([AERENDER_PATH, "-project", project_path,
                    "-s", "0", "-e", "0",   # frame 0 only (no render)
                    "-r", jsx_path])

    # Step 3: Render to MP4
    success = subprocess.run([AERENDER_PATH,
                               "-project", project_path,
                               "-comp", AE_MAIN_COMP_NAME,
                               "-output", render_path,
                               "-OMtemplate", AE_OUTPUT_MODULE])

    # Step 4: Save status immediately — crash recovery
    if success:
        v["status"] = "rendered"
        with open(VARIANTS_JSON, "w", encoding="utf-8") as f:
            json.dump(all_variants, f, ensure_ascii=False, indent=2)
```

> "Two aerender calls per variant. The first runs the ExtendScript to inject assets and copy into the AE comp. The second renders to MP4. After every successful render, variants.json is saved immediately. If aerender dies on variant 15, the first 14 keep their 'rendered' status — restart picks up from variant 15, not from scratch."

**Show the skip logic:**
```python
# Only render variants that haven't been rendered yet
variants_to_render = [v for v in all_variants if v.get("status") != "rendered"]
```

> "This is the idempotency check. Re-running the pipeline is always safe — it only processes what hasn't been done yet."

**Show the ExtendScript briefly:**

Open `extendscript/populate_template.jsx`:
```javascript
// Find placeholder layers by name, swap in real assets
var bgLayer = comp.layers.byName("BG_IMAGE_PLACEHOLDER");
bgLayer.replaceSource(importFile(bgPath), false);

var productLayer = comp.layers.byName("PRODUCT_CUTOUT_PLACEHOLDER");
productLayer.replaceSource(importFile(productPath), false);

// Text layers
comp.layers.byName("TAGLINE").text.sourceText = tagline;
comp.layers.byName("CTA_TEXT").text.sourceText = cta;
```

> "The AE template has named placeholder layers. The ExtendScript finds each layer by name and replaces it with the real asset. The layer names are the API between Python and After Effects — they have to match exactly. Three templates, one per aspect ratio, all use the same layer name convention."

---

### 05_deliver.py — Organise Output (1 min)

> "Reads variants.json, copies each rendered MP4 into a delivery folder organised by market then ratio. Nothing clever here — it's just a file organiser. The value is that the output is immediately hand-off ready."

---

## Block 4 — Live Run with Skip Flags (4 min)

**Run this in the terminal:**

```bash
python run_pipeline.py --skip-bg --skip-copy --no-drive
```

**Explain each flag as you type it:**
- `--skip-bg` — skips ComfyUI background generation (backgrounds already exist)
- `--skip-copy` — skips Claude copy generation (copy already in variants.json)
- `--no-drive` — skips Google Drive upload

> "These flags make the pipeline re-entrant. In production you'd run the full pipeline once. After that: change copy only → skip backgrounds, re-run 02b → 02c → 03. Regenerate a background → re-run 02 only. The pipeline is modular — each step is independently re-runnable."

**Expected output:** 0 rendered, 28 US skipped (+ 84 intl), 112 files delivered, exit code 0.

> "112 skipped — all already rendered. Completes in seconds because nothing needs to be re-done. This is the idempotency in practice."

---

## Block 5 — International Extension (3 min)

> "The US pipeline is the core. International is the same pipeline extended with two additions."

**Addition 1 — International backgrounds (`02a_generate_intl_backgrounds.py`):**
```python
# Same ComfyUI workflow, same C4D render —
# but the Flux prompt appends the market's visual_culture from brief.json
intl_prompt = us_prompt + f". {market['visual_culture']}"
```

> "The `visual_culture` field in brief.json for Japan might say 'refined concert hall, clean lines, soft diffused lighting.' For Brazil: 'vibrant outdoor venue, warm golden light, energetic atmosphere.' Same structural constraint from C4D, different photorealistic feel from Flux. 9 international backgrounds total — 3 scenes × 3 markets."

**Addition 2 — International copy (`02b` + `02c`):**
```python
# Call 2 in 02b: translate US copy to JP, DE, BR
# Claude receives the locked US tagline + generated CTA and adapts culturally
intl_prompt = f"""The US English copy is LOCKED.
Translate and culturally adapt it for each target market.
- Preserve emotional meaning — do NOT invent new concepts.
- German: use shorter phrasing for compound words.
- Japanese: max 6 syllable-words, refined and respectful tone.
"""
```

> "Claude handles the translation constraints natively — it knows German compound words run long, Japanese copy has different rhythm. The international variants are then cloned from US variants with the translated copy swapped in. Same AE templates, same render pipeline. The architecture doesn't change — just the inputs."

**Final summary number:**
> "28 US variants, plus 84 international across JP, DE, BR. 112 total. All from one brief.json, one pipeline run."

---

## Things to Have Open Before This Section

- [ ] Terminal ready at pipeline root
- [ ] `config.py` open in editor — scroll to the `os.getenv` section
- [ ] `brief.json` open — `products` and `families` sections visible
- [ ] `scripts/03_populate_templates.py` open — render loop visible
- [ ] `extendscript/populate_template.jsx` open
- [ ] `output/variants.json` open — all 112 with status "rendered"
- [ ] `scripts/02_generate_backgrounds.py` open — `find_output` visible
