"""
02b_generate_copy_preview.py
Generates copy via Claude API and prints a preview without touching variants.json.

US:
  - tagline: locked in brief.json per product family (Sax = "Own the stage", etc.)
  - CTA: Claude generates one per product family
  - series_title: kept from existing variants.json

International (JP, DE, BR):
  - Driven by the US copy — Claude translates/adapts the US tagline + CTA
  - Does NOT invent new concepts; preserves the US emotional intent
  - Handles text overflow constraints (German compound words, Japanese brevity)
"""

import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import os; os.environ["PYTHONIOENCODING"] = "utf-8"

# Force stdout to UTF-8 so Japanese/German/Portuguese characters print correctly
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import anthropic
from config import ANTHROPIC_API_KEY, BRIEF_JSON, CLAUDE_MODEL, COPY_PREVIEW_JSON, VARIANTS_JSON

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

with open(BRIEF_JSON, encoding="utf-8") as f:
    brief = json.load(f)

# ── Products and families from brief.json ────────────────────────────────────
products = {p["product_id"]: p for p in brief["products"]}

# Build a lookup: product_id → which family it belongs to
families = {f["id"]: f for f in brief["families"]}
pid_to_family = {}
for fid, fdata in families.items():
    for pid in fdata["product_ids"]:
        pid_to_family[pid] = fid

# ── Current US series_titles (kept as-is — only tagline + CTA change) ────────
with open(VARIANTS_JSON, encoding="utf-8") as f:
    existing_us = {}
    for v in json.load(f):
        pid = v["product_id"]
        if pid not in existing_us:
            existing_us[pid] = {
                "series_title": v.get("series_title", ""),
            }

# ── CALL 1 — US CTAs (Claude generates; taglines are locked from brief) ───────
# Build one line per family — pass the locked tagline so Claude can
# write a CTA that feels like a natural follow-through from it
cta_lines = []
for fid, fdata in families.items():
    # Pick one representative product for context
    rep_pid = fdata["product_ids"][0]
    rep_product = products[rep_pid]
    cta_lines.append(
        f'  - family: "{fid}" | product_line: {fdata["label"]} | '
        f'locked_tagline: "{fdata["us_tagline"]}" | '
        f'key_messages: "{rep_product["key_message"]}" | vibe: "{rep_product["vibe"]}"'
    )

cta_prompt = f"""You are a senior copywriter for Yosuki Musical Instrument Corporation.
Campaign: "Find Your Sound" — Spring 2026, US market.
Brand pillars: {brief["brand_pillars"]}
Tone: Aspirational, bold, expressive, in-your-face.

Each product family already has a LOCKED tagline.
Your job: write a CTA that feels like a powerful follow-through from that tagline.

Rules:
- CTA: max 4 words. Action-oriented and direct. No generic "Shop Now" or "Learn More".
- Must complement the locked tagline — not repeat or echo it.
- English only. No line breaks.
- Return ONLY a valid JSON array, no markdown:

[{{"family":"...","cta":"..."}}]

PRODUCT FAMILIES:
{chr(10).join(cta_lines)}"""

print("Calling Claude for US CTAs (taglines are locked from brief)...")
r1 = client.messages.create(model=CLAUDE_MODEL, max_tokens=256,
                              messages=[{"role": "user", "content": cta_prompt}])
raw1 = r1.content[0].text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()

# Map family CTA back to every product_id in that family
family_ctas = {item["family"]: item["cta"] for item in json.loads(raw1)}

# Build us_copy: tagline from brief, CTA from Claude, series_title from variants.json
us_copy = {}
for pid in products:
    fid = pid_to_family[pid]
    us_copy[pid] = {
        "tagline":      families[fid]["us_tagline"],
        "cta":          family_ctas[fid],
        "series_title": existing_us.get(pid, {}).get("series_title", ""),
    }


