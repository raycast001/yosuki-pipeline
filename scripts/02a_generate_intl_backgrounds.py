"""
02a_generate_intl_backgrounds.py
==============================
Generates 9 background images for international markets using Flux Canny + ControlNet.

  3 scenes (sax, piano, guitar) x 3 markets (JP, DE, BR) = 9 images at 16x9.

Each image uses:
  - The same C4D greyscale render as the US version (ControlNet input — same composition)
  - The scene's comfyui_prompt from variants.json (base scene description)
  - The market's visual_culture from brief.json (cultural nuance appended to prompt)

Outputs (saved to output/backgrounds/):
  sax_JP_16x9.png      piano_JP_16x9.png      guitar_JP_16x9.png
  sax_DE_16x9.png      piano_DE_16x9.png      guitar_DE_16x9.png
  sax_BR_16x9.png      piano_BR_16x9.png      guitar_BR_16x9.png

These are referenced in 03_populate_templates.py by scene family + market.

RUN:
  python scripts/02a_generate_intl_backgrounds.py
  python scripts/02a_generate_intl_backgrounds.py --market JP
  python scripts/02a_generate_intl_backgrounds.py --force   (regenerate even if exists)
"""

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
    BRIEF_JSON,
    C4D_RENDERS,
    COMFYUI_OUTPUT_DIR,
    COMFYUI_URL,
    COMFYUI_WORKFLOWS_DIR,
    VARIANTS_JSON,
)
from scripts.utils.logger import log

STEPS         = 20
POLL_INTERVAL = 3
MAX_WAIT      = 900

# ── Product → scene mapping ───────────────────────────────────────────────────
def get_scene(product_id: str) -> str:
    if product_id.startswith("sax"):   return "sax"
    if product_id.startswith("piano"): return "piano"
    return "guitar"

# ── Representative product_id per scene (for prompt lookup) ──────────────────
SCENE_REPR_PRODUCT = {
    "sax":    "sax_signature",
    "piano":  "piano_grand",
    "guitar": "guitar_paulie_black",
}

# ── Flux Canny node IDs (from flux_canny_model_example.json) ─────────────────
NODE = {
    "load_image":      "17",
    "canny":           "18",
    "positive_prompt": "23",
    "guidance":        "26",
    "save_image":      "9",
    "sampler":         "3",
}


def load_workflow() -> dict:
    path = COMFYUI_WORKFLOWS_DIR / "flux_canny_model_example.json"
    if not path.exists():
        log.error(f"Flux Canny workflow not found: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def upload_image(image_path: Path) -> str:
    """Uploads the C4D render to ComfyUI's input folder. Returns the filename."""
    log.info(f"  Uploading C4D render: {image_path.name}")
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


def inject_workflow(base: dict, uploaded_image: str, prompt: str, prefix: str) -> dict:
    wf = copy.deepcopy(base)
    wf[NODE["load_image"]]["inputs"]["image"]      = uploaded_image
    wf[NODE["save_image"]]["inputs"]["filename_prefix"] = prefix
    wf[NODE["sampler"]]["inputs"]["seed"]          = int(uuid.uuid4().int % (2**32))
    wf[NODE["sampler"]]["inputs"]["steps"]         = STEPS
    wf[NODE["positive_prompt"]]["inputs"]["text"]  = prompt
    wf[NODE["canny"]]["inputs"]["low_threshold"]   = 0.05
    wf[NODE["canny"]]["inputs"]["high_threshold"]  = 0.1
    return wf


def submit_job(workflow: dict) -> str:
    resp = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow}, timeout=30)
    if not resp.ok:
        log.error(f"ComfyUI rejected workflow (HTTP {resp.status_code}): {resp.text[:500]}")
        sys.exit(1)
    return resp.json()["prompt_id"]


def wait_for_job(prompt_id: str) -> bool:
    log.info(f"  Waiting for job {prompt_id[:8]}...")
    elapsed = 0
    while elapsed < MAX_WAIT:
        try:
            resp = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
            resp.raise_for_status()
            history = resp.json()
            if prompt_id in history:
                status = history[prompt_id].get("status", {})
                if status.get("status_str") == "success":
                    return True
                if status.get("status_str") == "error":
                    log.error(f"  Job failed: {status.get('messages', [])}")
                    return False
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        if elapsed % 30 == 0:
            log.info(f"  Still generating... ({elapsed}s)")
    log.error(f"  Timed out after {MAX_WAIT}s")
    return False


