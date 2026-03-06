# Presentation Guide — 20 Minutes
## Yosuki "Find Your Sound" — Spring 2026 Campaign Pipeline

---

## Overview of the 20 Minutes

| Block | Time | What you're doing |
|-------|------|-------------------|
| The Problem | 2 min | Frame the brief — why this is hard manually |
| The Architecture | 3 min | The big picture — what the pipeline does |
| Live Demo: Dashboard | 7 min | Walk through the 5 steps for the US market |
| The Output | 4 min | Show US renders, then briefly show intl as an extension |
| Design Decisions | 2 min | Why these tools, why this architecture |
| Wrap-Up | 2 min | What this enables at scale |

---

## Block 1 — The Problem (2 min)

**What to say:**

> "The brief is: produce a full campaign for Yosuki Musical Instruments — 3 instrument families, 10 products, 3 aspect ratios. Doing this manually means an artist placing and rendering every combination by hand. Even for just the US market, that's 28 individual ad variants. At 15 minutes each that's 7 hours of production time — before any rounds of copy changes or background regeneration."

> "The brief specifically invited opting into digital twin 3D workflows and AI image generation. So I treated this as an engineering problem, not just a design problem: build a pipeline that generates all variants automatically, with the creative direction baked in — not bolted on at the end."

**Key US numbers to have ready:**
- 10 products × 3 aspect ratios = **28 US variants**
- 3 scene families: **Saxophone / Piano / Guitar**
- 3 aspect ratios: **16:9, 1:1, Billboard 970×250**

*(International adds another 84 variants on top — more on that at the end.)*

---

## Block 2 — The Architecture (3 min)

**Draw or point to this flow while you talk:**

```
Cinema 4D                 ComfyUI                  After Effects
─────────────             ───────────────────       ──────────────────────
Digital twin    ──────→   Flux Canny ControlNet  →  AE template per ratio
(3 scenes,                (9 unique US backgrounds) + product cutout
 greyscale                                          + Claude copy
 renders)                                                 ↓
                                               aerender batch → 28 US .mp4s
                                                              ↓
                                               Delivery folder (organized)
```

**What to say:**

> "There are four creative inputs: a Cinema 4D digital twin for scene structure, ComfyUI with Flux for photorealistic backgrounds, Claude for ad copy, and After Effects templates for the final compositing. The Python pipeline glues them together — it orchestrates the API calls, populates the templates, and drives aerender to batch-render all the variants."

> "Everything is driven by a single `brief.json` file. That's the creative brief as code. Change it, re-run the pipeline, get new output."

---

## Block 3 — Live Demo: Dashboard (7 min)

**Run:** `streamlit run dashboard.py`

Walk through each step — **stay focused on US market throughout.**

### Step 1 — C4D Scene Renders (1.5 min)
- "Step 1 is the 3D foundation. Cinema 4D renders a clean greyscale scene — no textures, no product, just the geometry and lighting."
- Show the 3 scene thumbnails in the dashboard.
- "These are the ControlNet inputs. I'm using C4D as a digital twin — the same camera angle and floor plane that the real product will sit in. This is what makes the AI-generated background feel spatially correct rather than generic stock imagery."

### Step 2 — Background Generation (2 min)
- "Step 2 is the AI generation. The C4D render gets uploaded to ComfyUI, Canny edge detection extracts the structural lines, and Flux generates a photorealistic scene within those edges."
- Show the US backgrounds tab — 9 backgrounds (one per product family × ratio).
- "The scene direction comes from `brief.json` — the `comfyui_prompt` field on each product. A saxophone scene might say 'moody jazz club, stage lighting, brick walls.' Flux generates the photorealistic version of that description, constrained to the spatial layout from C4D."

> **International aside:** "The International tab shows the same thing for JP, DE, BR — same C4D structure, different cultural feel in the prompt. But that's an extension — the US pipeline is the core."

### Step 3 — Copy Generation (1.5 min)
- "Step 3 is Claude. Two things happen: Claude generates US CTAs, then I can review and approve before anything gets applied to a render."
- Show the copy preview — tagline (locked from brief), CTA (Claude-generated).
- "Taglines are locked in the brief — that's the creative director's decision. Claude only writes the CTAs. The preview step is a checkpoint — you see exactly what copy will appear in the renders before committing."

### Step 4 — AE Render (1.5 min)
- "Step 4 is where the pipeline drives After Effects. Each variant gets its background, product cutout, and copy injected into the AE template via ExtendScript, then aerender renders it to MP4."
- Show the render queue / progress if available.
- "The templates have named placeholder layers — `BG_IMAGE_PLACEHOLDER`, `PRODUCT_CUTOUT_PLACEHOLDER`, `TAGLINE`, `CTA_TEXT`. The script finds each layer by name and swaps in the real asset. Fully automated."

### Step 5 — Delivery (0.5 min)
- "Step 5 organises everything into a clean delivery folder — sorted by market, then ratio. Ready to hand off."

---

## Block 4 — The Output (4 min)

**Show US renders first — this is the main story.**

1. **Open the delivery folder → US/** — show the folder structure (16x9 / 1x1 / billboard)
2. **Play 2–3 US renders** — one 16x9, one 1x1, one billboard
3. **Point out what's composited** — background from Flux, product cutout from rembg, copy from Claude, all assembled in AE

**Then briefly show international as a bonus:**

> "The pipeline also extends to international markets. For JP, DE, and BR — same products, same AE templates, different backgrounds generated with a market-specific visual culture prompt, and copy translated and adapted by Claude. That gives us 112 total variants across 4 markets. But the architecture is identical — it's the same pipeline running with different inputs."

4. **Play one JP or DE render side-by-side with the matching US render** — same product, visually different market feel.

---

## Block 5 — Design Decisions (2 min)

Hit two focused points:

**1. Why Canny ControlNet instead of just prompting Flux directly?**
> "Without ControlNet, Flux generates beautiful images but with no spatial consistency — every background has a different floor plane, different camera angle, different perspective. The product cutout would look like it was pasted on. The C4D digital twin gives Canny clean edges to work with, and those edges constrain Flux to generate within the same composition every time."

**2. Why a single `config.py` / `.env` pattern?**
> "Machine-specific paths are a portability killer. config.py is the single source of truth — all scripts import from here, nothing is hardcoded. New machine setup is: copy .env.example, fill in your paths, done. This is the kind of thing that matters when you hand a project to a colleague or a new machine."

---

## Block 6 — Wrap-Up (2 min)

**What to say:**

> "What I've built here is a template factory, not a one-off production. The brief.json is the creative brief. The pipeline is the production system. New product — add one entry to brief.json and re-run. New market — add it to the markets array, run copy and backgrounds, and the new variants render automatically."

> "The creative judgment is still human: the scene direction, the ControlNet thresholds, the copy tone, the template layouts. The pipeline removes the mechanical repetition of applying those decisions across every size, every product, every market."

**Leave them with this:**
> "28 US renders. First time through, about 30 minutes — mostly ComfyUI generation time and aerender. Any subsequent change re-renders only the affected variants. That's the value."

---

## Things to Have Open / Ready Before You Start

- [ ] Dashboard running: `streamlit run dashboard.py`
- [ ] Delivery folder open in Explorer — US folder visible
- [ ] 2–3 US renders queued up and ready to play
- [ ] 1 international render ready for the "extension" moment
- [ ] `brief.json` open — shows the single creative brief that drives everything
- [ ] This doc minimised in the background as a cheat sheet
