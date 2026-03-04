"""
sax_16x9_test.py — Saxophone 16:9 Full Pipeline Test
=====================================================
WHAT THIS DOES (step by step):
  1. Reads the saxophone creative brief
  2. Finds the most recent C4D reference render (run yosuki_saxophone_16x9.py in Cinema 4D first)
  3. Builds a Flux background prompt guided by the brief's creative tone
  4. Submits to ComfyUI (Flux model) at 1920x1080 and waits for the result
  5. Copies the generated background into output/backgrounds/
  6. Writes the _data.json that the After Effects startup script reads
  7. Copies the landscape_16.9.aep template to output/projects/
  8. Runs aerender.exe to produce the final MP4

PRE-REQUISITES:
  1. Run yosuki_saxophone_16x9.py in Cinema 4D to get the reference render
  2. ComfyUI must be running at http://127.0.0.1:8188 with the Flux model loaded
  3. After Effects 2026 must be installed (aerender.exe)
  4. Run from the yosuki-pipeline folder:
       cd "F:/Adobe_FDE Take-Home/yosuki-pipeline"
       python scripts/sax_16x9_test.py

WHY A SEPARATE FILE:
  This is a standalone test that bridges the Cinema 4D staging work with the
  main pipeline. It does NOT modify or depend on yosuki_saxophone_16x9.py.
"""

import copy
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

# Allow importing config.py from the yosuki-pipeline root folder
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ["PYTHONIOENCODING"] = "utf-8"

import requests

from config import (
    AE_MAIN_COMP_NAME,
    AE_OUTPUT_MODULE,
    AE_TEMPLATES_DIR,
    AERENDER_PATH,
    BACKGROUNDS_DIR,
    COMFYUI_URL,
    COMFYUI_WORKFLOWS_DIR,
    PROJECTS_DIR,
    RENDERS_DIR,
)


# ─────────────────────────────────────────────
# PATHS SPECIFIC TO THIS TEST
# These are the only paths you may need to adjust.
# ─────────────────────────────────────────────

# Creative brief for the saxophone 16:9 variant
BRIEF_PATH = Path(r"F:\Adobe_FDE Take-Home\Assets\briefs\saxophone_model1_16x9.json")

# Where Cinema 4D saves its renders (output of yosuki_saxophone_16x9.py)
C4D_RENDERS_DIR = Path(r"F:\Adobe_FDE Take-Home\Assets\renders")

# Transparent saxophone PNG (no background) — used in the AE composite
PRODUCT_CUTOUT = Path(r"F:\Adobe_FDE Take-Home\yosuki-pipeline\assets\product_cutouts\sax1_cutout.png")

# The 16:9 After Effects template
AE_TEMPLATE = AE_TEMPLATES_DIR / "landscape_16.9.aep"

# Where ComfyUI Desktop saves generated images on this machine
COMFYUI_OUTPUT_DIR = Path("G:/ComfyUI/output")

# Unique ID used for all output filenames in this test run
VARIANT_ID = "sax_model1_16x9_test"


# ─────────────────────────────────────────────
# COMFYUI SETTINGS
# Node IDs match background_workflow.json exactly.
# ─────────────────────────────────────────────

NODE = {
    "positive_prompt": "6",   # CLIPTextEncode  — the scene description text
    "save_image":      "9",   # SaveImage        — filename prefix for output
    "scheduler":       "17",  # BasicScheduler   — number of generation steps
    "seed":            "25",  # RandomNoise      — seed for variation
    "latent":          "27",  # EmptySD3LatentImage — image width/height
}

STEPS         = 25    # Generation steps — higher = slower but more detailed
POLL_INTERVAL = 3     # Seconds between checking if ComfyUI is done
MAX_WAIT      = 300   # Maximum seconds to wait (5 minutes)


# ─────────────────────────────────────────────
# STEP 1 — FIND THE C4D REFERENCE RENDER
# ─────────────────────────────────────────────

def find_latest_c4d_render():
    """
    Looks for the most recent saxophone PNG in the C4D renders folder.

    The C4D render is the visual reference — it shows the saxophone staged
    on the platform with sleek blue lighting. We use it to confirm the
    composition and to guide the background prompt description.

    Run yosuki_saxophone_16x9.py in Cinema 4D before this script.
    """
    if not C4D_RENDERS_DIR.exists():
        print("[ERROR] C4D renders folder not found:", C4D_RENDERS_DIR)
        return None

    renders = list(C4D_RENDERS_DIR.glob("saxophone_model1_16x9_*.png"))
    if not renders:
        print("[ERROR] No saxophone C4D renders found in:", C4D_RENDERS_DIR)
        print("        Run yosuki_saxophone_16x9.py in Cinema 4D first, then re-run this.")
        return None

    # Sort by modification time — newest file first
    renders.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    latest = renders[0]
    size_kb = latest.stat().st_size // 1024
    print(f"[C4D]  Reference render: {latest.name} ({size_kb} KB)")
    return latest


