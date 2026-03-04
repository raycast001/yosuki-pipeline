"""
04_render.py — Render populated .aep projects to .mp4 using aerender
=====================================================================
PURPOSE:
  Takes every populated .aep in output/projects/ and renders it to .mp4
  using aerender.exe (After Effects' headless command-line renderer).

HOW IT WORKS:
  For each variant with status "populated":
    aerender.exe -project output/projects/{id}.aep
                 -comp MAIN_COMP
                 -output output/renders/{id}.mp4
                 -OMtemplate "H.264 - Match Source - High bitrate"

OUTPUT MODULE TEMPLATE:
  The -OMtemplate flag must match an output module template saved in your
  After Effects preferences. "H.264 - Match Source - High bitrate" is a
  standard template that should exist by default in AE 2026.
  If you get an error, open AE → Edit → Templates → Output Module and check
  the exact template name, then update AE_OUTPUT_MODULE in config.py.

CRASH SAFETY:
  Variants with status "rendered" or "delivered" are skipped. Re-run freely.

RUN:
  python scripts/04_render.py
  python scripts/04_render.py --variant sax_signature_US_16x9
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import os
os.environ["PYTHONIOENCODING"] = "utf-8"


from config import (
    AE_MAIN_COMP_NAME,
    AE_OUTPUT_MODULE,
    AERENDER_PATH,
    PROJECTS_DIR,
    RENDERS_DIR,
    VARIANTS_JSON,
)
from scripts.utils.logger import log


def render_variant(variant: dict) -> bool:
    """
    Calls aerender.exe to render a single populated .aep project.
    Returns True if render succeeded, False otherwise.
    """
    vid = variant["variant_id"]
    project_path = PROJECTS_DIR / f"{vid}.aep"
    output_path  = RENDERS_DIR  / f"{vid}.mp4"

    if not project_path.exists():
        log.error(f"Project file not found: {project_path}")
        log.error("Did 03_populate_templates.py succeed for this variant?")
        return False

    RENDERS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Build the aerender command ────────────────────────────────
    # -project:    the populated .aep file
    # -comp:       which composition to render (must be MAIN_COMP)
    # -output:     where to save the .mp4
    # -OMtemplate: the After Effects Output Module Template to use for encoding
    # -v ERRORS:   only show error messages (less terminal noise)
    cmd = [
        AERENDER_PATH,
        "-project",    str(project_path),
        "-comp",       AE_MAIN_COMP_NAME,
        "-output",     str(output_path),
        "-OMtemplate", AE_OUTPUT_MODULE,
        "-v",          "ERRORS",
    ]

    log.info(f"  Rendering: {vid}.mp4")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout per render
        )

        if result.returncode != 0:
            log.error(f"  aerender failed (exit code {result.returncode})")
            if result.stderr:
                # Show the last 500 chars of stderr — usually the error is at the end
                log.error(f"  Error output: {result.stderr[-500:]}")
            return False

        # Verify the output file actually exists and has content
        if not output_path.exists() or output_path.stat().st_size == 0:
            log.error(f"  Output file missing or empty: {output_path.name}")
            return False

        size_mb = output_path.stat().st_size / (1024 * 1024)
        log.ok(f"  Rendered: {vid}.mp4 ({size_mb:.1f} MB)")
        return True

    except subprocess.TimeoutExpired:
        log.error(f"  Render timed out after 10 minutes: {vid}")
        return False
    except Exception as e:
        log.error(f"  Render failed: {e}")
        return False


def run(variant_filter: str | None = None):
    log.section("STEP 4 — RENDERING (aerender.exe)")

    # ── Check aerender exists ──────────────────────────────────────
    if not Path(AERENDER_PATH).exists():
        log.error(f"aerender.exe not found at: {AERENDER_PATH}")
        log.error("Check AERENDER_PATH in config.py")
        sys.exit(1)

    # ── Load variants ──────────────────────────────────────────────
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
    else:
        variants = all_variants

    # Filter to populated-only (ready to render)
    to_render = [v for v in variants if v.get("status") == "populated"]
    skipped   = [v for v in variants if v.get("status") in ("rendered", "delivered")]
    pending   = [v for v in variants if v.get("status") not in ("populated", "rendered", "delivered")]

    log.info(f"Ready to render: {len(to_render)} | Already rendered: {len(skipped)} | Not ready: {len(pending)}")

    if pending:
        log.warn(f"{len(pending)} variant(s) not yet populated — run 03_populate_templates.py first")

    if not to_render:
        log.ok("Nothing new to render.")
        return

    # ── Render each variant ────────────────────────────────────────
    success = 0
    failed  = 0

    for i, v in enumerate(to_render, 1):
        log.progress(i, len(to_render), v["variant_id"])

        ok = render_variant(v)
        if ok:
            v["status"] = "rendered"
            success += 1
        else:
            failed += 1

    # ── Save updated variants.json (always save the FULL list) ────────
    with open(VARIANTS_JSON, "w", encoding="utf-8") as f:
        json.dump(all_variants, f, ensure_ascii=False, indent=2)

    print()
    log.ok(f"Done. {success} rendered, {failed} failed.")
    if failed:
        log.warn("Check errors above. Failed variants keep status 'populated' — re-run to retry.")
    log.info("Next step: python scripts/05_deliver.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render all populated AE projects to MP4.")
    parser.add_argument(
        "--variant",
        type=str,
        default=None,
        help="Render a single variant_id only."
    )
    args = parser.parse_args()
    run(variant_filter=args.variant)
