"""
dashboard.py — Yosuki Pipeline Dashboard
=========================================
Run with:
    streamlit run dashboard.py

Full pipeline flow:
  Step 1: C4D Render         — preview greyscale scene renders
  Step 2: ComfyUI Flux Canny — generate backgrounds from C4D + preview
  Step 3: Generate Copy      — Claude API copy generation + review before applying
  Step 4: AE Render          — plug copy + backgrounds into AE templates and render
  Step 5: Deliver            — package and deliver to Google Drive
"""

import json
import subprocess
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from config import (
    C4D_EXE,
    C4D_RENDERS,
    C4D_RENDERS_DIR,
    C4D_SCRIPTS,
    COPY_PREVIEW_JSON,
    PRODUCT_CUTOUTS_DIR,
    VARIANTS_JSON,
)

# ─────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────
BASE_DIR         = Path(__file__).parent
RENDERS_DIR      = BASE_DIR / "output" / "renders"
BACKGROUNDS_DIR  = BASE_DIR / "output" / "backgrounds"
BRIEF_JSON       = BASE_DIR / "brief.json"

# C4D preview scenes shown in Step 1 (filenames from config → C4D_RENDERS)
C4D_SCENES = {
    "Saxophone": C4D_RENDERS["sax"],
    "Piano":     C4D_RENDERS["piano"],
    "Guitar":    C4D_RENDERS["guitar"],
}

# ─────────────────────────────────────────────
# STATUS HELPERS
# ─────────────────────────────────────────────
STATUS_LABEL = {
    "pending":        "⏳ Pending",
    "copy_generated": "📝 Copy Ready",
    "copy_done":      "📝 Copy Ready",
    "rendered":       "🎬 Rendered",
    "delivered":      "✅ Delivered",
}
STATUS_COLOR = {
    "pending":        "#888888",
    "copy_generated": "#4A90D9",
    "copy_done":      "#4A90D9",
    "rendered":       "#F0A500",
    "delivered":      "#27AE60",
}

# ─────────────────────────────────────────────
# DATA LOADERS
# ─────────────────────────────────────────────
def load_variants() -> list[dict]:
    if not VARIANTS_JSON.exists():
        return []
    with open(VARIANTS_JSON, encoding="utf-8") as f:
        return json.load(f)

def load_brief() -> dict:
    if not BRIEF_JSON.exists():
        return {}
    with open(BRIEF_JSON, encoding="utf-8") as f:
        return json.load(f)

def get_render_path(variant: dict) -> Path | None:
    p = RENDERS_DIR / f"{variant['variant_id']}.mp4"
    return p if p.exists() else None

# ─────────────────────────────────────────────
# SCRIPT RUNNER
# ─────────────────────────────────────────────
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
    combined = result.stdout + ("\n" + result.stderr if result.stderr.strip() else "")
    return result.returncode, combined

def show_result(returncode: int, output: str):
    if returncode == 0:
        st.success("Done!")
    else:
        st.error(f"Script exited with error code {returncode}")
    with st.expander("Output log", expanded=(returncode != 0)):
        st.code(output, language=None)

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Yosuki Pipeline",
    page_icon="🎵",
    layout="wide",
)

# ─────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────
variants      = load_variants()
brief         = load_brief()
campaign_name = brief.get("campaign_name", "Yosuki 2026")

total     = len(variants)
rendered  = sum(1 for v in variants if v.get("status") in ("rendered", "delivered"))
delivered = sum(1 for v in variants if v.get("status") == "delivered")

intl_markets = [m["id"] for m in brief.get("markets", []) if m["id"] != "US"]

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
st.markdown("## 🎵 YOSUKI PIPELINE DASHBOARD")
st.caption(f"{campaign_name} — Spring 2026")
st.divider()

m1, m2, m3, m4 = st.columns(4)
m1.metric("Campaign",       campaign_name)
m2.metric("Total Variants", total)
m3.metric("✓ Rendered",     rendered)
m4.metric("📦 Delivered",   delivered)

st.divider()

# ─────────────────────────────────────────────
# PIPELINE STEPS
# ─────────────────────────────────────────────
st.subheader("Pipeline Steps")
st.caption("Run each step in order. Each step can be re-run independently at any time.")

