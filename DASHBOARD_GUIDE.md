# Dashboard Guide
## What it is, how it works, how to talk about it

---

## How to Run It

```bash
streamlit run dashboard.py
```

Opens in your browser at `http://localhost:8501`.
The dashboard reads live from `variants.json` and `output/` — no page refresh needed after running a step,
it calls `st.rerun()` automatically.

---

## What It Is (in one sentence)

> "The dashboard is a Streamlit UI that wraps every pipeline step in a button. A creative director can run the entire campaign without ever touching the terminal."

Streamlit is a Python library that turns a regular Python script into a web app. No HTML, no JavaScript — just Python. That's why `dashboard.py` is readable as a normal script but renders as an interactive UI.

---

## Structure at a Glance

```
Header metrics bar
│  Campaign name / Total variants / Rendered / Delivered
│
├── STEP 1 — C4D Render
├── STEP 2 — ComfyUI Backgrounds   (US tab + International tabs)
├── STEP 3 — Generate Copy         (Preview → Approve two-step flow)
├── STEP 4 — AE Render             (market filter + single variant option)
├── STEP 5 — Deliver
│
├── Run Full Pipeline              (checkboxes to skip steps + progress bar)
│
└── All Variants table             (filterable, with Preview buttons)
```

Each step is an expander — collapsed by default so the page doesn't overwhelm. Open the one you're working on.

---

## The Key Pattern: run_script()

Every button in the dashboard calls the same helper:

```python
def run_script(script: str, extra_args: list[str] = []) -> tuple[int, str]:
    cmd = [sys.executable, script] + extra_args
    with st.spinner(f"Running {Path(script).name} ..."):
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(BASE_DIR),
            encoding="utf-8",
            errors="replace",
            timeout=3600,
        )
    combined = result.stdout + result.stderr
    return result.returncode, combined
```

**What to say about this:**
> "`run_script` runs the Python script as a subprocess — exactly as if you typed it in the terminal. It captures stdout and stderr, then `show_result()` displays them in an expandable log panel. If the script exits with code 0 (success), you see a green 'Done!'. Non-zero exit shows a red error with the log expanded automatically. The dashboard is essentially a GUI wrapper around the same CLI scripts."

**Why this matters:**
- The dashboard and the terminal are interchangeable — same scripts, same output
- A button press in the UI is identical to typing `python scripts/02b_generate_copy_preview.py` in the terminal
- Non-technical team members can run the pipeline without knowing the command names

---

## Step-by-Step Walkthrough

---

### Step 1 — C4D Renders

**What it shows:**
- Thumbnail previews of the 3 C4D greyscale renders (Saxophone, Piano, Guitar)
- A warning if any render file is missing
- Four buttons: Saxophone / Piano / Guitar / All — each launches Cinema 4D with the matching Python script

**The C4D launch code:**
```python
subprocess.run(
    [str(C4D_EXE), "-script", str(script_path)],
    timeout=7200,  # 2 hour timeout
)
```

**What to say:**
> "Clicking a C4D button opens Cinema 4D with the scene script pre-loaded. The dashboard blocks and shows a spinner — it's waiting for Cinema 4D to close. When you close C4D after the render finishes, the dashboard resumes. C4D_EXE and the script paths come from config.py — no hardcoded paths in the dashboard."

---

### Step 2 — ComfyUI Backgrounds

**Two tabs: US and International.**

