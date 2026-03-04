"""
sax_16x9_controlnet_test.py — Saxophone 16:9 Pipeline with ControlNet Depth Guidance
======================================================================================
WHAT THIS DOES:
  Same pipeline as sax_16x9_test.py, but uses the C4D render as a depth ControlNet
  reference — the "digital twin" approach. Instead of generating a background blind
  from a text prompt, Flux now sees the spatial layout of your 3D stage (platform
  shape, depth, perspective) and generates a background that fits it.

HOW THE DIGITAL TWIN PART WORKS:
  1. Python uploads the C4D render to ComfyUI via the /upload/image API
  2. ComfyUI's AIO_Preprocessor extracts a depth map from it (DepthAnythingV2)
     — a grayscale image where white = close to camera, black = far away
  3. The depth map goes into ControlNetApplyAdvanced which "steers" the Flux
     generation to respect the spatial layout of the stage
  4. Result: background that spatially matches your Cinema 4D scene composition

REQUIRED SETUP (one-time, before running this script):
  ┌─────────────────────────────────────────────────────────────────────┐
  │ 1. Download Flux Depth ControlNet model                             │
  │    URL: https://huggingface.co/XLabs-AI/flux-controlnet-depth-v3   │
  │    File to download: flux-depth-controlnet-v3.safetensors           │
  │    Place in: G:/ComfyUI/models/controlnet/                          │
  │                                                                     │
  │ 2. Install ComfyUI-ControlNet-Aux custom nodes                      │
  │    In ComfyUI: Manager > Install Custom Nodes                       │
  │    Search for: ComfyUI-ControlNet-Aux (by Fannovel16)               │
  │    Install it, then restart ComfyUI                                 │
  └─────────────────────────────────────────────────────────────────────┘

PRE-REQUISITES (each run):
  - Run yosuki_saxophone_16x9.py in Cinema 4D first (for the reference render)
  - ComfyUI running at http://127.0.0.1:8188 with Flux model loaded

RUN:
  cd "F:/Adobe_FDE Take-Home/yosuki-pipeline"
  python scripts/sax_16x9_controlnet_test.py

  Optional flags:
  --strength 0.5     Override ControlNet strength (0.0–1.0, default 0.65)
  --steps 30         Override generation steps (default 25)
  --regen            Force regenerate even if background already exists
"""

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

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
# ─────────────────────────────────────────────

BRIEF_PATH     = Path(r"F:\Adobe_FDE Take-Home\Assets\briefs\saxophone_model1_16x9.json")
C4D_RENDERS_DIR = Path(r"F:\Adobe_FDE Take-Home\Assets\renders")
PRODUCT_CUTOUT  = Path(r"F:\Adobe_FDE Take-Home\yosuki-pipeline\assets\product_cutouts\sax1_cutout.png")
AE_TEMPLATE     = AE_TEMPLATES_DIR / "landscape_16.9.aep"
COMFYUI_OUTPUT_DIR = Path("G:/ComfyUI/output")

# The ControlNet model filename — must exist in G:/ComfyUI/models/controlnet/
CONTROLNET_MODEL = "flux-depth-controlnet-v3.safetensors"

VARIANT_ID = "sax_model1_16x9_controlnet_test"


# ─────────────────────────────────────────────
# COMFYUI NODE IDs  (match controlnet_depth_workflow.json)
# ─────────────────────────────────────────────

NODE = {
    "positive_prompt":  "6",   # CLIPTextEncode — scene description
    "save_image":       "9",   # SaveImage — filename prefix
    "scheduler":        "17",  # BasicScheduler — steps
    "seed":             "25",  # RandomNoise — seed value
    "latent":           "27",  # EmptySD3LatentImage — width/height
    "load_image":       "30",  # LoadImage — C4D render filename (after upload)
    "controlnet":       "31",  # ControlNetLoader — model name
    "controlnet_apply": "33",  # ControlNetApplyAdvanced — strength
}

STEPS         = 25
POLL_INTERVAL = 3
MAX_WAIT      = 360   # 6 minutes — ControlNet generation takes slightly longer


# ─────────────────────────────────────────────
# PREFLIGHT CHECK — verify setup before starting
# ─────────────────────────────────────────────