all_markets = sorted(set(v["market"] for v in variants)) if variants else ["US"]

st.markdown("")


# ────────────────────────────────────────────────────────────────────
# STEP 1 — C4D Render
# ────────────────────────────────────────────────────────────────────
with st.expander("**STEP 1 — C4D Render** — Scene reference renders for ControlNet", expanded=False):
    st.markdown(
        "Cinema 4D renders the greyscale scene for each product group. "
        "These are used as the ControlNet image in Flux Canny (Step 2), "
        "giving every background the correct spatial composition."
    )

    # Re-glob every render so the dashboard picks up new files without restarting
    def latest_c4d_scenes() -> dict:
        patterns = {
            "Saxophone": "saxophone_model1_16x9_*.png",
            "Piano":     "piano_grand_16x9_*.png",
            "Guitar":    "guitar_16x9_*.png",
        }
        result = {}
        for name, pat in patterns.items():
            matches = sorted(C4D_RENDERS_DIR.glob(pat), key=lambda p: p.stat().st_mtime, reverse=True)
            if matches:
                result[name] = matches[0]
        return result

    live_scenes = latest_c4d_scenes()
    missing     = [n for n in ["Saxophone", "Piano", "Guitar"] if n not in live_scenes]

    if missing:
        st.warning(f"Missing C4D renders: {', '.join(missing)}")

    if live_scenes:
        cols = st.columns(len(live_scenes))
        for col, (name, path) in zip(cols, live_scenes.items()):
            with col:
                # Guard: only show the image if the file actually exists on disk.
                # Without this, Streamlit throws a MediaFileStorageError when
                # config.py returns the placeholder path (_001) for a missing render.
                if path.exists():
                    try:
                        # Read into bytes first — bypasses Streamlit's internal
                        # file server, which fails on Windows paths with spaces.
                        img_bytes = path.read_bytes()
                        st.image(img_bytes, caption=name, use_container_width=True)
                    except Exception:
                        st.caption(f"{name} — render exists but can't display")
                else:
                    st.caption(f"{name} — no render yet")

    st.caption(f"C4D renders location: {C4D_RENDERS_DIR}")
    st.markdown("")

    if not C4D_EXE.exists():
        st.error(f"Cinema 4D not found at: {C4D_EXE}")
    else:
        st.markdown(
            "**Render C4D scenes** — open your combined project in C4D, then click a button below. "
            "'All' renders every take (Saxophone / Piano / Guitar) in sequence."
        )

        # Map each scene name to its render glob pattern (used to detect new files)
        SCENE_PATTERNS = {
            "Saxophone": "saxophone_model1_16x9_*.png",
            "Piano":     "piano_grand_16x9_*.png",
            "Guitar":    "guitar_16x9_*.png",
        }

        def wait_for_new_render(pattern: str, known: set, timeout: int = 300) -> bool:
            """Polls the renders folder until a new file matching pattern appears."""
            import time
            deadline = time.time() + timeout
            while time.time() < deadline:
                matches = set(C4D_RENDERS_DIR.glob(pattern))
                if matches - known:
                    return True
                time.sleep(2)
            return False

        individual = {k: v for k, v in C4D_SCRIPTS.items() if k != "All"}
        btn_cols   = st.columns(len(individual))

        # Individual scene buttons — each passes one script to the running C4D instance
        for col, (scene_name, script_path) in zip(btn_cols, individual.items()):
            with col:
                if st.button(f"▶ {scene_name}", key=f"c4d_launch_{scene_name}", use_container_width=True):
                    if not script_path.exists():
                        st.error(f"Script not found: {script_path.name}")
                    else:
                        pattern  = SCENE_PATTERNS[scene_name]
                        existing = set(C4D_RENDERS_DIR.glob(pattern))
                        subprocess.Popen([str(C4D_EXE), "-script", str(script_path)])
                        with st.spinner(f"Waiting for {scene_name} render..."):
                            found = wait_for_new_render(pattern, existing)
                        if found:
                            st.success(f"{scene_name} render done.")
                        else:
                            st.error(f"{scene_name} timed out — check C4D for errors.")
                        st.rerun()



