# International Markets — Reference Guide

All 112 renders (28 US + 84 international) are complete. This document explains how the international pipeline works for future re-runs or new campaigns.

---

## How International Copy Works

The pipeline does **cultural adaptation**, not literal translation.

| Approach | What it does |
|----------|-------------|
| Literal translation | Takes "Own the stage" and converts it word-for-word |
| Cultural adaptation | Asks: *what would a musician in this market actually respond to?* Then writes that |

### US copy is locked at the family level

Taglines are fixed in `brief.json` under `families` — Claude does not invent them:

| Family | Locked US Tagline |
|--------|------------------|
| Saxophone | Own the stage |
| Pianos | Crafted for Generations |
| Guitars | Play Loud |

Claude only generates the **CTA** for US markets.

### International copy is driven by US copy

For JP, DE, BR: Claude receives the US tagline + CTA and produces a culturally adapted version in the target language. The `tone` and `visual_culture` in `brief.json` guide this adaptation:

| Market | Tone |
|--------|------|
| JP | Respectful, refined, craftsmanship-focused |
| DE | Precision, engineering excellence. Shorter phrasing (compound words). |
| BR | Emotional, energetic, expressive |

---

## How International Backgrounds Work

International backgrounds are separate from US backgrounds. Each market gets its own version of the 3 scene backgrounds, with the market's `visual_culture` from `brief.json` appended to the Flux prompt.

**9 images total** (3 scenes × 3 markets):

```
output/backgrounds/
├── sax_JP_16x9.png    piano_JP_16x9.png    guitar_JP_16x9.png
├── sax_DE_16x9.png    piano_DE_16x9.png    guitar_DE_16x9.png
└── sax_BR_16x9.png    piano_BR_16x9.png    guitar_BR_16x9.png
```

All use Flux Canny ControlNet with the same C4D renders as ControlNet input — only the prompt changes between markets.

**All products in a scene family share one background per market.** For example, `guitar_JP_16x9.png` is used for all 6 guitar variants (3 models × 2 colours) in the JP market.

---

## What Changes Per Market vs. What Stays the Same

| Element | Same across markets? | Notes |
|---------|---------------------|-------|
| Product cutout PNG | ✅ Yes | Same sax/piano/guitar image |
| AE template (.aep) | ✅ Yes | Same animation structure |
| Background image | ❌ No | Intl markets have their own culturally adapted backgrounds |
| Tagline text | ❌ No | Culturally adapted in each market's language |
| Series title text | ❌ No | Translated naturally |
| CTA text | ❌ No | Culturally adapted |

---

## Re-Running International Renders

### To generate new background variations for a market:

```bash
# Regenerate all 3 backgrounds for JP (new Flux variations)
python scripts/02a_generate_intl_backgrounds.py --market JP --force

# Or use the dashboard: Step 2 → International tab → JP → "Generate new variation"
```

### To re-render a market after new backgrounds:

```bash
python scripts/03_populate_templates.py --market JP
```

The `--market` flag resets all variants for that market from `rendered` back to `copy_generated`, then re-renders them with the new backgrounds.

### To re-run the full international pipeline for one market:

```bash
# Via dashboard: Run Full Pipeline → select JP → uncheck Skip ComfyUI → Run

# Or via command line:
python scripts/02a_generate_intl_backgrounds.py --market JP --force
python scripts/03_populate_templates.py --market JP
python scripts/05_deliver.py --market JP
```

---

## Things to Watch For

**German compound words**
German produces very long words that can overflow text layers. After rendering DE, spot-check a few variants to confirm text isn't being cut off.

**Japanese character rendering**
AE templates must have a font installed that supports Japanese (kanji, hiragana, katakana). Before batch rendering JP, open a template manually and click a text layer — if the font shows squares, switch to a Japanese-compatible font (e.g. Noto Sans JP, Source Han Sans).

**Word count limits**
`brief.json` constrains taglines to max 6 words and CTAs to max 4 words. Japanese has no spaces between words, so JP copy is typically a single "word" by space-count even if conceptually long. Check JP renders visually rather than relying on word count.

**Background fallback**
If an international background file doesn't exist for a scene+market, `03_populate_templates.py` automatically falls back to the US product background for that variant. You'll see a warning in the terminal but the render won't fail.
