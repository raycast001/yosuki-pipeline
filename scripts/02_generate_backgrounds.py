"""
02_generate_backgrounds.py — Generate scene backgrounds using ComfyUI + FLUX
=============================================================================
PURPOSE:
  Generates AI background images for all markets:

  US (base):
    One background per unique product+ratio combo (27 total).
    Saved as: output/backgrounds/{product_id}_{ratio}.png

  International (JP, DE, BR):
    One background per market+product+ratio combo.
    Same Flux Canny workflow, but the prompt has cultural visual nuances
    appended from brief.json so each market gets a culturally-adapted scene.
    Saved as: output/backgrounds/{product_id}_{market_id}_{ratio}.png
    C4D does NOT re-run for international — the same structural composition
    is reused, only the visual style shifts via the prompt.

HOW IT WORKS:
  1. Reads variants.json (created by 01_generate_copy.py)
  2. For US: collects unique product+ratio combos, generates base backgrounds
  3. For international: reads visual_culture from brief.json, appends it to the
     US comfyui_prompt, and generates market-specific backgrounds
  4. Waits for each job to complete, copies image from G:/ComfyUI/output/

MODEL: FLUX (flux1-dev.safetensors)
  FLUX is different from standard SDXL — it does NOT use a negative prompt.
  The workflow uses SamplerCustomAdvanced + BasicScheduler instead of KSampler.

NODE MAP (from background_workflow.json):
  "6"  — CLIPTextEncode    → positive prompt text
  "9"  — SaveImage         → output filename prefix (we set a unique one per job)
  "17" — BasicScheduler    → steps count
  "25" — RandomNoise       → seed value
  "27" — EmptySD3LatentImage → width, height, batch_size

CRASH SAFETY:
  If a background already exists in output/backgrounds/, it is skipped.
  Safe to re-run at any time.

RUN:
  python scripts/02_generate_backgrounds.py              # US backgrounds only
  python scripts/02_generate_backgrounds.py --intl       # US + international
  python scripts/02_generate_backgrounds.py --intl --market JP   # one market
  python scripts/02_generate_backgrounds.py --product sax_signature
"""

import argparse
import copy
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ["PYTHONIOENCODING"] = "utf-8"

import requests

from config import (
    BACKGROUNDS_DIR,
    BRIEF_JSON,
    COMFYUI_OUTPUT_DIR,
    COMFYUI_URL,
    COMFYUI_WORKFLOWS_DIR,
    RATIO_DIMENSIONS,
    VARIANTS_JSON,
)
from scripts.utils.logger import log

# ─────────────────────────────────────────────
# FLUX WORKFLOW NODE IDs
# These match background_workflow.json exactly. Don't change unless you
# restructure the workflow in ComfyUI.
# ─────────────────────────────────────────────
NODE = {
    "positive_prompt": "6",   # CLIPTextEncode — text field is the prompt
    "save_image":      "9",   # SaveImage — filename_prefix field
    "scheduler":       "17",  # BasicScheduler — steps field
    "seed":            "25",  # RandomNoise — noise_seed field
    "latent":          "27",  # EmptySD3LatentImage — width, height, batch_size
}

# ─────────────────────────────────────────────
# GENERATION SETTINGS
# ─────────────────────────────────────────────
STEPS        = 25     # Generation steps — 20-30 is a good range for FLUX
POLL_INTERVAL = 3     # Seconds between polling ComfyUI for job status
MAX_WAIT      = 300   # Maximum seconds to wait per image (5 minutes)


