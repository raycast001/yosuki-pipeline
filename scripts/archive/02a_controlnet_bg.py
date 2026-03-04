"""
02a_controlnet_bg.py — Generate a background using Flux + ControlNet Depth
===========================================================================
PURPOSE:
  Takes a Cinema 4D render and uses it as a depth reference to guide Flux
  background generation. This is the "Digital Twin" approach:

    1. Upload the C4D render to ComfyUI
    2. DepthAnythingV2 extracts a depth map from it
    3. Flux generates a stylized background that matches the scene's spatial
       layout — floor plane, platform shape, depth perspective
    4. Saves the result to output/backgrounds/{product_id}_{ratio}.png

  After this script, run 02b_generate_bg_videos.py to animate the PNG
  into a short video using LTX2 i2v.

FULL PIPELINE:
  C4D render  →  ControlNet Depth (this script)  →  PNG background
                                                        ↓
                                               LTX2 i2v (02b)
                                                        ↓
                                              Animated MP4 background
                                                        ↓
                                                After Effects render

WHY THIS IS BETTER THAN TEXT-PROMPT ONLY:
  The standard background_workflow.json generates backgrounds from a text
  prompt alone — the AI has no idea what the 3D stage actually looks like.
  With ControlNet depth, the AI reads the spatial layout from the C4D render
  and generates a background that matches it. The product placement, floor
  plane, and camera perspective all match the 3D composition.

NODE MAP (controlnet_depth_workflow.json):
  "6"  — CLIPTextEncode          → scene description prompt
  "9"  — SaveImage               → output filename prefix (injected by us)
  "17" — BasicScheduler          → steps count
  "25" — RandomNoise             → seed (randomised each run)
  "27" — EmptySD3LatentImage     → canvas size (must be divisible by 16)
  "30" — LoadImage               → uploaded C4D render filename
  "33" — ControlNetApplyAdvanced → strength of depth guidance (0.5–0.85)

RUN:
  python scripts/02a_controlnet_bg.py --product sax_signature --ratio 16x9 --source "F:/Adobe_FDE Take-Home/Assets/renders/saxophone_model1_16x9.png"
  python scripts/02a_controlnet_bg.py --product sax_signature --ratio 16x9 --source "..." --strength 0.5
  python scripts/02a_controlnet_bg.py --product sax_signature --ratio 16x9 --source "..." --force
"""

import argparse
import copy
import json
import shutil
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import os
os.environ["PYTHONIOENCODING"] = "utf-8"

import requests

from config import (
    BACKGROUNDS_DIR,
    COMFYUI_URL,
    COMFYUI_WORKFLOWS_DIR,
    VARIANTS_JSON,
)
from scripts.utils.logger import log


# ─────────────────────────────────────────────
# COMFYUI OUTPUT FOLDER
# Where ComfyUI Desktop saves generated images.
# ─────────────────────────────────────────────
COMFYUI_OUTPUT_DIR = Path("G:/ComfyUI/output")

# ─────────────────────────────────────────────
# DIMENSIONS PER RATIO (must be divisible by 16)
# Flux ControlNet uses patch-based processing that requires both
# width and height to divide evenly by 16. Standard 1080 fails
# (1080 ÷ 16 = 67.5), so we round up to 1088.
# AE scales the output to fill its comp — the extra 8px is invisible.
# ─────────────────────────────────────────────
CONTROLNET_DIMENSIONS = {
    "16x9":              (1920, 1088),   # 1080 → 1088 (next multiple of 16)
    "1x1":               (1088, 1088),   # 1080 → 1088
    "billboard_970x250": (2912, 752),    # 2910 → 2912, 750 → 752
}

