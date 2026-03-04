"""
02c_apply_copy_preview.py
=====================
Applies the approved copy from copy_preview.json into variants.json,
then creates international (JP, DE, BR) variants from the US variants.

Run this after reviewing 02b_generate_copy_preview.py output and approving the copy.

What this does:
  1. Updates all US variants with the new tagline + CTA from the preview
  2. Resets their status to "copy_generated" so they re-render with the new copy
  3. Creates new JP, DE, BR variants cloned from US variants with translated copy
  4. Saves everything back to variants.json

Then run:
  python scripts/03_populate_templates.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import BRIEF_JSON, COPY_PREVIEW_JSON, VARIANTS_JSON

# ── Load copy preview ────────────────────────────────────────────────────────
if not COPY_PREVIEW_JSON.exists():
    print("ERROR: copy_preview.json not found. Run 02b_generate_copy_preview.py first.")
    sys.exit(1)

with open(COPY_PREVIEW_JSON, encoding="utf-8") as f:
    preview = json.load(f)

# us:   {product_id: {tagline, cta, series_title}}
# intl: {product_id_marketid: {tagline, series_title, cta}}
us_copy   = preview["us"]
intl_copy = preview["intl"]

# ── Load brief for market info ───────────────────────────────────────────────
with open(BRIEF_JSON, encoding="utf-8") as f:
    brief = json.load(f)

market_language = {m["id"]: m["language"] for m in brief["markets"]}
intl_markets    = [m for m in brief["markets"] if m["id"] != "US"]

# ── Load variants.json — keep only US variants as the base ───────────────────
with open(VARIANTS_JSON, encoding="utf-8") as f:
    all_variants = json.load(f)

us_variants = [v for v in all_variants if v.get("market") == "US"]

# ── 1. Update US variants with new copy, reset status ───────────────────────
updated = 0
for v in us_variants:
    pid = v["product_id"]
    if pid in us_copy:
        c = us_copy[pid]
        v["tagline"] = c["tagline"]
        v["cta"]     = c["cta"]
        # series_title is kept from the original — not touched
        v["status"]  = "copy_generated"   # reset so it re-renders with new copy
        updated += 1

print(f"Updated {updated} US variants with new copy.")

# ── 2. Build international variants ─────────────────────────────────────────
# Clone each US variant, swap in the translated copy, and assign the market.
intl_variants = []
missing = []

for mkt in intl_markets:
    mid  = mkt["id"]
    lang = mkt["language"]

    for us_v in us_variants:
        pid = us_v["product_id"]
        key = f"{pid}_{mid}"

        if key not in intl_copy:
            missing.append(key)
            continue

        c = intl_copy[key]

        # Clone the US variant and override market-specific fields
        intl_v = dict(us_v)
        intl_v["variant_id"]   = f"{pid}_{mid}_{us_v['ratio']}"
        intl_v["market"]       = mid
        intl_v["language"]     = lang
        intl_v["tagline"]      = c.get("tagline", "")
        intl_v["series_title"] = c.get("series_title", us_v["series_title"])
        intl_v["cta"]          = c.get("cta", "")
        intl_v["status"]       = "copy_generated"
        intl_variants.append(intl_v)

market_ids = ", ".join(m["id"] for m in intl_markets)
print(f"Created {len(intl_variants)} international variants ({market_ids}).")

if missing:
    print(f"WARNING: No intl copy found for: {', '.join(missing)}")

# ── 3. Combine and save ──────────────────────────────────────────────────────
final_variants = us_variants + intl_variants
with open(VARIANTS_JSON, "w", encoding="utf-8") as f:
    json.dump(final_variants, f, ensure_ascii=False, indent=2)

print(f"\nVariants saved: {len(final_variants)} total "
      f"({len(us_variants)} US + {len(intl_variants)} intl)")
print("\nNext step: python scripts/03_populate_templates.py")