def load_workflow() -> dict:
    """Loads the FLUX workflow JSON from disk."""
    path = COMFYUI_WORKFLOWS_DIR / "background_workflow.json"
    if not path.exists():
        log.error(f"Workflow not found: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def make_job_prefix(product_id: str, ratio: str, market_id: str = "US") -> str:
    """
    Creates a unique, filesystem-safe filename prefix for this job.
    ComfyUI saves the output as: {prefix}_00001_.png
    We use this prefix to find the file in G:/ComfyUI/output/ after generation.

    Examples:
      US:  "yosuki_sax_signature_16x9"
      JP:  "yosuki_sax_signature_JP_16x9"
    """
    if market_id == "US":
        safe = f"yosuki_{product_id}_{ratio}".replace("/", "_")
    else:
        safe = f"yosuki_{product_id}_{market_id}_{ratio}".replace("/", "_")
    return safe


def inject_into_workflow(workflow: dict, prompt: str, width: int, height: int,
                         prefix: str) -> dict:
    """
    Returns a modified copy of the workflow with our values injected.

    What we change:
      - Node 6 (CLIPTextEncode): set the prompt text
      - Node 9 (SaveImage): set a unique filename prefix so we can find the output
      - Node 17 (BasicScheduler): set steps count
      - Node 25 (RandomNoise): set a random seed (different image each run)
      - Node 27 (EmptySD3LatentImage): set width and height

    Why we use copy.deepcopy:
      We generate many images in a loop. deepcopy makes sure each iteration
      gets its own fresh copy of the workflow dict — without it, changes from
      one iteration would leak into the next.
    """
    wf = copy.deepcopy(workflow)

    # Set the scene description prompt
    wf[NODE["positive_prompt"]]["inputs"]["text"] = prompt

    # Set a unique prefix so we can find THIS job's output file
    wf[NODE["save_image"]]["inputs"]["filename_prefix"] = prefix

    # Set generation steps
    wf[NODE["scheduler"]]["inputs"]["steps"] = STEPS

    # Set a random seed so every image is unique
    wf[NODE["seed"]]["inputs"]["noise_seed"] = int(uuid.uuid4().int % (2**32))

    # Set image dimensions
    wf[NODE["latent"]]["inputs"]["width"]      = width
    wf[NODE["latent"]]["inputs"]["height"]     = height
    wf[NODE["latent"]]["inputs"]["batch_size"] = 1

    return wf


def submit_job(workflow: dict) -> str:
    """
    Posts the workflow to ComfyUI and returns the prompt_id.
    ComfyUI queues jobs and processes them asynchronously.
    """
    try:
        resp = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow}, timeout=30)
        resp.raise_for_status()
        return resp.json()["prompt_id"]
    except requests.ConnectionError:
        log.error(f"Cannot reach ComfyUI at {COMFYUI_URL}")
        log.error("Start ComfyUI Desktop first, then re-run this script.")
        sys.exit(1)
    except Exception as e:
        log.error(f"Failed to submit job: {e}")
        sys.exit(1)


def wait_for_completion(prompt_id: str) -> bool:
    """
    Polls ComfyUI's /history endpoint until the job appears (= it's done).
    Returns True if completed, False if timed out.

    How this works:
      ComfyUI processes jobs in a queue. The /history endpoint only lists
      jobs that have FINISHED. So we keep polling until our prompt_id appears.
    """
    elapsed = 0
    print("  Generating", end="", flush=True)
    while elapsed < MAX_WAIT:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        print(".", end="", flush=True)

        try:
            resp = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
            resp.raise_for_status()
            history = resp.json()
            if prompt_id in history:
                print()  # newline after the dots
                return True
        except Exception:
            pass  # Keep trying until timeout

    print()
    log.error(f"Timed out after {MAX_WAIT}s waiting for job {prompt_id}")
    return False


def find_output_file(prefix: str) -> Path | None:
    """
    Looks in G:/ComfyUI/output/ for a file starting with our unique prefix.
    ComfyUI saves files as: {prefix}_00001_.png

    Why we look on disk instead of using the /view API:
      It's simpler and more reliable — we already know the prefix we set,
      so we just scan for it. No need to parse the history JSON structure.
    """
    if not COMFYUI_OUTPUT_DIR.exists():
        log.error(f"ComfyUI output folder not found: {COMFYUI_OUTPUT_DIR}")
        return None

    # Find any PNG starting with our prefix
    matches = list(COMFYUI_OUTPUT_DIR.glob(f"{prefix}_*.png"))
    if not matches:
        log.error(f"No output file found with prefix '{prefix}' in {COMFYUI_OUTPUT_DIR}")
        return None

    # Sort by modification time — take the newest in case of duplicates
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0]