# ─────────────────────────────────────────────
# STEP 2 — BUILD THE COMFYUI BACKGROUND PROMPT
# ─────────────────────────────────────────────

def build_background_prompt(brief):
    """
    Converts the creative brief into a Flux-friendly scene description.

    The C4D render informs the visual direction — the saxophone is on a
    dark circular platform with cool blue-white lighting ("sleek" tone).
    The background should complement that staging without repeating the
    instrument itself.

    Flux does not use a negative prompt, so we describe what we WANT
    clearly, and include "no instruments visible" to keep the background
    as a clean backdrop for the AE composite.
    """
    tone = brief.get("creative_tone", "sleek")

    # Scene descriptions matched to the brief's creative_tone values.
    # These mirror the lighting presets in the C4D pipeline scripts.
    tone_scenes = {
        "sleek": (
            "intimate jazz club interior, cool blue ambient stage lighting, "
            "dark atmospheric background, smooth polished floor reflection, "
            "subtle bokeh depth of field, cinematic photography, premium feel"
        ),
        "warm": (
            "warm concert hall interior, golden amber stage lighting, "
            "rich wooden textures, soft bokeh, cinematic, professional photography"
        ),
        "dramatic": (
            "dramatic concert stage, single spotlight from above, deep shadows, "
            "high contrast lighting, dark premium atmosphere, cinematic"
        ),
    }

    scene = tone_scenes.get(tone, tone_scenes["sleek"])

    # Full prompt — we specify no instruments so the saxophone in the
    # AE composite reads clearly against the background
    prompt = (
        f"{scene}, "
        f"product photography background, 16:9 wide format, "
        f"no text, no people, no musical instruments, no saxophone, "
        f"high quality, photorealistic, clean composition"
    )

    print(f"[Brief] Tone: {tone}")
    print(f"[Prompt] {prompt[:100]}...")
    return prompt


# ─────────────────────────────────────────────
# STEP 3 — SUBMIT TO COMFYUI AND WAIT
# ─────────────────────────────────────────────

def load_workflow():
    """Loads the Flux background workflow template from disk."""
    path = COMFYUI_WORKFLOWS_DIR / "background_workflow.json"
    if not path.exists():
        print(f"[ERROR] Workflow not found: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def inject_into_workflow(workflow, prompt, width, height, prefix):
    """
    Returns a modified copy of the workflow with our values injected.

    Uses deepcopy so the original template dict stays clean — important
    if this function is ever called in a loop for multiple variants.
    """
    wf = copy.deepcopy(workflow)

    # Inject our scene description
    wf[NODE["positive_prompt"]]["inputs"]["text"] = prompt

    # Unique prefix so we can find THIS job's output in ComfyUI's output folder
    wf[NODE["save_image"]]["inputs"]["filename_prefix"] = prefix

    # How many steps Flux takes to refine the image (more = better quality, slower)
    wf[NODE["scheduler"]]["inputs"]["steps"] = STEPS

    # Random seed so each run generates a different image
    wf[NODE["seed"]]["inputs"]["noise_seed"] = int(uuid.uuid4().int % (2**32))

    # Output resolution — 1920x1080 for 16:9
    wf[NODE["latent"]]["inputs"]["width"]      = width
    wf[NODE["latent"]]["inputs"]["height"]     = height
    wf[NODE["latent"]]["inputs"]["batch_size"] = 1

    return wf


def submit_job(workflow):
    """Posts the workflow JSON to ComfyUI and returns the prompt_id."""
    try:
        resp = requests.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow},
            timeout=30
        )
        resp.raise_for_status()
        prompt_id = resp.json()["prompt_id"]
        print(f"[ComfyUI] Job submitted — ID: {prompt_id[:8]}...")
        return prompt_id
    except requests.ConnectionError:
        print(f"[ERROR] Cannot reach ComfyUI at {COMFYUI_URL}")
        print("        Open ComfyUI Desktop and wait for it to finish loading.")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Failed to submit job: {e}")
        sys.exit(1)


