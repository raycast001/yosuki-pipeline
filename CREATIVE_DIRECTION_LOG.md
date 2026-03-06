# Creative Direction Log
## How your decisions shaped the pipeline

This documents the moments across the full build where you pushed back,
redirected, or made a call that made the pipeline better — more efficient,
cleaner, or more useful in practice. Written from the perspective of what
each decision actually changed.

---

## 1. "Save the git repo for last"

**What you said:**
> "Take care of these in the best order, maybe save the git repo for last."

**What it changed:**
The instinct here was right. Git was the lowest-risk step — it doesn't touch
any code, it just captures state. If git had gone first and then a path fix
broke something, the commit would have captured broken code. By saving git
for last, the repo's one and only commit is the clean, tested, fully working
version of the pipeline. Anyone who clones it gets something that runs.

---

## 2. "Run the full pipeline before we move to git"

**What you said:**
> "Before moving onto step 4, can you run the full pipeline again to make
> sure there are no errors please."

**What it changed:**
This caught nothing — and that was the point. It was a quality gate: a
deliberate check before doing something irreversible (publishing to GitHub).
Running `run_pipeline.py --skip-bg --skip-copy --no-drive` and getting
`0 rendered, 112 skipped, 0 failed` was the green light. Without that step,
there's always a chance the polish pass introduced a subtle bug that would
have been committed and pushed publicly. The verification was the right call.

---

## 3. Approving the 02a / 02b / 02c naming scheme

**What you said:**
> Confirmed the sub-letter naming scheme for the three unnumbered scripts.

**What it changed:**
Before this, the scripts folder had a mix of numbered (`02_`, `03_`) and
un-numbered (`generate_copy_preview.py`) files. Anyone scanning the folder
couldn't tell the order without opening each file. The 02a/02b/02c scheme
makes the pipeline sequence self-documenting — you can read the entire
pipeline order just from the filenames:

```
00_prep_assets.py
02_generate_backgrounds.py
02a_generate_intl_backgrounds.py
02b_generate_copy_preview.py
02c_apply_copy_preview.py
03_populate_templates.py
05_deliver.py
```

That's the whole pipeline, readable in one glance.

---

## 4. "The walkthrough should mostly focus on the US market"

**What you said:**
> "Can the walkthrough mostly focus on the US market, and have the caveat
> of how the international markets on the side."

**What it changed:**
The original presentation docs treated US and international as equal halves.
That made the story muddy — a reviewer can't hold both in their head at once.
Reframing it as "US is the core, international is the extension" made the
narrative flow naturally: here's the pipeline, here's what it produces, and
by the way it also scales to 3 more markets. That's a stronger structure
for a 20-minute presentation than trying to cover everything at once.

It also reflects how the pipeline actually works — the US pipeline is the
foundation, and international is genuinely built on top of it.

---

## 5. "Is the dashboard covered anywhere? If not, write a separate doc."

**What you said:**
> "Is the dashboard talked about within any of the documents, if not, can
> you write up a separate md file for it."

**What it changed:**
Caught a real gap. The dashboard was mentioned in the presentation doc as
"run this and click through it" but the actual code — how `run_script()` works,
why the copy step is split into preview + apply, how the full pipeline
orchestrator handles errors — was undocumented. For the 20–30 minute code
walkthrough, that's a section interviewers will definitely dig into.
The dedicated `DASHBOARD_GUIDE.md` now covers every section with the exact
talking points and code snippets to reference.

---

## 6. "Show the English translation next to the foreign copy"

**What you said:**
> "Can you actually have the English translation next to each foreign
> translation so we know what it's saying."

**What it changed:**
Before this, the international copy table showed Japanese, German, and
Portuguese text with no reference point. Unless you speak those languages,
the preview was useless — you couldn't tell if the translation captured the
right tone or if it drifted from the US intent. Adding a `Tagline (EN)` and
`CTA (EN)` column next to each foreign column turned the table into an
actual review tool. You can now see at a glance whether "舞台を、己のものに"
is a faithful adaptation of "Own the Stage" — without speaking Japanese.

This is the kind of thing a developer wouldn't think to add, because they're
focused on whether the data is correct, not whether the UI is useful.

---

## 7. "Just show Sax / Piano / Guitar — no need for the individual variants"

**What you said:**
> "For the copy preview, can you just have product - sax, piano, guitar for
> all the markets, no need to have their variants because the family has the
> same tagline and CTA."

**What it changed:**
The table was showing 5+ rows per market (sax_signature, piano_grand,
piano_upright, piano_digital, guitar_paulie_black…) when every product
within a family shares identical copy. It was visually noisy and implied
a level of variation that doesn't exist. Collapsing to 3 rows — Saxophone,
Piano, Guitar — is both more honest and much easier to scan. It also made
the table consistent with how the pipeline actually thinks about copy:
at the family level, not the product level.

---

## 8. "Make the US backgrounds look like the international tab"

**What you said:**
> "Any way to make the US background look like the other markets as well,
> right now it's too big."

**What it changed:**
The US backgrounds tab was showing up to 4 images per scene in stacked rows,
which made each image take up a large portion of the screen. The international
tab was clean — exactly 3 images side by side, one per scene. Matching that
layout brought visual consistency to the dashboard: both tabs now show the
same 3-column, one-per-scene format. It's a small UI change but it makes
the dashboard feel coherent rather than like two different features bolted
together.

---

## 9. "We only need 16x9 backgrounds"

**What you said:**
> "I ran the backgrounds in the dashboard, it generates the other sizes but
> doesn't need to. We only need the 16x9 backgrounds to be generated."

**What it changed:**
The background generation script was looping over every ratio in `variants.json`
(16x9, 1x1, billboard) and generating a separate Flux image for each. That's
3× the generation time and 3× the ComfyUI queue load — for no benefit, since
After Effects uses the same 16x9 background and scales it for the other formats.
One line added to the script (`if v["ratio"] != "16x9": continue`) cut the
background generation job count by two-thirds. On a 5-product batch that's
the difference between 15 ComfyUI jobs and 5.

This was caught from actually running the pipeline and noticing something
felt wrong — not from reading the code. That's a meaningful quality of
attention.

---

## The Bigger Pattern

Looking across all of these: most of the improvements came from asking
"does this actually make sense in practice?" rather than "does this work
technically?" The pipeline ran correctly before each of these changes.
What you were catching was the gap between code that works and a tool
that's genuinely useful — cleaner UI, tighter scope, honest data, a story
that a reviewer can follow.

That instinct — noticing when something is technically correct but practically
wrong — is exactly what separates a pipeline built for a demo from one built
for production.