# ────────────────────────────────────────────────────────────────────
# STEP 2 — ComfyUI Flux Canny Backgrounds
# ────────────────────────────────────────────────────────────────────
with st.expander("**STEP 2 — ComfyUI Flux Canny** — Generate scene backgrounds", expanded=False):
    st.markdown(
        "Runs the C4D render through Flux Canny (ControlNet) to generate photorealistic "
        "backgrounds. **US:** one background per product+ratio (from C4D + brief scene prompt). "
        "**International:** one background per scene per market, with cultural visual nuances "
        "from `brief.json` appended to the prompt."
    )

    tab_us, tab_intl = st.tabs(["US", "🌍 International"])

    with tab_us:
        st.markdown("**US backgrounds** — one per product+ratio combo (27 total)")

        # Show one representative 16x9 per scene — same 3-column layout as international
        us_scenes = {"Saxophone": "sax_signature", "Piano": "piano_grand", "Guitar": "guitar_paulie_black"}
        scene_items = list(us_scenes.items())
        cols = st.columns(3)
        for col, (scene_name, pid) in zip(cols, scene_items):
            bg = next(iter(sorted(BACKGROUNDS_DIR.glob(f"{pid}_16x9*.png"))), None)
            if bg:
                col.image(str(bg), caption=bg.stem, use_container_width=True)
            else:
                col.info(f"No {scene_name} background yet")

        us_product = st.text_input(
            "Product filter (optional — leave blank for all 27)",
            placeholder="e.g. sax_signature",
            key="us_product",
        )
        st.caption("Already-generated backgrounds are skipped automatically. Delete specific files from `output/backgrounds/` to regenerate them.")

        us_args = ["--product", us_product.strip()] if us_product.strip() else []

        if st.button("▶ Generate US Backgrounds", key="run_us_bg", use_container_width=True):
            rc, out = run_script("scripts/02_generate_backgrounds.py", us_args)
            show_result(rc, out)
            st.rerun()

    with tab_intl:
        st.markdown(
            "**International backgrounds** — one per scene per market (9 total). "
            "Same C4D ControlNet input as US, prompt enriched with market's `visual_culture`."
        )

        scenes = ["sax", "piano", "guitar"]
        intl_mkt_tabs = st.tabs(intl_markets) if intl_markets else []

        for tab, mkt in zip(intl_mkt_tabs, intl_markets):
            with tab:
                existing = [(s, BACKGROUNDS_DIR / f"{s}_{mkt}_16x9.png") for s in scenes]
                existing_found = [(s, p) for s, p in existing if p.exists()]

                if existing_found:
                    cols = st.columns(len(existing_found))
                    for col, (scene_name, bg_path) in zip(cols, existing_found):
                        col.image(str(bg_path), caption=f"{scene_name}_{mkt}_16x9", use_container_width=True)
                else:
                    st.info(f"No {mkt} backgrounds generated yet.")

                if st.button(f"▶ Generate {mkt} Backgrounds (new variation)", key=f"run_intl_bg_{mkt}", use_container_width=True):
                    # Delete existing so we get fresh variations
                    for s in scenes:
                        p = BACKGROUNDS_DIR / f"{s}_{mkt}_16x9.png"
                        if p.exists():
                            p.unlink()
                    rc, out = run_script("scripts/02a_generate_intl_backgrounds.py", ["--market", mkt])
                    show_result(rc, out)
                    st.rerun()


# ────────────────────────────────────────────────────────────────────
# STEP 2a — Background Removal (rembg)
# ────────────────────────────────────────────────────────────────────
with st.expander("**STEP 2a — Background Removal** — Remove backgrounds from product images", expanded=False):
    st.markdown(
        "Removes white/grey backgrounds from product PNGs using rembg (AI-based, runs locally). "
        "Outputs transparent cutouts to `assets/product_cutouts/` for use in After Effects. "
        "Already-processed cutouts are skipped automatically."
    )

    # The cutout filenames produced by 00_prep_assets.py
    CUTOUT_NAMES = [
        "sax1_cutout.png",
        "piano1_cutout.png", "piano2_cutout.png", "piano3_cutout.png",
        "guitar1a_cutout.png", "guitar1b_cutout.png",
        "guitar2a_cutout.png", "guitar2b_cutout.png",
        "guitar3a_cutout.png", "guitar3b_cutout.png",
        "logo_cutout.png",
    ]
    done_cutouts    = [n for n in CUTOUT_NAMES if (PRODUCT_CUTOUTS_DIR / n).exists()]
    missing_cutouts = [n for n in CUTOUT_NAMES if not (PRODUCT_CUTOUTS_DIR / n).exists()]

    st.caption(f"{len(done_cutouts)} / {len(CUTOUT_NAMES)} cutouts ready")

    if missing_cutouts:
        st.warning(f"Missing: {', '.join(missing_cutouts)}")
    else:
        st.success("All product cutouts are ready.")

    if st.button("▶ Run Background Removal", key="run_rembg", use_container_width=True):
        rc, out = run_script("scripts/00_prep_assets.py")
        show_result(rc, out)
        st.rerun()