def wait_for_completion(prompt_id):
    """
    Polls ComfyUI's /history endpoint until the job appears there.
    Jobs only appear in /history once they are DONE.
    Prints dots so you can see it's working.
    """
    elapsed = 0
    print("[ComfyUI] Generating background", end="", flush=True)
    while elapsed < MAX_WAIT:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        print(".", end="", flush=True)
        try:
            resp = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
            resp.raise_for_status()
            if prompt_id in resp.json():
                print(f" done ({elapsed}s)")
                return True
        except Exception:
            pass  # Keep retrying until timeout
    print()
    print(f"[ERROR] Timed out after {MAX_WAIT}s — ComfyUI may be stuck")
    return False


def find_comfyui_output(prefix):
    """
    Finds the generated PNG in ComfyUI's output folder by matching the filename prefix.
    ComfyUI saves files as: {prefix}_00001_.png
    """
    if not COMFYUI_OUTPUT_DIR.exists():
        print(f"[ERROR] ComfyUI output folder not found: {COMFYUI_OUTPUT_DIR}")
        print("        Check that COMFYUI_OUTPUT_DIR is set correctly in this script.")
        return None

    matches = list(COMFYUI_OUTPUT_DIR.glob(f"{prefix}_*.png"))
    if not matches:
        print(f"[ERROR] No output found with prefix '{prefix}' in {COMFYUI_OUTPUT_DIR}")
        return None

    # Take the newest match in case of duplicates from previous runs
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0]


# ─────────────────────────────────────────────
# STEP 4 — WRITE DATA JSON FOR AFTER EFFECTS
# ─────────────────────────────────────────────