# ─────────────────────────────────────────────
# WORKFLOW DEFINITIONS
# Two ControlNet workflows are supported:
#
#   "depth"  — Flux + ControlNet depth (controlnet_depth_workflow.json)
#              Uses DepthAnythingV2 to extract depth from C4D render.
#              25 steps, guided by scene depth structure.
#
#   "turbo"  — Z-Image-Turbo + Canny ControlNet (image_z_image_turbo_fun_union_controlnet.json)
#              Uses Canny edge detection on the C4D render.
#              9 steps, very fast, faithfully follows the C4D outlines.
#              Output size auto-matches the input image — no div-by-16 restriction.
# ─────────────────────────────────────────────

# Node IDs for the Flux depth workflow
NODE_DEPTH = {
    "positive_prompt": "6",    # CLIPTextEncode — the scene description
    "save_image":      "9",    # SaveImage — filename_prefix
    "scheduler":       "17",   # BasicScheduler — steps
    "seed":            "25",   # RandomNoise — noise_seed
    "latent":          "27",   # EmptySD3LatentImage — width, height
    "load_image":      "30",   # LoadImage — the C4D reference render
    "controlnet":      "33",   # ControlNetApplyAdvanced — strength
}

# Node IDs for the Flux Canny Dev workflow (flux1-canny-dev.safetensors)
# This is Flux's dedicated native Canny model — fine-tuned specifically for
# Canny-based generation. Much more photorealistic than using ControlNet on top.
# Output size auto-matches the input image (no div-by-16 restriction).
NODE_FLUX_CANNY = {
    "load_image":      "17",   # LoadImage — the C4D render
    "canny":           "18",   # Canny — low_threshold / high_threshold
    "positive_prompt": "23",   # CLIPTextEncode — scene description
    "guidance":        "26",   # FluxGuidance — guidance strength (default 30)
    "save_image":      "9",    # SaveImage — filename_prefix
    "sampler":         "3",    # KSampler — seed, steps
}

# Node IDs for the Z-Image-Turbo Canny workflow
NODE_TURBO = {
    "load_image":      "58",     # LoadImage — the C4D reference render
    "save_image":      "9",      # SaveImage — filename_prefix
    "seed":            "70:44",  # KSampler — seed field
    "steps":           "70:44",  # KSampler — steps field
    "positive_prompt": "70:45",  # CLIPTextEncode — text prompt
    "controlnet":      "70:60",  # QwenImageDiffsynthControlnet — strength
    "canny":           "57",     # Canny — low_threshold / high_threshold
}

# Generation settings
STEPS          = 20    # Steps — turbo default is 9 but 20 gives more refined detail
POLL_INTERVAL  = 3     # seconds between status checks
MAX_WAIT       = 900   # 15 minutes max