# ────────────────────────────────────────────────────────────────────
# STEP 3 — Generate Copy
# ────────────────────────────────────────────────────────────────────
with st.expander("**STEP 3 — Generate Copy** — Claude API copy generation", expanded=False):
    st.markdown(
        "**US:** Taglines are locked in `brief.json` per product family. "
        "Claude generates the CTA only. "
        "**International:** Claude translates the US copy (tagline + CTA) for JP/DE/BR, "
        "keeping it culturally nuanced rather than a literal translation."
    )

    col_preview, col_apply = st.columns(2)

    with col_preview:
        st.markdown("**1. Generate & Preview** — calls Claude API, shows copy before writing anything")
        if st.button("▶ Generate Copy Preview", key="run_copy_preview", use_container_width=True):
            rc, out = run_script("scripts/02b_generate_copy_preview.py")
            show_result(rc, out)
            # Auto-expand the preview table after generating so you can see it immediately
            st.session_state["copy_preview_expanded"] = True
            st.rerun()

    with col_apply:
        st.markdown("**2. Apply to Variants** — writes approved copy into `variants.json` + creates intl variants")
        if COPY_PREVIEW_JSON.exists():
            if st.button("✅ Apply Copy", key="run_apply_copy", use_container_width=True, type="primary"):
                rc, out = run_script("scripts/02c_apply_copy_preview.py")
                show_result(rc, out)
                st.rerun()
        else:
            st.info("Run Generate Copy Preview first.")

    # Show current copy preview if it exists
    if COPY_PREVIEW_JSON.exists():
        with open(COPY_PREVIEW_JSON, encoding="utf-8") as f:
            cp = json.load(f)

        with st.expander("Current copy preview", expanded=st.session_state.get("copy_preview_expanded", False)):
            # Helper: collapse product IDs down to their family name (sax / piano / guitar)
            FAMILY_LABEL = {"sax": "Saxophone", "piano": "Piano", "guitar": "Guitar"}
            def family_of(pid):
                for prefix, label in FAMILY_LABEL.items():
                    if pid.startswith(prefix):
                        return prefix, label
                return pid, pid

            # US — one row per family (all products in a family share tagline + CTA)
            st.markdown("**US** *(tagline from brief, CTA from Claude)*")
            us_data = cp.get("us", {})
            seen_us, us_rows = set(), []
            for pid, c in us_data.items():
                fkey, flabel = family_of(pid)
                if fkey not in seen_us:
                    seen_us.add(fkey)
                    us_rows.append({
                        "Scene":   flabel,
                        "Tagline": c.get("tagline", ""),
                        "CTA":     c.get("cta", ""),
                    })
            if us_rows:
                st.table(us_rows)

            # International — taglines adapted from US, CTAs written fresh per market
            st.markdown("**International** *(taglines culturally adapted · CTAs written fresh per market)*")
            intl_data = cp.get("intl", {})
            for mkt_id in intl_markets:
                st.markdown(f"*{mkt_id}*")
                seen_intl, rows = set(), []
                for key, c in intl_data.items():
                    if key.endswith(f"_{mkt_id}"):
                        pid = key.replace(f"_{mkt_id}", "")
                        fkey, flabel = family_of(pid)
                        if fkey not in seen_intl:
                            seen_intl.add(fkey)
                            us_c = us_data.get(pid, {})
                            rows.append({
                                "Scene":        flabel,
                                "Tagline":      c.get("tagline", ""),
                                "Tagline (EN)": us_c.get("tagline", ""),
                                "CTA":          c.get("cta", ""),
                                "CTA (EN)":     c.get("cta_en", ""),
                            })
                if rows:
                    st.table(rows)