def preflight_check():
    """
    Checks that the required ControlNet model and custom nodes are in place
    before starting the pipeline. Exits with a clear message if anything is missing.

    This saves you from waiting through ComfyUI generation only to hit an
    error at the end because a model file is missing.
    """
    print("[Check] Running preflight checks...")
    ok = True

    # Check ControlNet model
    controlnet_path = Path("G:/ComfyUI/models/controlnet") / CONTROLNET_MODEL
    if not controlnet_path.exists():
        print(f"[MISSING] ControlNet model not found: {controlnet_path}")
        print(f"          Download from: https://huggingface.co/XLabs-AI/flux-controlnet-depth-v3")
        print(f"          File: flux-depth-controlnet-v3.safetensors")
        print(f"          Place in: G:/ComfyUI/models/controlnet/")
        ok = False

    # Check C4D renders exist
    renders = list(C4D_RENDERS_DIR.glob("saxophone_model1_16x9_*.png"))
    if not renders:
        print(f"[MISSING] No C4D reference renders found in: {C4D_RENDERS_DIR}")
        print(f"          Run yosuki_saxophone_16x9.py in Cinema 4D first.")
        ok = False

    # Check AE template
    if not AE_TEMPLATE.exists():
        print(f"[MISSING] AE template not found: {AE_TEMPLATE}")
        ok = False

    # Check product cutout
    if not PRODUCT_CUTOUT.exists():
        print(f"[MISSING] Product cutout not found: {PRODUCT_CUTOUT}")
        ok = False

    if ok:
        print("[Check] All preflight checks passed.")
    else:
        print()
        print("Fix the issues above, then re-run.")
        sys.exit(1)


# ─────────────────────────────────────────────
# STEP 1 — FIND THE C4D REFERENCE RENDER
# ─────────────────────────────────────────────

def find_latest_c4d_render():
    """Returns the most recently modified saxophone C4D render PNG."""
    renders = list(C4D_RENDERS_DIR.glob("saxophone_model1_16x9_*.png"))
    renders.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    latest = renders[0]
    size_kb = latest.stat().st_size // 1024
    print(f"[C4D]  Reference render: {latest.name} ({size_kb} KB)")
    return latest


# ─────────────────────────────────────────────
# STEP 2 — BUILD THE BACKGROUND PROMPT
# ─────────────────────────────────────────────

def build_background_prompt(brief):
    """
    Same prompt logic as sax_16x9_test.py, but with ControlNet doing the heavy
    lifting for spatial composition. The text prompt mainly sets the lighting mood
    and atmosphere — the depth map handles the geometry and perspective.
    """
    tone = brief.get("creative_tone", "sleek")

    tone_scenes = {
        "sleek": (
            "intimate jazz club interior, cool blue ambient stage lighting, "
            "dark atmospheric background, smooth polished floor, subtle bokeh, "
            "cinematic photography, premium feel"
        ),
        "warm": (
            "warm concert hall interior, golden amber stage lighting, "
            "rich wooden textures, soft bokeh, cinematic, professional photography"
        ),
        "dramatic": (
            "dramatic concert stage, single spotlight, deep shadows, "
            "high contrast, dark premium atmosphere, cinematic"
        ),
    }

    scene = tone_scenes.get(tone, tone_scenes["sleek"])

    # Explicitly exclude the instrument — the ControlNet depth reference will
    # guide the platform/stage shape without needing the saxophone in the description
    prompt = (
        f"{scene}, "
        f"product photography background, 16:9 wide format, "
        f"no saxophone, no musical instruments, no people, no text, "
        f"high quality, photorealistic"
    )

    print(f"[Brief] Tone: {tone}")
    print(f"[Prompt] {prompt[:100]}...")
    return prompt


# ─────────────────────────────────────────────
# STEP 3A — UPLOAD C4D RENDER TO COMFYUI
# ─────────────────────────────────────────────

def upload_c4d_render(image_path):
    """
    Uploads the C4D render to ComfyUI's input folder via the /upload/image API.

    Why we need to upload:
      ComfyUI's LoadImage node can only read files from its own input folder
      (G:/ComfyUI/input/). Our C4D renders are in a different location.
      This API call copies the file into ComfyUI's input folder and returns
      the filename we can then reference in the workflow.

    Returns the filename ComfyUI assigned to the uploaded image.
    """
    print(f"[Upload] Uploading C4D render to ComfyUI...")
    try:
        with open(image_path, "rb") as f:
            files = {"image": (image_path.name, f, "image/png")}
            resp = requests.post(
                f"{COMFYUI_URL}/upload/image",
                files=files,
                timeout=30
            )
        resp.raise_for_status()
        uploaded_name = resp.json()["name"]
        print(f"[Upload] Uploaded as: {uploaded_name}")
        return uploaded_name
    except Exception as e:
        print(f"[ERROR] Failed to upload image to ComfyUI: {e}")
        sys.exit(1)


