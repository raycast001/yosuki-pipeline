"""
03_populate_templates.py — Populate AND render After Effects templates in one step
==================================================================================
PURPOSE:
  For each variant in variants.json, this script:
  1. Copies the appropriate AE template (.aep) to output/projects/
  2. Writes a {variant_id}_data.json alongside it (the data ExtendScript will read)
  3. Runs aerender.exe with BOTH the -s flag (JSX) AND render flags in one call:
       - JSX runs FIRST: sets text + relinks footage IN MEMORY
       - aerender renders IMMEDIATELY from that in-memory state
       - No save/reload cycle — footage stays relinked

WHY COMBINED? (The key insight):
  If we separate populate and render into two aerender calls:
    1. JSX modifies footage and saves the .aep
    2. Second aerender opens the saved .aep — but AE re-resolves footage
       from the original template paths when loading, losing our changes
  By combining both into ONE call, the JSX modifies in memory and aerender
  renders before AE ever touches the file system again. This is the fix.

OUTPUT:
  Renders go directly to output/renders/{variant_id}.mp4
  Variants are marked "rendered" (not just "populated") on success.

CRASH SAFETY:
  Variants with status "rendered" or "delivered" are skipped.

RUN:
  python scripts/03_populate_templates.py
  python scripts/03_populate_templates.py --variant sax_signature_US_16x9
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))
import os
os.environ["PYTHONIOENCODING"] = "utf-8"


from config import (
    AE_MAIN_COMP_NAME,
    AE_OUTPUT_MODULE,
    AE_TEMPLATES_DIR,
    AERENDER_PATH,
    BACKGROUNDS_DIR,
    PROJECTS_DIR,
    RENDERS_DIR,
    VARIANTS_JSON,
)
from scripts.utils.logger import log


# ─────────────────────────────────────────────
# TEMPLATE FILENAME PER RATIO
# ─────────────────────────────────────────────
TEMPLATE_MAP = {
    "billboard_970x250": "billboard_970x250.aep",
    "16x9":              "landscape_16.9.aep",
    "1x1":               "square_1x1.aep",
}


def sample_bg_color(bg_png: Path) -> list:
    """
    Samples the average color from the background PNG.
    This is passed to ExtendScript so it can apply a matching tint
    to the product layer, blending it into the scene.
    Returns [r, g, b] as integers 0-255.
    Falls back to a warm amber if the file can't be read.
    """
    try:
        img = Image.open(bg_png).convert("RGB")
        img = img.resize((100, 100))  # downsample for speed
        pixels = list(img.getdata())
        r = int(sum(p[0] for p in pixels) / len(pixels))
        g = int(sum(p[1] for p in pixels) / len(pixels))
        b = int(sum(p[2] for p in pixels) / len(pixels))
        return [r, g, b]
    except Exception:
        return [180, 120, 60]  # warm amber fallback


def write_data_json(variant: dict, data_json_path: Path):
    """
    Writes the data file that ExtendScript reads.
    Contains all the text and file paths needed to populate the AE project.

    We write absolute paths so ExtendScript can find the files regardless of
    where After Effects' working directory is.
    """
    # Always use the 16x9 background — one Flux Canny run covers all ratios.
    # AE scales/crops it to fit each comp (billboard, 1x1, 16x9).
    #
    # Background priority:
    #   1. Market-specific background: {product_id}_{market_id}_16x9.png (JP/DE/BR)
    #   2. US base background:         {product_id}_16x9.png (fallback for all markets)
    #
    # This lets international markets have their own culturally-adapted Flux image
    # while gracefully falling back to the US image if the intl one hasn't been
    # generated yet.
    market = variant.get("market", "US")
    pid    = variant["product_id"]

    if market != "US":
        # International markets use one background per scene per market.
        # Scene is determined by product family: sax / piano / guitar
        # Saved as: {scene}_{market_id}_16x9.png  e.g. sax_JP_16x9.png
        if pid.startswith("sax"):   scene = "sax"
        elif pid.startswith("piano"): scene = "piano"
        else:                          scene = "guitar"

        background_png = BACKGROUNDS_DIR / f"{scene}_{market}_16x9.png"
        background_mp4 = BACKGROUNDS_DIR / f"{scene}_{market}_16x9.mp4"
        # Fall back to US product background if the market-specific one doesn't exist yet
        if not background_png.exists() and not background_mp4.exists():
            background_png = BACKGROUNDS_DIR / f"{pid}_16x9.png"
            background_mp4 = BACKGROUNDS_DIR / f"{pid}_16x9.mp4"
    else:
        background_png = BACKGROUNDS_DIR / f"{pid}_16x9.png"
        background_mp4 = BACKGROUNDS_DIR / f"{pid}_16x9.mp4"

    # Prefer the .mp4 if it exists (animated), otherwise use the static .png
    background_path = background_mp4 if background_mp4.exists() else background_png

    data = {
        # Text layers — these get set on the AE text layers
        "tagline":      variant.get("tagline", ""),
        "series_title": variant.get("series_title", ""),
        "cta":          variant.get("cta", ""),

        # Footage paths — these get relinked in the AE project
        # We use as_posix() to convert Windows backslashes to forward slashes
        # (ExtendScript handles forward slashes fine on Windows)
        "bg_image_path":      background_path.as_posix(),
        "product_image_path": str(Path(variant["product_image"]).resolve()).replace("\\", "/"),

        # Tinting disabled — product renders with natural colours.
        "bg_tint_color":  None,
        "bg_tint_amount": 0,

        # Product scale override:
        #   Guitars (billboard): sanjose gets explicit 16%; others auto-contain (None)
        #   Guitars (16x9/1x1): per-model manual values tuned to the PRODUCT_CONSTRAIN box
        #   Everything else (sax, piano): None → use AE template default
        "product_scale": (
            {
                "guitar_sanjose_black":     16,
                "guitar_sanjose_blueburst": 16,
            }.get(variant.get("product_id", ""), None)
            if variant.get("ratio") == "billboard_970x250"
            else {
                "guitar_paulie_black":            29,
                "guitar_paulie_blueburst":        29,
                "guitar_sanjose_black":           41,
                "guitar_sanjose_blueburst":       41,
                "guitar_stratoblaster_black":     39,
                "guitar_stratoblaster_blueburst": 39,
            }.get(variant.get("product_id", ""), None)
        ),

        # Relative scale multiplier applied ON TOP of the AE template's current scale.
        # 1.1 = 10% bigger than whatever the layer is already set to in the template.
        # Only used when product_scale is None (pianos and sax).
        "product_scale_multiplier": 1.1 if variant.get("product_id", "").startswith("piano_") else None,

        # Product position override — only used when use_product_constrain is False.
        "product_position": None,

        # Y offset (pixels) applied on top of the constrain box center position.
        # Negative = up, positive = down. Only applies when use_product_constrain is True.
        # Sanjose needs +up nudge for 16x9/1x1 only — billboard uses auto-contain so no offset.
        "constrain_y_offset": 0 if variant.get("ratio") == "billboard_970x250" else {
            "guitar_sanjose_black":     -40,
            "guitar_sanjose_blueburst": -40,
        }.get(variant.get("product_id", ""), 0),

        # Constrain mode — when True, the JSX fits PRODUCT_IMAGE_PLACEHOLDER inside
        # the PRODUCT_CONSTRAIN solid in the AE template (contain scaling + position snap).
        # Guitars use this so the product always respects the red constraint box.
        "use_product_constrain": variant.get("product_id", "").startswith("guitar_"),

        # Metadata (useful for debugging inside AE)
        "variant_id":  variant["variant_id"],
        "market":      variant["market"],
        "ratio":       variant["ratio"],
        "comp_name":   AE_MAIN_COMP_NAME,
    }

    with open(data_json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def populate_and_render(project_path: Path, render_output_path: Path) -> bool:
    """
    Runs aerender.exe to render the project.

    The populate (text + footage relinking) is handled automatically by
    zz_yosuki_populate.jsx, which lives in AE's Scripts/Startup/ folder.
    That script wraps AddCompToRenderQueue so it fires after the project
    opens — it reads the {variant_id}_data.json file we wrote next to the .aep
    and swaps in the correct text and footage before the render begins.

    Returns True if render succeeded and output file exists, False otherwise.
    """
    if not Path(AERENDER_PATH).exists():
        log.error(f"aerender.exe not found at: {AERENDER_PATH}")
        log.error("Check AERENDER_PATH in config.py")
        return False

    # The aerender command:
    # -project:    the copied .aep template to open
    # -comp:       which composition to render
    # -output:     where to save the MP4
    # -OMtemplate: the After Effects Output Module Template (encoding settings)
    # -v ERRORS:   only show error messages in terminal
    #
    # NOTE: There is NO script execution flag in aerender.
    # The JSX runs via a Startup hook (zz_yosuki_populate.jsx in AE's Scripts/Startup/ folder).
    # It wraps AddCompToRenderQueue so it fires after the project opens, before rendering.
    cmd = [
        AERENDER_PATH,
        "-project",    str(project_path),
        "-comp",       AE_MAIN_COMP_NAME,
        "-output",     str(render_output_path),
        "-OMtemplate", AE_OUTPUT_MODULE,
        "-v",          "ERRORS",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout — rendering takes longer than just scripting
        )

        if result.returncode != 0:
            log.error(f"aerender returned error code {result.returncode}")
            if result.stderr:
                log.error(f"stderr: {result.stderr[-500:]}")
            return False

        # Verify the output file exists and has content
        if not render_output_path.exists() or render_output_path.stat().st_size == 0:
            log.error(f"Output file missing or empty: {render_output_path.name}")
            return False

        size_mb = render_output_path.stat().st_size / (1024 * 1024)
        log.ok(f"  Rendered: {render_output_path.name} ({size_mb:.1f} MB)")
        return True

    except subprocess.TimeoutExpired:
        log.error("aerender timed out (>10 min) — render may be stuck")
        return False
    except Exception as e:
        log.error(f"Failed to run aerender: {e}")
        return False


def run(variant_filter: str | None = None, market_filter: str | None = None):
    log.section("STEP 3 — POPULATE + RENDER (combined aerender call)")

    # ── Load variants.json ─────────────────────────────────────────
    if not VARIANTS_JSON.exists():
        log.error("variants.json not found. Run 01_generate_copy.py first.")
        sys.exit(1)

    with open(VARIANTS_JSON, encoding="utf-8") as f:
        all_variants = json.load(f)

    # Work on a filtered subset for processing, but always save all_variants back to disk
    if variant_filter:
        variants = [v for v in all_variants if v["variant_id"] == variant_filter]
        if not variants:
            log.error(f"Variant '{variant_filter}' not found in variants.json")
            sys.exit(1)
    elif market_filter:
        variants = [v for v in all_variants if v.get("market") == market_filter]
        if not variants:
            log.error(f"No variants found for market '{market_filter}'")
            sys.exit(1)
        # Reset status so they re-render even if previously marked rendered
        for v in variants:
            if v.get("status") == "rendered":
                v["status"] = "copy_generated"
    else:
        variants = all_variants

    # ── Check AE templates exist ───────────────────────────────────
    for ratio, template_name in TEMPLATE_MAP.items():
        template_path = AE_TEMPLATES_DIR / template_name
        if not template_path.exists():
            log.warn(f"Template not found: {template_path}")
            log.warn("Build your AE templates first (see ae_templates/ README).")

    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    RENDERS_DIR.mkdir(parents=True, exist_ok=True)  # renders go here directly now

    success = 0
    skipped = 0
    failed  = 0

    total = len([v for v in variants if v.get("status") not in ("rendered", "delivered")])
    count = 0

    for v in variants:
        vid = v["variant_id"]

        # Skip already-rendered variants (rendered = populated + rendered in one step now)
        if v.get("status") in ("rendered", "delivered"):
            skipped += 1
            continue

        # Skip variants without copy
        if v.get("status") == "pending":
            log.warn(f"Skipping {vid} — copy not yet generated")
            continue

        # Check background exists — prefer market-specific, fall back to US base
        market = v.get("market", "US")
        pid    = v["product_id"]
        if market != "US":
            if pid.startswith("sax"):    scene = "sax"
            elif pid.startswith("piano"): scene = "piano"
            else:                          scene = "guitar"
            bg_path = BACKGROUNDS_DIR / f"{scene}_{market}_16x9.png"
            if not bg_path.exists():
                bg_path = BACKGROUNDS_DIR / f"{pid}_16x9.png"  # US fallback
        else:
            bg_path = BACKGROUNDS_DIR / f"{pid}_16x9.png"

        if not bg_path.exists():
            log.warn(f"Skipping {vid} — background not found: {bg_path.name}")
            failed += 1
            continue

        count += 1
        log.progress(count, total, vid)

        # Find the right template for this ratio
        template_name = TEMPLATE_MAP.get(v["ratio"])
        if not template_name:
            log.error(f"No template defined for ratio '{v['ratio']}'")
            failed += 1
            continue

        template_path = AE_TEMPLATES_DIR / template_name
        if not template_path.exists():
            log.warn(f"Template file not found: {template_path} — skipping {vid}")
            failed += 1
            continue

        # ── Copy template to output/projects ────────────────────────
        project_path   = PROJECTS_DIR / f"{vid}.aep"
        data_json_path = PROJECTS_DIR / f"{vid}_data.json"
        render_path    = RENDERS_DIR  / f"{vid}.mp4"

        shutil.copy2(template_path, project_path)

        # ── Write data JSON for ExtendScript ────────────────────────
        write_data_json(v, data_json_path)

        # ── Populate in memory + render in one aerender call ─────────
        # This is the key fix: JSX modifies footage IN MEMORY, then aerender
        # renders immediately — no save/reload, so relinked footage stays put.
        log.info(f"  Populating + rendering {vid}...")
        success_flag = populate_and_render(project_path, render_path)

        if success_flag:
            # Jump straight to "rendered" — no separate render step needed
            v["status"] = "rendered"
            success += 1
            # Save immediately after each success so crash recovery works.
            # If aerender dies mid-batch, all previously-rendered variants
            # keep their "rendered" status and won't be re-rendered on restart.
            with open(VARIANTS_JSON, "w", encoding="utf-8") as f:
                json.dump(all_variants, f, ensure_ascii=False, indent=2)
        else:
            log.error(f"  Failed: {vid}")
            failed += 1

    # ── Final save (catches failed/skipped counts, no-op if already saved) ───
    with open(VARIANTS_JSON, "w", encoding="utf-8") as f:
        json.dump(all_variants, f, ensure_ascii=False, indent=2)

    print()
    log.ok(f"Done. {success} rendered, {skipped} skipped, {failed} failed.")
    log.info("Next step: python scripts/05_deliver.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Populate AE templates with variant data.")
    parser.add_argument(
        "--variant",
        type=str,
        default=None,
        help="Process a single variant_id only (e.g. --variant sax_signature_US_16x9)"
    )
    parser.add_argument(
        "--market",
        type=str,
        default=None,
        help="Process all variants for one market only (e.g. --market JP)"
    )
    args = parser.parse_args()
    run(variant_filter=args.variant, market_filter=args.market)