# ────────────────────────────────────────────────────────────────────
# STEP 4 — AE Render
# ────────────────────────────────────────────────────────────────────
with st.expander("**STEP 4 — AE Render** — Plug copy + backgrounds into templates and render", expanded=False):
    st.markdown(
        "Copies the AE template for each variant, writes the data JSON (copy + asset paths), "
        "then runs `aerender.exe`. The JSX startup hook reads the data JSON and swaps in the "
        "correct text and footage before rendering begins."
    )

    r1, r2 = st.columns([2, 3])

    with r1:
        render_market = st.selectbox("Market", ["All Markets"] + all_markets, key="render_market_sel")
    with r2:
        variant_ids = [v["variant_id"] for v in variants] if variants else []
        render_single = st.selectbox("Single variant (optional)", ["— Run all —"] + variant_ids, key="render_single")

    render_args = []
    if render_market != "All Markets":
        render_args += ["--market", render_market]
    if render_single != "— Run all —":
        render_args = ["--variant", render_single]

    if st.button("▶ Run Render", key="run_render", use_container_width=True, type="primary"):
        rc, out = run_script("scripts/03_populate_templates.py", render_args)
        show_result(rc, out)
        st.rerun()

    # Quick stats
    rendered_count = sum(1 for v in variants if v.get("status") in ("rendered", "delivered"))
    pending_count  = sum(1 for v in variants if v.get("status") not in ("rendered", "delivered"))
    st.caption(f"Status: {rendered_count} rendered / {pending_count} pending")


# ────────────────────────────────────────────────────────────────────
# STEP 5 — Deliver
# ────────────────────────────────────────────────────────────────────
with st.expander("**STEP 5 — Deliver** — Package and deliver to Google Drive", expanded=False):
    st.markdown(
        "Organises rendered MP4s into `output/delivery/{MARKET}/{product}/{ratio}.mp4` "
        "and uploads to Google Drive. Configure the target Drive folder in `config.py`."
    )

    d_market = st.selectbox("Market", ["All Markets"] + all_markets, key="deliver_market")
    deliver_args = ["--market", d_market] if d_market != "All Markets" else []

    if st.button("▶ Run Deliver", key="run_deliver", use_container_width=True):
        rc, out = run_script("scripts/05_deliver.py", deliver_args)
        show_result(rc, out)
        st.rerun()

    delivered_count = sum(1 for v in variants if v.get("status") == "delivered")
    st.caption(f"Delivered: {delivered_count} of {total} variants")


st.divider()


# ────────────────────────────────────────────────────────────────────
# RUN FULL PIPELINE
# ────────────────────────────────────────────────────────────────────
st.subheader("🚀 Run Full Pipeline")
st.caption("Runs selected steps in sequence for your chosen market.")

# ── Options ────────────────────────────────────────────────────────
fp_col1, fp_col2, fp_col3, fp_col4, fp_col5 = st.columns([2, 1, 1, 1, 1])
with fp_col1:
    fp_market = st.selectbox("Market", all_markets, key="fp_market")
with fp_col2:
    fp_skip_c4d   = st.checkbox("Skip C4D",     value=True,  key="fp_skip_c4d",
                                help="Uncheck to launch Cinema 4D with the batch render script.")
with fp_col3:
    fp_skip_bg    = st.checkbox("Skip ComfyUI", value=True,  key="fp_skip_bg",
                                help="Uncheck to regenerate backgrounds before rendering.")
with fp_col4:
    fp_skip_rembg = st.checkbox("Skip Rembg",   value=True,  key="fp_skip_rembg",
                                help="Uncheck to run background removal on product images.")
with fp_col5:
    fp_skip_copy  = st.checkbox("Skip Copy",    value=True,  key="fp_skip_copy",
                                help="Uncheck to re-generate and apply copy before rendering.")