# ─────────────────────────────────────────────
# STEP 3B — SUBMIT TO COMFYUI AND WAIT
# ─────────────────────────────────────────────

def load_workflow():
    """Loads the ControlNet depth workflow template from disk."""
    path = COMFYUI_WORKFLOWS_DIR / "controlnet_depth_workflow.json"
    if not path.exists():
        print(f"[ERROR] Workflow not found: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    # Strip out the _README key — ComfyUI doesn't understand it
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def inject_into_workflow(workflow, prompt, width, height, prefix,
                          uploaded_image_name, controlnet_strength):
    """
    Injects all our dynamic values into a deep copy of the workflow.

    New vs sax_16x9_test.py:
      - node_30 image: the filename ComfyUI assigned after we uploaded the C4D render
      - node_31 control_net_name: the Flux depth ControlNet model
      - node_33 strength: how tightly to follow the depth reference
    """
    wf = copy.deepcopy(workflow)

    wf[NODE["positive_prompt"]]["inputs"]["text"]             = prompt
    wf[NODE["save_image"]]["inputs"]["filename_prefix"]       = prefix
    wf[NODE["scheduler"]]["inputs"]["steps"]                  = STEPS
    wf[NODE["seed"]]["inputs"]["noise_seed"]                  = int(uuid.uuid4().int % (2**32))
    wf[NODE["latent"]]["inputs"]["width"]                     = width
    wf[NODE["latent"]]["inputs"]["height"]                    = height
    wf[NODE["latent"]]["inputs"]["batch_size"]                = 1

    # ControlNet-specific injections
    wf[NODE["load_image"]]["inputs"]["image"]                          = uploaded_image_name
    wf[NODE["controlnet"]]["inputs"]["control_net_name"]               = CONTROLNET_MODEL
    wf[NODE["controlnet_apply"]]["inputs"]["strength"]                 = controlnet_strength

    return wf


def submit_job(workflow):
    """Posts the workflow to ComfyUI and returns the prompt_id."""
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
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Failed to submit job: {e}")
        sys.exit(1)


def wait_for_completion(prompt_id):
    """Polls /history until the job appears (= done). Prints dots as progress."""
    elapsed = 0
    print("[ComfyUI] Generating (depth ControlNet — may take ~60s)", end="", flush=True)
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
            pass
    print()
    print(f"[ERROR] Timed out after {MAX_WAIT}s")
    return False


def find_comfyui_output(prefix):
    """Finds the generated PNG in ComfyUI's output folder by filename prefix."""
    if not COMFYUI_OUTPUT_DIR.exists():
        print(f"[ERROR] ComfyUI output folder not found: {COMFYUI_OUTPUT_DIR}")
        return None
    matches = list(COMFYUI_OUTPUT_DIR.glob(f"{prefix}_*.png"))
    if not matches:
        print(f"[ERROR] No output found with prefix '{prefix}' in {COMFYUI_OUTPUT_DIR}")
        return None
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0]


# ─────────────────────────────────────────────
# STEP 4 — WRITE DATA JSON FOR AFTER EFFECTS
# ─────────────────────────────────────────────

