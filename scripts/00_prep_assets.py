"""
00_prep_assets.py — Remove white/gray backgrounds from product PNGs
=====================================================================
PURPOSE:
  After Effects compositing requires products to have a TRANSPARENT background
  so they can "float" over the AI-generated scene. The provided Yosuki PNGs
  have solid white or gray backgrounds — this script removes them automatically.

HOW IT WORKS:
  We use a library called `rembg` which runs a small AI model (U2Net) locally
  on your machine. It looks at the image, figures out where the product ends
  and the background begins, and cuts it out — like Photoshop's "Remove Background"
  but fully automated.

OUTPUT:
  Saves transparent PNG cutouts to: assets/product_cutouts/
  Example: saxophone/sax1.png → assets/product_cutouts/sax1_cutout.png

NOTE:
  The first time you run this, rembg will download its AI model (~170 MB).
  After that it runs instantly from cache. This is normal.

RUN:
  python scripts/00_prep_assets.py
"""

import sys
from pathlib import Path

# Add the project root to Python's path so our imports work
sys.path.insert(0, str(Path(__file__).parent.parent))
import os
os.environ["PYTHONIOENCODING"] = "utf-8"


from PIL import Image
from rembg import remove
from tqdm import tqdm

from config import ASSET_BUNDLE_DIR, PRODUCT_CUTOUTS_DIR
from scripts.utils.logger import log


# ─────────────────────────────────────────────
# MAPPING: source PNG → output cutout filename
# ─────────────────────────────────────────────

# Each entry is: (source path relative to ASSET_BUNDLE_DIR, output filename)
# We name outputs clearly so brief.json product_image paths are easy to read.
ASSET_MAP = [
    # Saxophone
    ("saxophone/sax1.png",    "sax1_cutout.png"),

    # Pianos
    ("pianos/piano1.png",     "piano1_cutout.png"),
    ("pianos/piano2.png",     "piano2_cutout.png"),
    ("pianos/piano3.png",     "piano3_cutout.png"),

    # Guitars — Paulie (guitar1)
    ("guitars/guitar1-a.png", "guitar1a_cutout.png"),  # Paulie Black
    ("guitars/guitar1-b.png", "guitar1b_cutout.png"),  # Paulie Blue-burst

    # Guitars — San Jose SJ (guitar2)
    ("guitars/guitar2-a.png", "guitar2a_cutout.png"),  # San Jose Black
    ("guitars/guitar2-b.png", "guitar2b_cutout.png"),  # San Jose Blue-burst

    # Guitars — Stratoblaster (guitar3)
    ("guitars/guitar3-a.png", "guitar3a_cutout.png"),  # Stratoblaster Black
    ("guitars/guitar3-b.png", "guitar3b_cutout.png"),  # Stratoblaster Blue-burst

    # Logo (for After Effects templates)
    ("logo.png",              "logo_cutout.png"),
]


def run():
    log.section("STEP 0 — ASSET PREP (Background Removal)")

    # Create output folder if it doesn't exist yet
    PRODUCT_CUTOUTS_DIR.mkdir(parents=True, exist_ok=True)

    # Count how many files we actually need to process
    to_process = []
    for source_rel, output_name in ASSET_MAP:
        source_path = ASSET_BUNDLE_DIR / source_rel
        output_path = PRODUCT_CUTOUTS_DIR / output_name

        if not source_path.exists():
            log.warn(f"Source file not found — skipping: {source_path}")
            continue

        if output_path.exists():
            log.info(f"Already exists — skipping: {output_name}")
            continue

        to_process.append((source_path, output_path, output_name))

    if not to_process:
        log.ok("All cutouts already exist. Nothing to do.")
        return

    log.info(f"Processing {len(to_process)} image(s) with rembg...")
    log.info("(First run may take a moment to load the AI model)")
    print()

    success_count = 0
    fail_count = 0

    # tqdm gives us a progress bar in the terminal
    for source_path, output_path, output_name in tqdm(to_process, desc="Removing backgrounds"):
        try:
            # ── Open the source image ────────────────────────────
            input_image = Image.open(source_path)

            # ── Run rembg to remove the background ──────────────
            # `remove()` returns a PIL Image with a transparent alpha channel.
            # No configuration needed — rembg handles it automatically.
            output_image = remove(input_image)

            # ── Save as PNG (PNG supports transparency, JPEG does not) ──
            output_image.save(output_path, format="PNG")

            log.ok(f"Saved: {output_name}")
            success_count += 1

        except Exception as e:
            # We don't want one failed image to stop the whole batch
            log.error(f"Failed: {output_name} — {e}")
            fail_count += 1

    # ── Summary ──────────────────────────────────────────────────
    print()
    log.ok(f"Done. {success_count} cutout(s) saved to: {PRODUCT_CUTOUTS_DIR}")
    if fail_count:
        log.warn(f"{fail_count} image(s) failed. Check errors above.")

    log.info("Next step: python scripts/01_generate_copy.py")


if __name__ == "__main__":
    run()