# ── Build ordered step list ────────────────────────────────────────
# Each step is a dict — type "c4d" launches Cinema 4D, type "script" runs Python.
def build_pipeline_steps(market, skip_c4d, skip_bg, skip_rembg, skip_copy):
    steps = []
    if not skip_c4d:
        steps.append({"name": "C4D Renders", "type": "c4d",
                      "exe": C4D_EXE, "script": C4D_SCRIPTS["All"]})
    if not skip_bg:
        if market == "US":
            steps.append({"name": "ComfyUI — US Backgrounds", "type": "script",
                          "script": "scripts/02_generate_backgrounds.py", "args": []})
        else:
            steps.append({"name": "ComfyUI — Intl Backgrounds", "type": "script",
                          "script": "scripts/02a_generate_intl_backgrounds.py", "args": ["--market", market]})
    if not skip_rembg:
        steps.append({"name": "Background Removal", "type": "script",
                      "script": "scripts/00_prep_assets.py", "args": []})
    if not skip_copy:
        steps.append({"name": "Generate Copy Preview", "type": "script",
                      "script": "scripts/02b_generate_copy_preview.py", "args": []})
        steps.append({"name": "Apply Copy", "type": "script",
                      "script": "scripts/02c_apply_copy_preview.py",  "args": []})
    steps.append({"name": "AE Render", "type": "script",
                  "script": "scripts/03_populate_templates.py", "args": ["--market", market]})
    return steps


# ── Step preview chips (show what will run before button is pressed) ─
preview_steps = build_pipeline_steps(fp_market, fp_skip_c4d, fp_skip_bg, fp_skip_rembg, fp_skip_copy)
if preview_steps:
    chip_cols = st.columns(len(preview_steps))
    for col, step in zip(chip_cols, preview_steps):
        icon = "🎬" if step["type"] == "c4d" else "⚙️"
        col.markdown(
            f"<div style='text-align:center;padding:6px 4px;background:#1a3a5c;"
            f"border-radius:6px;color:#7ab8f5;font-size:0.78em'>{icon} {step['name']}</div>",
            unsafe_allow_html=True,
        )
else:
    st.info("All steps are skipped — enable at least one step above.")

st.markdown("")

# ── Run / Stop buttons ──────────────────────────────────────────────
run_col, stop_col = st.columns([3, 1])

with run_col:
    run_clicked = preview_steps and st.button(
        f"▶ Run Full Pipeline — {fp_market}",
        key="run_full_pipeline",
        use_container_width=True,
        type="primary",
    )

with stop_col:
    # Sets a flag — pipeline checks it between steps and halts.
    # Note: can't interrupt a step mid-run; refresh the browser (F5) for an immediate stop.
    if st.button("⏹ Stop", key="stop_pipeline", use_container_width=True):
        st.session_state["pipeline_stop"] = True
        st.info("Stop requested — pipeline will halt after the current step finishes.")

if run_clicked:
    # Clear any previous stop request when starting a new run
    st.session_state["pipeline_stop"] = False

    steps  = build_pipeline_steps(fp_market, fp_skip_c4d, fp_skip_bg, fp_skip_rembg, fp_skip_copy)
    n      = len(steps)
    all_ok = True
    progress_bar = st.progress(0, text="Starting pipeline...")

    for i, step in enumerate(steps):
        # Check for stop request before starting each new step
        if st.session_state.get("pipeline_stop"):
            progress_bar.progress(int(i / n * 100), text="Stopped by user.")
            st.warning(f"Pipeline stopped before step {i+1}: **{step['name']}**")
            all_ok = False
            break

        pct  = int(i / n * 100)
        name = step["name"]
        progress_bar.progress(pct, text=f"Step {i+1}/{n}: {name}...")

        if step["type"] == "c4d":
            # Launch Cinema 4D and block until the user closes it
            if not Path(step["exe"]).exists():
                st.error(f"Cinema 4D not found at: {step['exe']}")
                all_ok = False
                break
            with st.spinner("Cinema 4D is open — close it when your renders are done to continue the pipeline..."):
                subprocess.run([str(step["exe"]), "-script", str(step["script"])], timeout=7200)
            with st.expander(f"✓ {name} — Cinema 4D closed, continuing...", expanded=False):
                st.write("Renders saved to:", str(C4D_RENDERS_DIR))

        else:
            rc, out = run_script(step["script"], step.get("args", []))
            if rc != 0:
                progress_bar.progress(pct, text=f"Stopped at: {name}")
                st.error(f"Pipeline stopped at step {i+1}: **{name}**")
                with st.expander("Error log", expanded=True):
                    st.code(out, language=None)
                all_ok = False
                break
            else:
                with st.expander(f"✓ {name} — done", expanded=False):
                    st.code(out, language=None)

    if all_ok:
        progress_bar.progress(100, text=f"Pipeline complete — {fp_market} done!")
        st.success(f"Full pipeline complete for **{fp_market}** — {n} steps finished.")
        st.rerun()