def generate_backgrounds(combos_list: list, workflow_template: dict,
                          success_ref: list, skipped_ref: list, failed_ref: list):
    """
    Generates backgrounds for a list of combo dicts.
    Each combo must have: product_id, ratio, comfyui_prompt, output_name, market_id.
    Updates the success/skipped/failed reference lists in place.
    """
    for i, combo in enumerate(combos_list, 1):
        output_path = BACKGROUNDS_DIR / combo["output_name"]
        log.progress(i, len(combos_list),
                     f"{combo['product_id']} / {combo.get('market_id','US')} / {combo['ratio']}")

        # Skip if already exists (crash safety — safe to re-run)
        if output_path.exists():
            log.info(f"  Already exists — skipping: {combo['output_name']}")
            skipped_ref[0] += 1
            continue

        # Get pixel dimensions for this ratio
        width, height = RATIO_DIMENSIONS[combo["ratio"]]
        log.info(f"  Dimensions: {width}x{height}px")
        log.info(f"  Prompt: {combo['comfyui_prompt'][:80]}...")

        prefix = make_job_prefix(combo["product_id"], combo["ratio"],
                                  combo.get("market_id", "US"))

        workflow = inject_into_workflow(
            workflow_template,
            combo["comfyui_prompt"],
            width, height,
            prefix
        )

        prompt_id = submit_job(workflow)
        log.info(f"  Job submitted: {prompt_id[:8]}...")

        completed = wait_for_completion(prompt_id)
        if not completed:
            failed_ref[0] += 1
            continue

        source_file = find_output_file(prefix)
        if not source_file:
            failed_ref[0] += 1
            continue

        shutil.copy2(source_file, output_path)
        size_kb = output_path.stat().st_size // 1024
        log.ok(f"  Saved: {combo['output_name']} ({size_kb} KB)")
        success_ref[0] += 1


