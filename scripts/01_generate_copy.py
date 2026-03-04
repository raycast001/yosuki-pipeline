"""
01_generate_copy.py — Generate all ad copy using Claude API
============================================================
PURPOSE:
  Takes brief.json (the creative brief you wrote) and uses Claude to generate
  culturally adapted ad copy for every product × aspect ratio × market combination.

  Example output for one variant:
    {
      "variant_id": "sax_signature_US_billboard_970x250",
      "product_id": "sax_signature",
      "market": "US",
      "ratio": "billboard_970x250",
      "tagline": "Own Every Stage",
      "series_title": "Signature Series Saxophone",
      "cta": "Find Your Sound",
      "comfyui_prompt": "Intimate jazz club interior, warm golden bokeh ...",
      "status": "copy_done"
    }

HOW IT WORKS:
  1. Reads brief.json to get all products and markets
  2. Builds one big prompt asking Claude for copy for EVERY variant at once
     (this is more efficient and cheaper than one API call per variant)
  3. Claude returns a JSON array — we parse and validate it
  4. Any tagline over 6 words or CTA over 4 words triggers a targeted retry
  5. Saves everything to output/variants.json

CRASH SAFETY:
  If the script crashes halfway, variants.json is written immediately.
  Subsequent scripts check each variant's `status` field and skip completed ones.

FILTERING:
  Pass --market US to only generate copy for one market (useful for testing).

RUN:
  python scripts/01_generate_copy.py             # All 4 markets (108 variants)
  python scripts/01_generate_copy.py --market US # US only (27 variants)
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import os
os.environ["PYTHONIOENCODING"] = "utf-8"


import anthropic

from config import ANTHROPIC_API_KEY, BRIEF_JSON, CLAUDE_MODEL, VARIANTS_JSON
from scripts.utils.logger import log
from scripts.utils.validate import validate_brief


# ─────────────────────────────────────────────
# HOW MANY TIMES TO RETRY IF COPY IS TOO LONG
# ─────────────────────────────────────────────
MAX_RETRIES = 3


def build_variants_list(brief: dict, market_filter: str | None) -> list[dict]:
    """
    Expands brief.json into a flat list of variant dicts.
    Each dict represents one render: one product + one ratio + one market.

    Example row:
      { "variant_id": "sax_signature_US_16x9", "product_id": "sax_signature",
        "market": "US", "ratio": "16x9", "status": "pending" }
    """
    variants = []
    markets = brief["markets"]

    # Filter to a single market if --market flag was passed
    if market_filter:
        markets = [m for m in markets if m["id"] == market_filter]
        if not markets:
            log.error(f"Market '{market_filter}' not found in brief.json")
            sys.exit(1)

    for product in brief["products"]:
        for ratio in product["aspect_ratios"]:
            for market in markets:
                variant_id = f"{product['product_id']}_{market['id']}_{ratio}"
                variants.append({
                    "variant_id":  variant_id,
                    "product_id":  product["product_id"],
                    "series":      product["series"],
                    "model":       product.get("model", ""),
                    "color":       product.get("color"),
                    "market":      market["id"],
                    "language":    market["language"],
                    "ratio":       ratio,
                    "product_image": product["product_image"],
                    # Copy fields — filled in by Claude
                    "tagline":       "",
                    "series_title":  "",
                    "cta":           "",
                    "comfyui_prompt": "",
                    # Status tracking for crash recovery
                    "status": "pending",
                })

    return variants


def build_claude_prompt(brief: dict, batch: list[dict]) -> str:
    """
    Builds the prompt we send to Claude.
    We ask for ALL variants in one prompt to save API calls and cost.

    The prompt tells Claude:
    - What the brand is and its pillars
    - The copy constraints (max 6 words tagline, max 4 words CTA)
    - Each variant's product, market, scene, tone, and language
    - The exact JSON format we expect back

    Claude returns a JSON array with one object per variant.
    """
    constraints = brief["copy_constraints"]

    # Build a human-readable list of all the variants we need
    variant_lines = []
    for v in batch:
        product = next(p for p in brief["products"] if p["product_id"] == v["product_id"])
        market  = next(m for m in brief["markets"]   if m["id"]         == v["market"])
        color_note = f", color: {v['color']}" if v["color"] else ""
        variant_lines.append(
            f'  - variant_id: "{v["variant_id"]}" | '
            f'product: {product["model"]}{color_note} ({product["series"]}) | '
            f'ratio: {v["ratio"]} | '
            f'market: {v["market"]} | language: {market["language"]} | '
            f'tone: {market["tone"]} | '
            f'key_message: "{product["key_message"]}" | '
            f'scene: "{product["scene"]}" | '
            f'vibe: "{product["vibe"]}"'
        )

    variants_block = "\n".join(variant_lines)

    prompt = f"""You are a senior copywriter for {brief["brand"]}.
