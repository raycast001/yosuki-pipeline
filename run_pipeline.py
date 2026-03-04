"""
run_pipeline.py — Yosuki Pipeline Master Orchestrator
======================================================
CLI entry point for the full pipeline. For interactive control, use the dashboard instead:
  streamlit run dashboard.py

STEPS (in order):
  prep      Asset prep (rembg)         00_prep_assets.py               Removes white BG from product PNGs
                                                                        AUTO-SKIPS if all cutouts already exist
  bg-us     ComfyUI US backgrounds     02_generate_backgrounds.py      27 images (1 per product+ratio)
  bg-intl   ComfyUI intl backgrounds   02a_generate_intl_backgrounds.py  9 images (3 scenes x JP/DE/BR)
  copy      Copy generation            02b_generate_copy_preview.py      Claude generates US CTAs + intl translations
            Apply copy                 02c_apply_copy_preview.py         Writes copy to variants.json
  render    AE Render                  03_populate_templates.py        Populate + render in one aerender call
  deliver   Deliver                    05_deliver.py                   Organize output + upload to Google Drive

NOTE: C4D renders are a manual step. Run the Cinema 4D scripts inside Cinema 4D first,
or launch them from the dashboard (Step 1 → scene buttons).

USAGE:
  python run_pipeline.py                         # Full run — all 4 markets (112 renders)
  python run_pipeline.py --market US             # US only (28 renders)
  python run_pipeline.py --market JP             # JP only (28 renders)
  python run_pipeline.py --from-step render      # Skip prep/backgrounds/copy, go straight to render
  python run_pipeline.py --skip-bg               # Skip background generation (backgrounds already exist)
  python run_pipeline.py --skip-copy             # Skip copy generation (copy already applied)
  python run_pipeline.py --no-drive              # Skip Google Drive upload

CRASH RECOVERY:
  Each script tracks status in output/variants.json. If the pipeline stops,
  re-run the same command — completed variants are automatically skipped.
  Use --from-step to resume from a specific step.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Force UTF-8 so Japanese/German/Portuguese characters print correctly on Windows
os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))

from scripts.utils.logger import log

BASE_DIR = Path(__file__).parent

# Step names in order — used for --from-step logic
STEP_ORDER = ["prep", "bg-us", "bg-intl", "copy", "render", "deliver"]


def run_script(script_name: str, extra_args: list[str] = None) -> bool:
    """
    Runs a pipeline script as a subprocess and returns True on success.
    Each step runs in its own process — no shared state, and sys.exit() in a
    child script won't kill the orchestrator.
    """
    script_path = BASE_DIR / "scripts" / script_name
    cmd = [sys.executable, str(script_path)] + (extra_args or [])
    result = subprocess.run(cmd)
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(
        description="Yosuki Motion Graphics Pipeline — CLI runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--market",
        type=str,
        default=None,
        metavar="MARKET_ID",
        help="Run for a single market only: US, JP, DE, BR. Omit for all markets.",
    )
    parser.add_argument(
        "--from-step",
        type=str,
        default="bg-us",
        choices=STEP_ORDER,
        metavar="STEP",
        help=f"Resume from this step. Options: {', '.join(STEP_ORDER)}. Default: bg-us (start from beginning).",
    )
    parser.add_argument(
        "--skip-bg",
        action="store_true",
        help="Skip background generation (bg-us and bg-intl). Use when backgrounds already exist.",
    )
    parser.add_argument(
        "--skip-copy",
        action="store_true",
        help="Skip copy generation and apply. Use when copy is already in variants.json.",
    )
    parser.add_argument(
        "--no-drive",
        action="store_true",
        help="Skip Google Drive upload in the deliver step.",
    )
    args = parser.parse_args()

    market_flag = ["--market", args.market] if args.market else []

    # ── Banner ─────────────────────────────────────────────────────
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║       YOSUKI MOTION GRAPHICS PIPELINE                   ║")
    print("║       Find Your Sound — Spring 2026                     ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    log.info(f"Market:     {args.market or 'All (US, JP, DE, BR)'}")
    log.info(f"From step:  {args.from_step}")
    log.info(f"Asset prep: Auto-skip if cutouts exist")
    log.info(f"Skip BG:    {'Yes' if args.skip_bg else 'No'}")
    log.info(f"Skip Copy:  {'Yes' if args.skip_copy else 'No'}")
    log.info(f"Drive:      {'Disabled' if args.no_drive else 'Enabled (if GOOGLE_DRIVE_FOLDER_ID set)'}")
    print()

    # ── Step definitions ───────────────────────────────────────────
    # Each entry: (step_key, label, script, extra_args)
    # step_key matches STEP_ORDER for --from-step logic.
    # bg-intl is skipped automatically when --market US.
    # prep auto-skips internally if all cutouts already exist (no extra flag needed).
    steps = [
        (
            "prep",
            "Asset Prep — rembg background removal",
            "00_prep_assets.py",
            [],  # no flags — script auto-skips existing cutouts
        ),
        (
            "bg-us",
            "ComfyUI — US Backgrounds",
            "02_generate_backgrounds.py",
            [],
        ),
        (
            "bg-intl",
            "ComfyUI — International Backgrounds",
            "02a_generate_intl_backgrounds.py",
            market_flag,  # --market JP/DE/BR or empty (all intl markets)
        ),
        (
            "copy",
            "Generate Copy Preview",
            "02b_generate_copy_preview.py",
            [],
        ),
        (
            "copy-apply",  # internal — runs as part of the "copy" step group
            "Apply Copy to variants.json",
            "02c_apply_copy_preview.py",
            [],
        ),
        (
            "render",
            "AE Render (populate + aerender)",
            "03_populate_templates.py",
            market_flag,
        ),
        (
            "deliver",
            "Deliver + Google Drive Upload",
            "05_deliver.py",
            market_flag + (["--no-drive"] if args.no_drive else []),
        ),
    ]

    # ── Run steps ──────────────────────────────────────────────────
    from_idx = STEP_ORDER.index(args.from_step)

    for step_key, label, script, extra in steps:

        # Resolve the position of this step in STEP_ORDER
        # (copy-apply is grouped with copy, so it shares copy's index)
        order_key = "copy" if step_key == "copy-apply" else step_key
        step_idx  = STEP_ORDER.index(order_key) if order_key in STEP_ORDER else from_idx

        # Skip steps before --from-step
        if step_idx < from_idx:
            log.info(f"  Skipping: {label}")
            continue

        # Skip background steps if --skip-bg
        if args.skip_bg and step_key in ("bg-us", "bg-intl"):
            log.info(f"  Skipping: {label}  (--skip-bg)")
            continue

        # Skip copy steps if --skip-copy
        if args.skip_copy and step_key in ("copy", "copy-apply"):
            log.info(f"  Skipping: {label}  (--skip-copy)")
            continue

        # Skip intl backgrounds when running US-only
        if step_key == "bg-intl" and args.market == "US":
            log.info(f"  Skipping: {label}  (not needed for US market)")
            continue

        log.section(f"{label}")

        ok = run_script(script, extra)

        if not ok:
            print()
            log.error(f"Pipeline stopped at: {label}")
            log.error("Fix the issue above, then resume with:")
            resume_flag = f" --from-step {order_key}"
            market_part = f" --market {args.market}" if args.market else ""
            log.error(f"  python run_pipeline.py{resume_flag}{market_part}")
            sys.exit(1)

    # ── Done ───────────────────────────────────────────────────────
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  ✓  PIPELINE COMPLETE                                   ║")
    print("║     Check output/delivery/ for your renders             ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()


if __name__ == "__main__":
    main()