def load_workflow(workflow: str) -> dict:
    """Loads the specified workflow JSON and strips non-ComfyUI keys."""
    names = {
        "depth":       "controlnet_depth_workflow.json",
        "turbo":       "image_z_image_turbo_fun_union_controlnet.json",
        "flux_canny":  "flux_canny_model_example.json",
    }
    filename = names.get(workflow)
    if not filename:
        log.error(f"Unknown workflow: '{workflow}'. Use 'depth' or 'turbo'.")
        sys.exit(1)
    path = COMFYUI_WORKFLOWS_DIR / filename
    if not path.exists():
        log.error(f"Workflow not found: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    # Strip documentation keys that ComfyUI would reject
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def upload_image(image_path: Path) -> str:
    """
    Uploads the C4D render to ComfyUI's input folder.
    Returns the filename ComfyUI assigned (used in the LoadImage node).
    """
    log.info(f"  Uploading C4D render to ComfyUI: {image_path.name}")
    with open(image_path, "rb") as f:
        resp = requests.post(
            f"{COMFYUI_URL}/upload/image",
            files={"image": (image_path.name, f, "image/png")},
            data={"type": "input", "overwrite": "true"},
            timeout=30,
        )
    resp.raise_for_status()
    uploaded_name = resp.json()["name"]
    log.info(f"  Uploaded as: {uploaded_name}")
    return uploaded_name


def build_workflow(base_workflow: dict, workflow: str, uploaded_image: str,
                   prompt: str, width: int, height: int, prefix: str,
                   strength: float, steps: int) -> dict:
    """
    Returns a modified copy of the chosen workflow with our values injected.
    Routes to the correct injection logic based on workflow type.
    """
    wf = copy.deepcopy(base_workflow)

    if workflow == "flux_canny":
        # ── Flux Canny Dev (flux1-canny-dev.safetensors) ──────────────
        # Native Flux Canny model — fine-tuned for Canny-based generation.
        # Highly photorealistic. Output size auto-matches the input image.

        # C4D render — Canny edges will be extracted from this
        wf[NODE_FLUX_CANNY["load_image"]]["inputs"]["image"] = uploaded_image

        # Unique prefix to find the output PNG in G:/ComfyUI/output/
        wf[NODE_FLUX_CANNY["save_image"]]["inputs"]["filename_prefix"] = prefix

        # Random seed — different result each run
        wf[NODE_FLUX_CANNY["sampler"]]["inputs"]["seed"] = int(uuid.uuid4().int % (2**32))

        # Generation steps
        wf[NODE_FLUX_CANNY["sampler"]]["inputs"]["steps"] = steps

        # Scene description prompt
        wf[NODE_FLUX_CANNY["positive_prompt"]]["inputs"]["text"] = prompt

        # Canny thresholds — controls how many edges are picked up from the C4D scene
        wf[NODE_FLUX_CANNY["canny"]]["inputs"]["low_threshold"] = 0.05
        wf[NODE_FLUX_CANNY["canny"]]["inputs"]["high_threshold"] = 0.1

    elif workflow == "turbo":
        # ── Z-Image-Turbo Canny ControlNet ────────────────────────
        # Injects into the Z-Image-Turbo workflow nodes.
        # Output size is auto-matched to the input image via GetImageSize node —
        # no need to set width/height manually.

        # C4D render — Canny edges will be extracted from this
        wf[NODE_TURBO["load_image"]]["inputs"]["image"] = uploaded_image

        # Unique prefix to find the output PNG in G:/ComfyUI/output/
        wf[NODE_TURBO["save_image"]]["inputs"]["filename_prefix"] = prefix

        # Random seed — different result each run
        wf[NODE_TURBO["seed"]]["inputs"]["seed"] = int(uuid.uuid4().int % (2**32))

        # Steps — more steps = more refined detail (default 9 in workflow, we use 20)
        wf[NODE_TURBO["steps"]]["inputs"]["steps"] = steps

        # Text prompt (the turbo model works well with empty or simple prompts)
        wf[NODE_TURBO["positive_prompt"]]["inputs"]["text"] = prompt

        # ControlNet strength — how tightly to follow the C4D Canny edges
        wf[NODE_TURBO["controlnet"]]["inputs"]["strength"] = strength

        # Canny thresholds — lower values = more edges captured from the C4D scene
        # low_threshold:  0.05 (was 0.1)  — picks up weaker/thinner edges
        # high_threshold: 0.1  (was 0.2)  — lowers the bar for what counts as a strong edge
        # Together these preserve more structural detail: chair legs, curtain folds, wall frames
        wf[NODE_TURBO["canny"]]["inputs"]["low_threshold"] = 0.07
        wf[NODE_TURBO["canny"]]["inputs"]["high_threshold"] = 0.15

    else:
        # ── Flux Depth ControlNet ──────────────────────────────────
        # Scene description prompt
        wf[NODE_DEPTH["positive_prompt"]]["inputs"]["text"] = prompt

        # Unique prefix
        wf[NODE_DEPTH["save_image"]]["inputs"]["filename_prefix"] = prefix

        # Generation steps
        wf[NODE_DEPTH["scheduler"]]["inputs"]["steps"] = steps

        # Random seed
        wf[NODE_DEPTH["seed"]]["inputs"]["noise_seed"] = int(uuid.uuid4().int % (2**32))

        # Canvas size (must be divisible by 16 for Flux ControlNet)
        wf[NODE_DEPTH["latent"]]["inputs"]["width"]  = width
        wf[NODE_DEPTH["latent"]]["inputs"]["height"] = height

        # The uploaded C4D render (depth will be extracted from this)
        wf[NODE_DEPTH["load_image"]]["inputs"]["image"] = uploaded_image

        # Depth guidance strength
        wf[NODE_DEPTH["controlnet"]]["inputs"]["strength"] = strength

    return wf


def submit_job(workflow: dict) -> str:
    """Posts the workflow to ComfyUI and returns the prompt_id."""
    resp = requests.post(
        f"{COMFYUI_URL}/prompt",
        json={"prompt": workflow},
        timeout=30,
    )
    if not resp.ok:
        log.error(f"ComfyUI rejected the workflow (HTTP {resp.status_code}):")
        log.error(resp.text[:1000])
        sys.exit(1)
    return resp.json()["prompt_id"]


def wait_for_job(prompt_id: str) -> bool:
    """Polls ComfyUI until the job completes. Returns True on success."""
    log.info(f"  Waiting for ComfyUI job {prompt_id[:8]}...")
    elapsed = 0
    while elapsed < MAX_WAIT:
        try:
            resp = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
            resp.raise_for_status()
            history = resp.json()
            if prompt_id in history:
                job = history[prompt_id]
                status = job.get("status", {})
                if status.get("status_str") == "success":
                    return True
                if status.get("status_str") == "error":
                    log.error(f"  ComfyUI job failed: {status.get('messages', [])}")
                    return False
        except Exception:
            pass

        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

        if elapsed % 30 == 0:
            log.info(f"  Still generating... ({elapsed}s elapsed)")

    log.error(f"  Timed out after {MAX_WAIT}s")
    return False


def find_output_image(prefix: str) -> Path | None:
    """
    Searches ComfyUI's output folder for the generated PNG.
    SaveImage saves as: {prefix}_00001_.png
    """
    matches = list(COMFYUI_OUTPUT_DIR.glob(f"{prefix}_*.png"))
    if not matches:
        return None
    return sorted(matches, key=lambda p: p.stat().st_mtime)[-1]


def run(product_id: str, ratio: str, source_path: str, workflow: str = "turbo",
        strength: float = 1.0, steps: int = STEPS, force: bool = False):

    log.section(f"STEP 2a — CONTROLNET BACKGROUND ({workflow.upper()}) ({product_id} {ratio})")

    # ── Check ratio is supported ──────────────────────────────────
    if ratio not in CONTROLNET_DIMENSIONS:
        log.error(f"Unsupported ratio: {ratio}. Supported: {list(CONTROLNET_DIMENSIONS.keys())}")
        sys.exit(1)

    width, height = CONTROLNET_DIMENSIONS[ratio]

    # ── Check the C4D source render exists ─────────────────────────
    source = Path(source_path)
    if not source.exists():
        log.error(f"C4D source render not found: {source}")
        sys.exit(1)
    log.info(f"  C4D source: {source.name}")
    log.info(f"  Workflow: {workflow}")
    if workflow == "depth":
        log.info(f"  Output size: {width}×{height}px (divisible-by-16 for Flux ControlNet)")
    else:
        log.info(f"  Output size: auto-matched to input image (via GetImageSize node)")
    log.info(f"  ControlNet strength: {strength}")

    # ── Check output doesn't already exist ─────────────────────────
    output_png = BACKGROUNDS_DIR / f"{product_id}_{ratio}.png"
    if output_png.exists():
        if force:
            log.warn(f"  --force set: overwriting {output_png.name}")
            output_png.unlink()
        else:
            log.ok(f"Background already exists — skipping: {output_png.name}")
            log.info("Use --force to overwrite.")
            return

    # ── Get the scene prompt from variants.json ─────────────────────
    prompt = ""
    if VARIANTS_JSON.exists():
        with open(VARIANTS_JSON, encoding="utf-8") as f:
            variants = json.load(f)
        match = next(
            (v for v in variants
             if v["product_id"] == product_id and v["ratio"] == ratio),
            None
        )
        if match:
            prompt = match.get("comfyui_prompt", "")

    if not prompt:
        prompt = "cinematic background scene, atmospheric lighting, depth of field, no people"
        log.warn(f"  No comfyui_prompt found for {product_id}/{ratio} — using fallback")
    else:
        log.info(f"  Prompt: {prompt[:80]}...")

    # ── Check ComfyUI is running ────────────────────────────────────
    try:
        requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
    except requests.ConnectionError:
        log.error(f"Cannot reach ComfyUI at {COMFYUI_URL}")
        log.error("Make sure ComfyUI is running first.")
        sys.exit(1)

    # ── Upload the C4D render to ComfyUI ───────────────────────────
    uploaded_name = upload_image(source)

    # ── Build and submit the workflow ───────────────────────────────
    base_workflow = load_workflow(workflow)
    prefix = f"yosuki_controlnet_{workflow}_{product_id}_{ratio}"

    wf = build_workflow(
        base_workflow, workflow, uploaded_name, prompt,
        width, height, prefix, strength, steps
    )

    model_label = "Z-Image-Turbo Canny" if workflow == "turbo" else "Flux Depth ControlNet"
    log.info(f"  Submitting {model_label} job...")
    prompt_id = submit_job(wf)

    # ── Wait for completion ─────────────────────────────────────────
    success = wait_for_job(prompt_id)
    if not success:
        log.error("Job failed — check ComfyUI for details.")
        sys.exit(1)

    # ── Find the output PNG ─────────────────────────────────────────
    log.info("  Job complete. Looking for output PNG...")
    time.sleep(1)
    image_path = find_output_image(prefix)

    if not image_path:
        log.error(f"Could not find output PNG with prefix '{prefix}' in {COMFYUI_OUTPUT_DIR}")
        sys.exit(1)

    # ── Copy to backgrounds folder ─────────────────────────────────
    BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(image_path, output_png)
    size_kb = output_png.stat().st_size // 1024
    log.ok(f"  Saved: {output_png.name} ({size_kb} KB)")

    log.ok(f"Done! Background ready at: output/backgrounds/{output_png.name}")
    log.info("Next step: animate it into a video:")
    log.info(f"  python scripts/02b_generate_bg_videos.py --product {product_id} --ratio {ratio} --force")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate a Flux + ControlNet depth background from a C4D render."
    )
    parser.add_argument(
        "--product", type=str, default="sax_signature",
        help="Product ID (e.g. sax_signature)"
    )
    parser.add_argument(
        "--ratio", type=str, default="16x9",
        help="Aspect ratio (16x9, 1x1, billboard_970x250)"
    )
    parser.add_argument(
        "--source", type=str, required=True,
        help="Path to the Cinema 4D render to use as ControlNet reference"
    )
    parser.add_argument(
        "--workflow", type=str, default="flux_canny", choices=["turbo", "depth", "flux_canny"],
        help="Which ControlNet workflow to use. 'turbo' = Z-Image-Turbo Canny (default, fast). 'depth' = Flux depth ControlNet."
    )
    parser.add_argument(
        "--strength", type=float, default=1.0,
        help="ControlNet depth strength (0.5=loose, 0.65=balanced, 0.85=tight). Default: 0.65"
    )
    parser.add_argument(
        "--steps", type=int, default=STEPS,
        help=f"Generation steps. Default: {STEPS}"
    )
    parser.add_argument(
        "--force", action="store_true", default=False,
        help="Overwrite the output PNG if it already exists."
    )
    args = parser.parse_args()
    run(
        product_id=args.product,
        ratio=args.ratio,
        source_path=args.source,
        workflow=args.workflow,
        strength=args.strength,
        steps=args.steps,
        force=args.force,
    )