Campaign: "{brief["campaign_name"]}"
Brand pillars: {brief["brand_pillars"]}

COPY RULES (strictly enforced — violating these causes automatic retries):
- tagline: max {constraints["tagline_max_words"]} words. Bold, direct, culturally adapted — NOT a literal translation. No clichés.
- series_title: translate the product line name naturally into the target language (e.g. "Savant Series Piano" in Japanese)
- cta: max {constraints["cta_max_words"]} words. Action-oriented. Natural in the target language.
- comfyui_prompt: English only regardless of market. Vivid visual scene description for AI image generation.
  Include: lighting style, atmosphere, color palette, mood, environment, bokeh/depth-of-field notes.
  Do NOT include the instrument itself — only the background scene. ~40-60 words.
- no_line_breaks: {constraints["no_line_breaks"]} — no \\n characters anywhere in copy fields
- {constraints.get("note", "")}

Generate copy for each of the following variants. Return ONLY a valid JSON array — no markdown, no explanation, just the JSON.

Each object must have exactly these keys:
  variant_id, tagline, series_title, cta, comfyui_prompt

VARIANTS TO GENERATE:
{variants_block}

Return format example:
[
  {{
    "variant_id": "sax_signature_US_16x9",
    "tagline": "Own Every Stage",
    "series_title": "Signature Series Saxophone",
    "cta": "Find Your Sound",
    "comfyui_prompt": "Intimate jazz club interior, warm golden bokeh light, thin haze drifting across a spotlit stage, deep burgundy velvet curtains, rich amber tones, close-up brass reflections, cinematic depth of field, moody film photography aesthetic"
  }},
  ...
]"""

    return prompt


def check_word_limits(variant: dict, constraints: dict) -> list[str]:
    """
    Returns a list of violation messages (empty list = all good).
    Word count is simple: split on spaces.
    """
    violations = []
    max_tag = constraints.get("tagline_max_words", 6)
    max_cta = constraints.get("cta_max_words", 4)

    tagline_words = len(variant.get("tagline", "").split())
    cta_words     = len(variant.get("cta", "").split())

    if tagline_words > max_tag:
        violations.append(
            f"tagline is {tagline_words} words (max {max_tag}): \"{variant['tagline']}\""
        )
    if cta_words > max_cta:
        violations.append(
            f"cta is {cta_words} words (max {max_cta}): \"{variant['cta']}\""
        )
    return violations


def retry_single_variant(client: anthropic.Anthropic, variant: dict, brief: dict) -> dict | None:
    """
    Called when a single variant's copy is too long.
    Sends a targeted correction prompt and returns updated copy dict, or None on failure.
    """
    constraints = brief["copy_constraints"]
    for attempt in range(1, MAX_RETRIES + 1):
        log.warn(f"  Retry {attempt}/{MAX_RETRIES} for {variant['variant_id']}...")
        retry_prompt = f"""The following copy violates word limits. Rewrite ONLY the fields that are too long.
Keep the cultural tone, language ({variant['language']}), and meaning. Return ONLY a JSON object.

Current copy:
  tagline:      "{variant.get('tagline', '')}"  (max {constraints['tagline_max_words']} words)
  cta:          "{variant.get('cta', '')}"       (max {constraints['cta_max_words']} words)