st.divider()


# ─────────────────────────────────────────────
# PREVIEW PANEL
# ─────────────────────────────────────────────
if "preview_id" not in st.session_state:
    st.session_state.preview_id = None

if st.session_state.preview_id:
    vid   = st.session_state.preview_id
    match = next((v for v in variants if v["variant_id"] == vid), None)

    if match:
        st.subheader(f"▶  Preview — {vid}")
        info_col, video_col = st.columns([1, 2])

        with info_col:
            st.markdown(f"**Tagline:** {match.get('tagline', '—')}")
            st.markdown(f"**Series:** {match.get('series_title', '—')}")
            st.markdown(f"**CTA:** {match.get('cta', '—')}")
            st.markdown(f"**Market:** {match.get('market', '—')}")
            st.markdown(f"**Ratio:** {match.get('ratio', '—')}")
            status = match.get("status", "pending")
            color  = STATUS_COLOR.get(status, "#888")
            label  = STATUS_LABEL.get(status, status)
            st.markdown(
                f'**Status:** <span style="color:{color}">{label}</span>',
                unsafe_allow_html=True,
            )
            if st.button("✕ Close Preview"):
                st.session_state.preview_id = None
                st.rerun()

        with video_col:
            render_path = get_render_path(match)
            if render_path:
                small_col, _ = st.columns([1, 1])
                with small_col:
                    st.video(str(render_path))
            else:
                st.warning("MP4 not found on disk.")

        st.divider()


# ─────────────────────────────────────────────
# VARIANTS TABLE
# ─────────────────────────────────────────────
with st.expander(f"**All Variants** — {total} total", expanded=False):

    f1, f2, f3 = st.columns([2, 2, 4])
    with f1:
        filter_market = st.selectbox(
            "Filter market",
            ["All"] + sorted(set(v["market"] for v in variants)),
            key="filter_market",
        )
    with f2:
        all_statuses  = sorted(set(v.get("status", "pending") for v in variants))
        filter_status = st.selectbox("Filter status", ["All"] + all_statuses, key="filter_status")
    with f3:
        search = st.text_input("Search", placeholder="e.g. guitar, sax, 16x9, JP ...")

    filtered = variants
    if filter_market != "All":
        filtered = [v for v in filtered if v["market"] == filter_market]
    if filter_status != "All":
        filtered = [v for v in filtered if v.get("status") == filter_status]
    if search:
        filtered = [v for v in filtered if search.lower() in v["variant_id"].lower()]

    st.caption(f"Showing {len(filtered)} of {total} variants")

    h1, h2, h3, h4, h5 = st.columns([4, 2, 2, 3, 2])
    h1.markdown("**VARIANT**")
    h2.markdown("**MARKET**")
    h3.markdown("**RATIO**")
    h4.markdown("**STATUS**")
    h5.markdown("**PREVIEW**")
    st.divider()

    for v in filtered:
        c1, c2, c3, c4, c5 = st.columns([4, 2, 2, 3, 2])
        c1.write(v["variant_id"])
        c2.write(v["market"])
        c3.write(v["ratio"])

        status = v.get("status", "pending")
        label  = STATUS_LABEL.get(status, status)
        color  = STATUS_COLOR.get(status, "#888")
        c4.markdown(f'<span style="color:{color}">{label}</span>', unsafe_allow_html=True)

        render_path = get_render_path(v)
        if render_path:
            if c5.button("👁 Preview", key=f"btn_{v['variant_id']}"):
                if st.session_state.preview_id == v["variant_id"]:
                    st.session_state.preview_id = None
                else:
                    st.session_state.preview_id = v["variant_id"]
                st.rerun()
        else:
            c5.markdown('<span style="color:#888">—</span>', unsafe_allow_html=True)