**US tab:**
- Shows existing US backgrounds grouped by scene family
- Optional product filter (run just one product's backgrounds)
- "Generate US Backgrounds" button → runs `02_generate_backgrounds.py`
- Already-generated files are skipped automatically by the script

**International tab:**
- One sub-tab per market (JP, DE, BR)
- Shows existing international backgrounds per market
- "Generate [market] Backgrounds" button → deletes existing files for that market, runs `02a_generate_intl_backgrounds.py --market [mkt]`

**What to say about the delete-and-regenerate pattern:**
> "The 'Generate new variation' button for international markets deliberately deletes the existing files first. That's intentional — it forces Flux to generate a fresh variation rather than skipping the file. For the US backgrounds, I don't delete first because those are keyed to specific product IDs and the skip logic is handled inside the script."

---

### Step 3 — Generate Copy

**Two-button flow side by side:**

```
[ ▶ Generate Copy Preview ]    [ ✅ Apply Copy Preview ]
  calls 02b (Claude API)         calls 02c (writes to variants.json)
  saves to copy_preview.json     only enabled if preview exists
```

**Below the buttons:** an expandable table showing the current copy preview — US taglines + CTAs, then international translations per market.

**What to say:**
> "The two-step design is a deliberate creative checkpoint. 'Generate' calls Claude and saves the copy to a staging file. You review it in the table — see the taglines, CTAs, translations. If you like it, you hit 'Apply' and it gets written into variants.json. If you don't, you hit 'Generate' again for a fresh Claude pass. The render step never runs with unapproved copy because Apply has to be clicked manually."

**The conditional button:**
```python
if COPY_PREVIEW_JSON.exists():
    st.button("✅ Apply Copy Preview", type="primary")
else:
    st.info("Run Generate Copy Preview first.")
```

> "The Apply button only appears if copy_preview.json exists. It's a UI guardrail — you can't apply copy that hasn't been generated yet."

---

### Step 4 — AE Render

**Two dropdowns + a Run button:**
- **Market** — filter to one market or run all
- **Single variant** — dropdown of all 112 variant IDs, for re-rendering one specific variant

```python
render_args = []
if render_market != "All Markets":
    render_args += ["--market", render_market]
if render_single != "— Run all —":
    render_args = ["--variant", render_single]
```

**What to say:**
> "The render step passes flags straight through to 03_populate_templates.py. Selecting a single variant is useful if one render failed or if a creative change only affects one product. You don't have to re-render all 112 — just the one that changed. The status display at the bottom reads live from variants.json: 'X rendered / Y pending.'"

---

### Step 5 — Deliver

- Market dropdown (deliver one market or all)
- Runs `05_deliver.py`, which organises renders into the delivery folder
- Shows count of delivered variants

---

## Run Full Pipeline — The Orchestrator

This section at the bottom is the most powerful part.

**What it has:**
- Market selector
- Four checkboxes: Skip C4D / Skip ComfyUI / Skip Copy / Include Deliver
- A row of "step chips" — shows exactly which steps will run before you press the button
- A progress bar that advances step by step

**The step chip preview:**
```python
preview_steps = build_pipeline_steps(fp_market, fp_skip_c4d, fp_skip_bg, fp_skip_copy, fp_deliver)
# Renders a row of coloured chips: ⚙️ ComfyUI  ⚙️ Copy  ⚙️ Apply  🎬 AE Render
```

**What to say:**
> "Before you click Run, you see exactly which steps will execute as a row of chips. No surprises. The pipeline runs each step in sequence — if any step exits with an error, it stops immediately, shows the error log expanded, and doesn't continue to the next step. This prevents a bad copy generation from silently flowing into a render."

**The C4D step inside the full pipeline:**
```python
if step["type"] == "c4d":
    # Blocks until the user closes Cinema 4D
    subprocess.run([str(C4D_EXE), "-script", str(script["script"])], timeout=7200)
```

> "If C4D is in the pipeline, the progress bar pauses with a spinner while Cinema 4D is open. Close C4D when the render is done, and the pipeline automatically continues to the next step."

---

## Variants Table

At the bottom of the page, an expandable table of all 112 variants.

**Three filters:**
- Market dropdown
- Status dropdown (pending / copy_generated / rendered / delivered)
- Text search — matches against variant ID (e.g. type "guitar" to see only guitar variants, "JP" to see Japan)

**Status colours:**
| Status | Colour | Meaning |
|--------|--------|---------|
| ⏳ Pending | Grey | No copy yet |
| 📝 Copy Ready | Blue | Copy applied, not yet rendered |
| 🎬 Rendered | Amber | MP4 exists |
| ✅ Delivered | Green | Organised into delivery folder |

**Preview button:**
Each rendered row has a "👁 Preview" button. Clicking it opens an inline preview panel at the top of the table showing the MP4 player + the variant's tagline, CTA, market, ratio, and status.

**What to say:**
> "The variants table is the campaign's live state. Every row is a render job. You can see at a glance which ones are done, which are waiting, and which failed. The Preview button lets you spot-check a specific render without leaving the dashboard — click it, the video player appears inline above the table."

---

## How to Demo It Effectively

**For the presentation (5 min):**
1. Open the dashboard — header metrics show 112 total / 112 rendered / 112 delivered
2. Expand Step 2 — show the US backgrounds tab (real AI-generated images)
3. Click to the International tab — show JP/DE/BR backgrounds side by side
4. Expand Step 3 — open the copy preview expander, show the table of US + intl copy
5. Scroll to the Variants table — filter by market (JP), click Preview on one rendered variant

**The line that lands:**
> "A motion designer who's never touched a terminal can run this entire campaign from this UI. But it's also fully runnable from the command line — the buttons are just calling the same Python scripts."

---

## One Technical Detail Worth Mentioning

The dashboard imports paths from `config.py` — no paths are hardcoded in `dashboard.py` itself:

```python
from config import (
    C4D_EXE,
    C4D_RENDERS,
    C4D_SCRIPTS,
    COPY_PREVIEW_JSON,
    VARIANTS_JSON,
)
```

> "The dashboard, like every other script in the pipeline, gets its paths from config.py. That's why the whole thing is portable — one .env file is all you change when moving to a new machine."