Return format (same keys, corrected values):
{{
  "variant_id": "{variant['variant_id']}",
  "tagline": "...",
  "series_title": "{variant.get('series_title', '')}",
  "cta": "...",
  "comfyui_prompt": "{variant.get('comfyui_prompt', '')}"
}}"""

        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=300,
                messages=[{"role": "user", "content": retry_prompt}]
            )
            raw = response.content[0].text.strip()
            corrected = json.loads(raw)
            violations = check_word_limits(corrected, constraints)
            if not violations:
                return corrected
            log.warn(f"  Still over limit after retry {attempt}: {violations}")
        except Exception as e:
            log.error(f"  Retry {attempt} failed with error: {e}")

    return None  # All retries exhausted


def run(market_filter: str | None = None):
    log.section("STEP 1 — COPY GENERATION (Claude API)")

    # ── Validate API key ──────────────────────────────────────────
    if not ANTHROPIC_API_KEY:
        log.error("ANTHROPIC_API_KEY not found. Add it to your .env file.")
        sys.exit(1)

    # ── Validate brief.json ───────────────────────────────────────
    brief = validate_brief(BRIEF_JSON)

    # ── Build the full list of variants ──────────────────────────
    variants = build_variants_list(brief, market_filter)
    log.info(f"Total variants to generate: {len(variants)}")

    # ── Check if variants.json already exists (crash recovery) ───
    # If it does, we only regenerate variants still marked "pending"
    existing_variants = {}
    if VARIANTS_JSON.exists():
        with open(VARIANTS_JSON, encoding="utf-8") as f:
            existing_list = json.load(f)
        existing_variants = {v["variant_id"]: v for v in existing_list}
        done_count = sum(1 for v in existing_list if v.get("status") != "pending")
        log.info(f"Found existing variants.json — {done_count} already complete, skipping those.")

    # Merge: keep completed variants, only re-generate pending ones
    pending = []
    for v in variants:
        if v["variant_id"] in existing_variants:
            existing = existing_variants[v["variant_id"]]
            if existing.get("status") != "pending":
                # Already done — keep the existing data
                # (We'll merge at the end)
                continue
        pending.append(v)

    if not pending:
        log.ok("All variants already have copy. Nothing to do.")
        log.info("Next step: python scripts/02_generate_backgrounds.py")
        return

    log.info(f"Generating copy for {len(pending)} variant(s)...")

    # ── Call Claude API ───────────────────────────────────────────
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # We send all pending variants in ONE API call for efficiency
    # For very large batches (>50), consider splitting into chunks of 30
    prompt = build_claude_prompt(brief, pending)

    log.info("Sending request to Claude API...")
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=8192,  # Plenty of room for 108 variants
            messages=[{"role": "user", "content": prompt}]
        )
    except anthropic.AuthenticationError:
        log.error("Invalid API key. Check your ANTHROPIC_API_KEY in .env")
        sys.exit(1)
    except Exception as e:
        log.error(f"Claude API request failed: {e}")
        sys.exit(1)

    # ── Parse Claude's response ───────────────────────────────────
    raw_text = response.content[0].text.strip()

    # Claude sometimes wraps JSON in ```json ... ``` markdown — strip that
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        raw_text = "\n".join(lines[1:-1])

    try:
        claude_results = json.loads(raw_text)
    except json.JSONDecodeError as e:
        log.error(f"Claude returned invalid JSON: {e}")
        log.error(f"Raw response (first 500 chars): {raw_text[:500]}")
        sys.exit(1)

    # ── Index Claude's results by variant_id ──────────────────────
    claude_by_id = {item["variant_id"]: item for item in claude_results}

    # ── Validate word limits + retry if needed ───────────────────
    constraints = brief["copy_constraints"]
    final_results = {}

    for v in pending:
        vid = v["variant_id"]
        if vid not in claude_by_id:
            log.warn(f"Claude did not return copy for: {vid}")
            continue

        copy = claude_by_id[vid]
        violations = check_word_limits(copy, constraints)

        if violations:
            log.warn(f"Word limit violation for {vid}:")
            for violation in violations:
                log.warn(f"  → {violation}")
            # Attempt targeted retry
            corrected = retry_single_variant(client, {**v, **copy}, brief)
            if corrected:
                copy = corrected
                log.ok(f"  Retry succeeded for {vid}")
            else:
                log.warn(f"  Could not fix {vid} — keeping over-limit copy")

        final_results[vid] = copy

    # ── Merge back into full variants list ────────────────────────
    # Re-build the complete list: existing completed + new results
    all_variants_by_id = {v["variant_id"]: v for v in variants}

    # Apply existing completed data
    for vid, existing in existing_variants.items():
        if existing.get("status") != "pending" and vid in all_variants_by_id:
            all_variants_by_id[vid] = existing

    # Apply new Claude results
    for vid, copy in final_results.items():
        if vid in all_variants_by_id:
            all_variants_by_id[vid].update({
                "tagline":        copy.get("tagline", ""),
                "series_title":   copy.get("series_title", ""),
                "cta":            copy.get("cta", ""),
                "comfyui_prompt": copy.get("comfyui_prompt", ""),
                "status":         "copy_done",
            })

    # ── Save variants.json ────────────────────────────────────────
    VARIANTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    output_list = list(all_variants_by_id.values())

    with open(VARIANTS_JSON, "w", encoding="utf-8") as f:
        json.dump(output_list, f, ensure_ascii=False, indent=2)

    done = sum(1 for v in output_list if v.get("status") == "copy_done")
    log.ok(f"variants.json saved — {done}/{len(output_list)} variants have copy")
    log.info(f"File: {VARIANTS_JSON}")
    log.info("Next step: python scripts/02_generate_backgrounds.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate ad copy for all variants.")
    parser.add_argument(
        "--market",
        type=str,
        default=None,
        help="Filter to a single market (e.g. --market US). Omit for all markets."
    )
    args = parser.parse_args()
    run(market_filter=args.market)