def find_output(prefix: str) -> Path | None:
    matches = list(COMFYUI_OUTPUT_DIR.glob(f"{prefix}_*.png"))
    if not matches:
        return None
    return sorted(matches, key=lambda p: p.stat().st_mtime)[-1]


def run(market_filter: str | None = None, force: bool = False):
    log.section("INTERNATIONAL BACKGROUNDS — 9 images (3 scenes x JP/DE/BR)")

    # ── Check ComfyUI ─────────────────────────────────────────────
    try:
        requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
    except requests.ConnectionError:
        log.error(f"ComfyUI not running at {COMFYUI_URL}")
        sys.exit(1)

    # ── Load brief for market visual_culture ───────────────────────
    with open(BRIEF_JSON, encoding="utf-8") as f:
        brief = json.load(f)
    intl_markets = [m for m in brief["markets"] if m["id"] != "US"]
    if market_filter:
        intl_markets = [m for m in intl_markets if m["id"] == market_filter]

    # ── Load scene prompts from US variants ────────────────────────
    with open(VARIANTS_JSON, encoding="utf-8") as f:
        variants = json.load(f)
    scene_prompts = {}
    for scene, rep_pid in SCENE_REPR_PRODUCT.items():
        match = next(
            (v for v in variants
             if v["product_id"] == rep_pid and v.get("market") == "US" and v.get("comfyui_prompt")),
            None
        )
        if match:
            scene_prompts[scene] = match["comfyui_prompt"]
        else:
            scene_prompts[scene] = "cinematic atmospheric scene, dramatic lighting, no people"
            log.warn(f"  No comfyui_prompt found for {scene} — using fallback")

    BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)
    workflow_template = load_workflow()

    scenes = list(C4D_RENDERS.keys())
    total  = len(scenes) * len(intl_markets)
    count  = 0

    for mkt in intl_markets:
        mid     = mkt["id"]
        culture = mkt.get("visual_culture", "")

        for scene in scenes:
            count += 1
            output_path = BACKGROUNDS_DIR / f"{scene}_{mid}_16x9.png"
            log.progress(count, total, f"{scene} / {mid}")

            if output_path.exists() and not force:
                log.info(f"  Already exists — skipping: {output_path.name}")
                continue

            c4d_source = C4D_RENDERS[scene]
            if not c4d_source.exists():
                log.error(f"  C4D render not found: {c4d_source}")
                continue

            # Combine scene description with market cultural nuance
            base_prompt = scene_prompts[scene]
            prompt = f"{base_prompt}, {culture}" if culture else base_prompt
            log.info(f"  Prompt: {prompt[:100]}...")

            # Upload C4D render as ControlNet input
            uploaded = upload_image(c4d_source)

            # Build and submit Flux Canny job
            prefix   = f"yosuki_intl_{scene}_{mid}_16x9"
            workflow = inject_workflow(workflow_template, uploaded, prompt, prefix)
            prompt_id = submit_job(workflow)

            # Wait for completion
            if not wait_for_job(prompt_id):
                log.error(f"  Failed: {scene}_{mid}")
                continue

            # Find and save the output
            time.sleep(1)
            source_file = find_output(prefix)
            if not source_file:
                log.error(f"  Output PNG not found for prefix '{prefix}'")
                continue

            shutil.copy2(source_file, output_path)
            size_kb = output_path.stat().st_size // 1024
            log.ok(f"  Saved: {output_path.name} ({size_kb} KB)")

    print()
    log.ok("Done. Check output/backgrounds/ for the 9 international backgrounds.")
    log.info("Review images, then re-render with: python scripts/03_populate_templates.py --market JP")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", type=str, default=None,
                        help="Generate for one market only (e.g. --market JP)")
    parser.add_argument("--force", action="store_true", default=False,
                        help="Overwrite existing images")
    args = parser.parse_args()
    run(market_filter=args.market, force=args.force)