def write_data_json(brief, bg_path, data_json_path):
    """
    Writes the sidecar JSON file that the After Effects startup script reads.

    The startup script (zz_yosuki_populate.jsx) lives in AE's Scripts/Startup/ folder.
    When aerender opens the .aep, that script fires automatically and:
      - Relinks BG_IMAGE_PLACEHOLDER  → our ComfyUI background PNG
      - Relinks PRODUCT_IMAGE_PLACEHOLDER → the sax1_cutout.png (transparent)
      - Sets SERIES_TITLE_TEXT, TAGLINE_TEXT, CTA_TEXT from the values below

    Field names here must match exactly what the JSX reads.
    """
    data = {
        "tagline":            brief.get("tagline", ""),
        "series_title":       "Saxophone Model 1",   # displayed in the AE text layer
        "cta":                brief.get("cta", ""),
        "bg_image_path":      bg_path.as_posix(),
        "product_image_path": PRODUCT_CUTOUT.as_posix(),
        "variant_id":         VARIANT_ID,
        "market":             "US",
        "ratio":              "16x9",
        "comp_name":          AE_MAIN_COMP_NAME,
    }

    with open(data_json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[AE]   Data JSON written: {data_json_path.name}")
    print(f"       Tagline: {data['tagline']}")
    print(f"       CTA:     {data['cta']}")


# ─────────────────────────────────────────────
# STEP 5 — RENDER FINAL OUTPUT VIA AERENDER
# ─────────────────────────────────────────────

def run_aerender(project_path, render_output_path):
    """
    Calls aerender.exe (After Effects command-line renderer) to produce the final MP4.

    The zz_yosuki_populate.jsx startup script handles all the footage relinking
    and text population IN MEMORY before the render begins — so the footage
    paths we wrote to _data.json get applied correctly.

    Returns True if the render produced a valid output file.
    """
    if not Path(AERENDER_PATH).exists():
        print(f"[ERROR] aerender.exe not found: {AERENDER_PATH}")
        print("        Check AERENDER_PATH in config.py")
        return False

    cmd = [
        AERENDER_PATH,
        "-project",    str(project_path),
        "-comp",       AE_MAIN_COMP_NAME,
        "-output",     str(render_output_path),
        "-OMtemplate", AE_OUTPUT_MODULE,
        "-v",          "ERRORS",              # only show errors in terminal output
    ]

    print(f"[AE]   Rendering... (this may take a few minutes)")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode != 0:
            print(f"[ERROR] aerender failed (exit code {result.returncode})")
            if result.stderr:
                print(f"        {result.stderr[-400:]}")
            return False

        if not render_output_path.exists() or render_output_path.stat().st_size == 0:
            print(f"[ERROR] Output file missing or empty: {render_output_path.name}")
            return False

        size_mb = render_output_path.stat().st_size / (1024 * 1024)
        print(f"[AE]   Render complete: {render_output_path.name} ({size_mb:.1f} MB)")
        return True

    except subprocess.TimeoutExpired:
        print("[ERROR] aerender timed out after 10 minutes")
        return False
    except Exception as e:
        print(f"[ERROR] Failed to run aerender: {e}")
        return False


# ─────────────────────────────────────────────
# MAIN — runs all 5 steps in sequence
# ─────────────────────────────────────────────

def main():
    print()
    print("=" * 60)
    print("  YOSUKI — Saxophone 16:9 Full Pipeline Test")
    print("=" * 60)

    # ── Read the brief ─────────────────────────────────────────────
    if not BRIEF_PATH.exists():
        print(f"[ERROR] Brief not found: {BRIEF_PATH}")
        sys.exit(1)
    with open(BRIEF_PATH, encoding="utf-8") as f:
        brief = json.load(f)
    print(f"[Brief] {brief['brand']} / {brief['product']} / {brief['creative_tone']} / {brief['output_format']}")

    # ── Step 1: Find C4D reference render ─────────────────────────
    print()
    print("[ Step 1 ] C4D Reference Render")
    print("-" * 40)
    c4d_render = find_latest_c4d_render()
    if not c4d_render:
        sys.exit(1)

    # ── Step 2: Build background prompt ───────────────────────────
    print()
    print("[ Step 2 ] Build ComfyUI Prompt")
    print("-" * 40)
    prompt = build_background_prompt(brief)

    # ── Step 3: Generate background in ComfyUI ────────────────────
    print()
    print("[ Step 3 ] Generate Background (ComfyUI + Flux)")
    print("-" * 40)

    # Check ComfyUI is reachable before doing anything else
    try:
        requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
        print(f"[ComfyUI] Connected at {COMFYUI_URL}")
    except requests.ConnectionError:
        print(f"[ERROR] ComfyUI is not running at {COMFYUI_URL}")
        print("        Open ComfyUI Desktop, wait for it to fully load, then re-run.")
        sys.exit(1)

    BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)
    bg_output_path = BACKGROUNDS_DIR / f"{VARIANT_ID}_bg.png"

    if bg_output_path.exists():
        # Skip generation if we already have a background — saves time during testing
        print(f"[ComfyUI] Background already exists — skipping generation")
        print(f"          Delete {bg_output_path.name} to regenerate on next run")
    else:
        job_prefix = "yosuki_sax_16x9_test"
        workflow   = load_workflow()
        workflow   = inject_into_workflow(workflow, prompt, 1920, 1080, job_prefix)

        prompt_id = submit_job(workflow)
        completed = wait_for_completion(prompt_id)
        if not completed:
            sys.exit(1)

        source_file = find_comfyui_output(job_prefix)
        if not source_file:
            sys.exit(1)

        shutil.copy2(source_file, bg_output_path)
        size_kb = bg_output_path.stat().st_size // 1024
        print(f"[ComfyUI] Background saved: {bg_output_path.name} ({size_kb} KB)")

    # ── Step 4: Prepare AE project ────────────────────────────────
    print()
    print("[ Step 4 ] Prepare After Effects Project")
    print("-" * 40)

    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    RENDERS_DIR.mkdir(parents=True, exist_ok=True)

    project_path   = PROJECTS_DIR / f"{VARIANT_ID}.aep"
    data_json_path = PROJECTS_DIR / f"{VARIANT_ID}_data.json"
    render_path    = RENDERS_DIR  / f"{VARIANT_ID}.mp4"

    if not AE_TEMPLATE.exists():
        print(f"[ERROR] AE template not found: {AE_TEMPLATE}")
        print("        Build landscape_16.9.aep first (see ae_templates/README.md)")
        sys.exit(1)

    if not PRODUCT_CUTOUT.exists():
        print(f"[ERROR] Product cutout not found: {PRODUCT_CUTOUT}")
        sys.exit(1)

    shutil.copy2(AE_TEMPLATE, project_path)
    print(f"[AE]   Template copied: {project_path.name}")

    write_data_json(brief, bg_output_path, data_json_path)

    # ── Step 5: Render via aerender ───────────────────────────────
    print()
    print("[ Step 5 ] Render Final Output (aerender)")
    print("-" * 40)
    success = run_aerender(project_path, render_path)

    # ── Final summary ─────────────────────────────────────────────
    print()
    print("=" * 60)
    if success:
        print("  PIPELINE COMPLETE")
        print()
        print(f"  C4D reference:  {c4d_render.name}")
        print(f"  BG generated:   {bg_output_path.name}")
        print(f"  Final render:   {render_path}")
    else:
        print("  PIPELINE FAILED — check errors above")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