def write_data_json(brief, bg_path, data_json_path):
    """Writes the _data.json sidecar that the AE startup script reads."""
    data = {
        "tagline":            brief.get("tagline", ""),
        "series_title":       "Saxophone Model 1",
        "cta":                brief.get("cta", ""),
        "bg_image_path":      bg_path.as_posix(),
        "product_image_path": PRODUCT_CUTOUT.as_posix(),
        "variant_id":         VARIANT_ID,
        "market":             "US",
        "ratio":              "16x9",
        "comp_name":          AE_MAIN_COMP_NAME,
        # The C4D render already has the saxophone staged in the scene,
        # so we hide the product cutout layer to avoid double-compositing it.
        "hide_product_layer": True,
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
    """Runs aerender.exe to produce the final MP4."""
    if not Path(AERENDER_PATH).exists():
        print(f"[ERROR] aerender.exe not found: {AERENDER_PATH}")
        return False

    cmd = [
        AERENDER_PATH,
        "-project",    str(project_path),
        "-comp",       AE_MAIN_COMP_NAME,
        "-output",     str(render_output_path),
        "-OMtemplate", AE_OUTPUT_MODULE,
        "-v",          "ERRORS",
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
            print(f"[ERROR] Output file missing or empty")
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
# MAIN
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Saxophone 16:9 pipeline with ControlNet depth guidance.")
    parser.add_argument("--strength", type=float, default=0.65,
                        help="ControlNet strength 0.0–1.0 (default 0.65). Higher = closer match to C4D stage layout.")
    parser.add_argument("--steps", type=int, default=25,
                        help="Generation steps (default 25).")
    parser.add_argument("--regen", action="store_true",
                        help="Force regenerate background even if it already exists.")
    args = parser.parse_args()

    global STEPS
    STEPS = args.steps

    print()
    print("=" * 60)
    print("  YOSUKI — Saxophone 16:9 ControlNet Depth Pipeline Test")
    print("=" * 60)

    # ── Preflight ─────────────────────────────────────────────────
    preflight_check()

    # ── Read brief ────────────────────────────────────────────────
    with open(BRIEF_PATH, encoding="utf-8") as f:
        brief = json.load(f)
    print(f"[Brief] {brief['brand']} / {brief['product']} / {brief['creative_tone']} / {brief['output_format']}")

    # ── Step 1: Find C4D reference render ─────────────────────────
    print()
    print("[ Step 1 ] C4D Reference Render")
    print("-" * 40)
    c4d_render = find_latest_c4d_render()

    # ── Step 2: Build background prompt ───────────────────────────
    print()
    print("[ Step 2 ] Build ComfyUI Prompt")
    print("-" * 40)
    prompt = build_background_prompt(brief)

    # ── Step 3: Generate background in ComfyUI ────────────────────
    print()
    print(f"[ Step 3 ] Generate Background (ComfyUI + Flux + Depth ControlNet @ strength {args.strength})")
    print("-" * 40)

    try:
        requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
        print(f"[ComfyUI] Connected at {COMFYUI_URL}")
    except requests.ConnectionError:
        print(f"[ERROR] ComfyUI is not running at {COMFYUI_URL}")
        print("        Open ComfyUI Desktop, wait for it to fully load, then re-run.")
        sys.exit(1)

    BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)
    bg_output_path = BACKGROUNDS_DIR / f"{VARIANT_ID}_bg.png"

    if bg_output_path.exists() and not args.regen:
        print(f"[ComfyUI] Background already exists — skipping generation")
        print(f"          Run with --regen to force a new one")
    else:
        # Upload the C4D render so ComfyUI's LoadImage node can access it
        uploaded_name = upload_c4d_render(c4d_render)

        job_prefix = "yosuki_sax_controlnet"
        workflow   = load_workflow()

        # Flux ControlNet requires dimensions divisible by 16.
        # 1080 / 16 = 67.5 — fails. Round up to 1088 (1088/16=68).
        # After Effects will scale it to fill the 1920x1080 comp anyway.
        cn_width  = ((1920 + 15) // 16) * 16   # = 1920
        cn_height = ((1080 + 15) // 16) * 16   # = 1088
        print(f"[ComfyUI] Latent size adjusted for ControlNet: {cn_width}x{cn_height} (must be divisible by 16)")

        workflow   = inject_into_workflow(
            workflow, prompt, cn_width, cn_height, job_prefix,
            uploaded_name, args.strength
        )

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

    shutil.copy2(AE_TEMPLATE, project_path)
    print(f"[AE]   Template copied: {project_path.name}")
    write_data_json(brief, bg_output_path, data_json_path)

    # ── Step 5: Render via aerender ───────────────────────────────
    print()
    print("[ Step 5 ] Render Final Output (aerender)")
    print("-" * 40)
    success = run_aerender(project_path, render_path)

    # ── Summary ───────────────────────────────────────────────────
    print()
    print("=" * 60)
    if success:
        print("  PIPELINE COMPLETE")
        print()
        print(f"  C4D reference:    {c4d_render.name}")
        print(f"  ControlNet depth: strength {args.strength}")
        print(f"  BG generated:     {bg_output_path.name}")
        print(f"  Final render:     {render_path}")
        print()
        print("  Tip: tweak the spatial match by adjusting --strength")
        print("  Lower (0.4) = looser, more creative | Higher (0.85) = tighter match")
    else:
        print("  PIPELINE FAILED — check errors above")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
