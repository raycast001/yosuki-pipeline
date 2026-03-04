"""
validate.py — Validates brief.json before the pipeline runs
============================================================
Catches mistakes early (missing fields, wrong types, unknown ratios)
so you don't waste time running ComfyUI only to fail on a typo.

Usage:
    from scripts.utils.validate import validate_brief
    brief = validate_brief("brief.json")  # Returns parsed dict or raises SystemExit
"""

import json
import sys
from pathlib import Path

from scripts.utils.logger import log


# ─────────────────────────────────────────────
# VALID VALUES
# ─────────────────────────────────────────────

VALID_RATIOS = {"billboard_970x250", "16x9", "1x1"}
VALID_MARKET_IDS = {"US", "JP", "DE", "BR"}

# Every product must have these keys
REQUIRED_PRODUCT_KEYS = {
    "product_id", "series", "model", "key_message",
    "scene", "vibe", "visual_motifs",
    "source_image", "product_image", "aspect_ratios"
}

# Every market must have these keys
REQUIRED_MARKET_KEYS = {"id", "language", "tone"}


# ─────────────────────────────────────────────
# MAIN VALIDATION FUNCTION
# ─────────────────────────────────────────────

def validate_brief(brief_path: str | Path) -> dict:
    """
    Loads and validates brief.json.

    Returns the parsed dict if valid.
    Calls sys.exit(1) with an error message if anything is wrong.

    Why sys.exit instead of raising an exception?
    Because this is called from pipeline scripts, and we want a clean
    terminal error — not a Python traceback — when there's a config mistake.
    """
    brief_path = Path(brief_path)

    # ── 1. File exists ──────────────────────────────────────────
    if not brief_path.exists():
        log.error(f"brief.json not found at: {brief_path}")
        sys.exit(1)

    # ── 2. Valid JSON ────────────────────────────────────────────
    try:
        with open(brief_path, encoding="utf-8") as f:
            brief = json.load(f)
    except json.JSONDecodeError as e:
        log.error(f"brief.json has invalid JSON syntax: {e}")
        sys.exit(1)

    # ── 3. Top-level required keys ───────────────────────────────
    for key in ("campaign_name", "brand", "markets", "copy_constraints", "products"):
        if key not in brief:
            log.error(f"brief.json is missing required top-level key: '{key}'")
            sys.exit(1)

    # ── 4. Markets ───────────────────────────────────────────────
    markets = brief["markets"]
    if not isinstance(markets, list) or len(markets) == 0:
        log.error("brief.json 'markets' must be a non-empty list.")
        sys.exit(1)

    for market in markets:
        missing = REQUIRED_MARKET_KEYS - set(market.keys())
        if missing:
            log.error(f"Market entry missing keys: {missing}  →  {market}")
            sys.exit(1)
        if market["id"] not in VALID_MARKET_IDS:
            log.warn(f"Unknown market id '{market['id']}'. Expected one of: {VALID_MARKET_IDS}")

    # ── 5. Products ───────────────────────────────────────────────
    products = brief["products"]
    if not isinstance(products, list) or len(products) == 0:
        log.error("brief.json 'products' must be a non-empty list.")
        sys.exit(1)

    seen_ids = set()
    for product in products:

        # Check for missing required keys
        missing = REQUIRED_PRODUCT_KEYS - set(product.keys())
        if missing:
            pid = product.get("product_id", "(unknown)")
            log.error(f"Product '{pid}' is missing required keys: {missing}")
            sys.exit(1)

        # Check for duplicate product IDs
        pid = product["product_id"]
        if pid in seen_ids:
            log.error(f"Duplicate product_id found: '{pid}'. All product IDs must be unique.")
            sys.exit(1)
        seen_ids.add(pid)

        # Check aspect ratios are valid strings
        for ratio in product["aspect_ratios"]:
            if ratio not in VALID_RATIOS:
                log.error(f"Product '{pid}' has unknown aspect ratio: '{ratio}'. Valid: {VALID_RATIOS}")
                sys.exit(1)

        # Check source image exists on disk
        source = Path(product["source_image"])
        if not source.exists():
            log.warn(f"Product '{pid}': source_image not found: {source}")
            log.warn("  → Run 00_prep_assets.py first, or check the path.")

    # ── 6. Copy constraints ──────────────────────────────────────
    constraints = brief.get("copy_constraints", {})
    if constraints.get("tagline_max_words", 0) < 1:
        log.error("copy_constraints.tagline_max_words must be a positive number.")
        sys.exit(1)

    log.ok(f"brief.json is valid — {len(products)} products, {len(markets)} markets")
    return brief