def run(product_filter: str | None = None,
        run_intl: bool = False,
        market_filter: str | None = None):
    log.section("STEP 2 — BACKGROUND GENERATION (ComfyUI + FLUX)")

    # ── Check ComfyUI is reachable ────────────────────────────────
    try:
        requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
    except requests.ConnectionError:
        log.error(f"ComfyUI is not running at {COMFYUI_URL}")
        log.error("Open ComfyUI Desktop and wait for it to finish loading, then re-run.")
        sys.exit(1)

    # ── Load variants.json ────────────────────────────────────────
    if not VARIANTS_JSON.exists():
        log.error("variants.json not found. Run 01_generate_copy.py first.")
        sys.exit(1)

    with open(VARIANTS_JSON, encoding="utf-8") as f:
        variants = json.load(f)

    # ── Load brief.json for cultural nuance data ──────────────────
    with open(BRIEF_JSON, encoding="utf-8") as f:
        brief = json.load(f)

    # Build a lookup: market_id → visual_culture string
    market_culture = {
        m["id"]: m.get("visual_culture", "")
        for m in brief["markets"]
        if m["id"] != "US"
    }

    BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)
    workflow_template = load_workflow()

    # Shared counters (using single-element lists so the helper can mutate them)
    success = [0]
    skipped = [0]
    failed  = [0]

    # ── PHASE 1 — US backgrounds (one per unique product+ratio) ───
    log.info("Generating US backgrounds...")
    us_combos = {}
    for v in variants:
        if v.get("market", "US") != "US":
            continue
        if product_filter and v["product_id"] != product_filter:
            continue
        if v["ratio"] != "16x9":
            continue   # backgrounds are only needed at 16x9 — AE scales them for other ratios
        if not v.get("comfyui_prompt"):
            log.warn(f"Skipping {v['variant_id']} — no comfyui_prompt (run step 01 first)")
            continue
        key = f"{v['product_id']}__{v['ratio']}"
        if key not in us_combos:
            us_combos[key] = {
                "product_id":     v["product_id"],
                "ratio":          v["ratio"],
                "market_id":      "US",
                "comfyui_prompt": v["comfyui_prompt"],
                # US backgrounds: {product_id}_{ratio}.png (no market suffix)
                "output_name":    f"{v['product_id']}_{v['ratio']}.png",
            }

    if us_combos:
        log.info(f"US backgrounds to generate: {len(us_combos)}")
        generate_backgrounds(list(us_combos.values()), workflow_template,
                             success, skipped, failed)
    else:
        log.warn("No US variants found in variants.json.")

    # ── PHASE 2 — International backgrounds (market-specific) ─────
    # Each market gets its own background per product+ratio, generated
    # from the same base prompt + cultural nuance suffix from brief.json.
    # C4D does NOT re-run — only the Flux Canny prompt changes.
    if run_intl:
        log.info("\nGenerating international backgrounds...")

        # Build base prompt lookup from US variants (same product scenes)
        us_prompts = {}
        for v in variants:
            if v.get("market", "US") == "US" and v.get("comfyui_prompt"):
                key = f"{v['product_id']}__{v['ratio']}"
                if key not in us_prompts:
                    us_prompts[key] = v["comfyui_prompt"]

        intl_combos = {}
        intl_markets = [m for m in brief["markets"] if m["id"] != "US"]
        if market_filter:
            intl_markets = [m for m in intl_markets if m["id"] == market_filter]

        for m in intl_markets:
            culture = market_culture.get(m["id"], "")
            for key, base_prompt in us_prompts.items():
                product_id, ratio = key.split("__")
                if product_filter and product_id != product_filter:
                    continue

                # Append cultural visual nuances to the base scene prompt
                culturally_adapted_prompt = (
                    f"{base_prompt}, {culture}" if culture else base_prompt
                )

                intl_key = f"{product_id}__{m['id']}__{ratio}"
                intl_combos[intl_key] = {
                    "product_id":     product_id,
                    "ratio":          ratio,
                    "market_id":      m["id"],
                    "comfyui_prompt": culturally_adapted_prompt,
                    # International: {product_id}_{market_id}_{ratio}.png
                    "output_name":    f"{product_id}_{m['id']}_{ratio}.png",
                }

        if intl_combos:
            log.info(f"International backgrounds to generate: {len(intl_combos)}")
            generate_backgrounds(list(intl_combos.values()), workflow_template,
                                 success, skipped, failed)
        else:
            log.warn("No international backgrounds to generate (check variants.json and brief.json).")

    # ── Summary ───────────────────────────────────────────────────
    print()
    log.ok(f"Done. {success[0]} generated, {skipped[0]} already existed, {failed[0]} failed.")
    if success[0] or skipped[0]:
        log.info(f"Backgrounds saved to: {BACKGROUNDS_DIR}")
        log.info("Next step: python scripts/03_populate_templates.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate ComfyUI backgrounds for all products.")
    parser.add_argument(
        "--product",
        type=str,
        default=None,
        help="Filter to a single product_id (e.g. --product sax_signature)"
    )
    parser.add_argument(
        "--intl",
        action="store_true",
        default=False,
        help="Also generate international (JP, DE, BR) market backgrounds"
    )
    parser.add_argument(
        "--market",
        type=str,
        default=None,
        help="Filter international to one market only (e.g. --market JP). Requires --intl."
    )
    args = parser.parse_args()
    run(product_filter=args.product, run_intl=args.intl, market_filter=args.market)