# ── CALL 2 — International copy (JP, DE, BR) ─────────────────────────────────
# International is driven by US copy.
# Claude translates/adapts the US tagline + CTA — it does not invent new copy.
intl_markets = [m for m in brief["markets"] if m["id"] != "US"]

intl_lines = []
for m in intl_markets:
    for fid, fdata in families.items():
        rep_pid = fdata["product_ids"][0]
        rep_product = products[rep_pid]
        intl_lines.append(
            f'  - key: "{fid}_{m["id"]}" | market: {m["id"]} | '
            f'language: {m["language"]} | tone: {m["tone"]} | '
            f'product_line: {fdata["label"]} | '
            f'us_tagline: "{fdata["us_tagline"]}" | '
            f'us_cta: "{family_ctas[fid]}"'
        )

intl_prompt = f"""You are a senior copywriter for Yosuki Musical Instrument Corporation.
Campaign: "Find Your Sound" — Spring 2026.
Brand pillars: {brief["brand_pillars"]}

The US English copy is LOCKED. Your job is to translate and culturally adapt it for each target market.

Rules:
- Preserve the emotional meaning of the US copy — do NOT invent new concepts.
- The translation should feel native and natural in the target language, not word-for-word literal.
- tagline: translate/adapt the us_tagline. Max 6 words in target language.
- series_title: translate the product line name naturally into the target language.
- cta: translate/adapt the us_cta. Max 4 words in target language. Action-oriented.
- No line breaks anywhere.
- German: use shorter phrasing to account for longer compound words.
- Japanese: max 6 short syllable-words or equivalent, refined and respectful tone.

Return ONLY a valid JSON array, no markdown:
[{{"key":"...","tagline":"...","series_title":"...","cta":"..."}}]

VARIANTS TO TRANSLATE:
{chr(10).join(intl_lines)}"""

print("Calling Claude for international copy (JP, DE, BR) — translating from US...")
r2 = client.messages.create(model=CLAUDE_MODEL, max_tokens=2048,
                              messages=[{"role": "user", "content": intl_prompt}])
raw2 = r2.content[0].text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()

# family+market → copy dict
family_intl = {item["key"]: item for item in json.loads(raw2)}

# Expand to per-product_id keys for apply_copy_preview.py
intl_copy = {}
for m in intl_markets:
    for pid in products:
        fid = pid_to_family[pid]
        family_key   = f"{fid}_{m['id']}"
        product_key  = f"{pid}_{m['id']}"
        if family_key in family_intl:
            intl_copy[product_key] = family_intl[family_key]


# ── SAVE PREVIEW (save FIRST so data isn't lost if printing fails) ────────────
preview = {"us": us_copy, "intl": intl_copy}
with open(COPY_PREVIEW_JSON, "w", encoding="utf-8") as f:
    json.dump(preview, f, ensure_ascii=False, indent=2)

# ── PRINT PREVIEW ─────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("  COPY PREVIEW - review before rendering")
print("="*70)

print("\n-- US " + "-"*64)
for pid, p in products.items():
    c = us_copy[pid]
    print(f"\n  {p['model']} ({p['series']})")
    print(f"    tagline (brief):     {c['tagline']!r}")
    print(f"    cta (AI):            {c['cta']!r}")
    print(f"    series_title (kept): {c['series_title']!r}")

# International: one block per family per market (all products in a family share copy)
for mkt in intl_markets:
    print(f"\n-- {mkt['id']} ({mkt['language']}) " + "-"*(60-len(mkt['language'])))
    for fid, fdata in families.items():
        rep_pid = fdata["product_ids"][0]
        key = f"{rep_pid}_{mkt['id']}"
        c = intl_copy.get(key, {})
        print(f"\n  [{fid.upper()}] {fdata['label']}")
        print(f"    tagline:      {c.get('tagline', '?')!r}")
        print(f"    series_title: {c.get('series_title', '?')!r}")
        print(f"    cta:          {c.get('cta', '?')!r}")

print("\n\nPreview saved to output/copy_preview.json")
print("Run apply_copy_preview.py to write this into variants.json and render.")
