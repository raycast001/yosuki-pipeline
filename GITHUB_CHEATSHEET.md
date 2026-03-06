# GitHub Page Cheat Sheet
## How to read your repo at github.com/raycast001/yosuki-pipeline

---

## The Page at a Glance

When you open the repo, here's what you're looking at:

```
┌─────────────────────────────────────────────────────────┐
│  raycast001 / yosuki-pipeline          ★ Star  🍴 Fork  │
│  Public                                                  │
├─────────────────────────────────────────────────────────┤
│  < > Code   Issues   Pull requests   Actions   ...      │  ← tabs
├─────────────────────────────────────────────────────────┤
│  Branch: master ▼    [1 commit]   [Contributors]        │
│                                                         │
│  📁 ae_templates/                                       │
│  📁 comfyui_workflows/                                  │  ← file browser
│  📁 extendscript/                                       │
│  📁 output/                                             │
│  📁 scripts/                                            │
│  📄 .env.example                                        │
│  📄 .gitignore                                          │
│  📄 brief.json                                          │
│  📄 config.py                                           │
│  📄 dashboard.py                                        │
│  📄 README.md                                           │
│  ...                                                    │
├─────────────────────────────────────────────────────────┤
│  README.md                                              │  ← auto-rendered below
│  [your README content displayed here]                   │
└─────────────────────────────────────────────────────────┘
```

---

## The Key Numbers (top-right area of the file browser)

| What you see | What it means |
|---|---|
| **1 commit** | The full history of changes. We have one — the initial commit with everything. Click it to see what was included. |
| **master** (branch dropdown) | The current branch you're viewing. `master` is the main/default branch. |
| **2 contributors** | You + Claude (Claude is listed because the commit includes a `Co-Authored-By` line). |
| **86.1% Python, 13.9% JavaScript** | GitHub auto-detects languages. The JS is the ExtendScript files in `extendscript/` (.jsx files). |

---

## The File Browser

Click any folder or file to read it directly on GitHub. A few things worth knowing:

**Why `output/` appears but is mostly empty:**
> The `output/` folder is in the repo because it contains two tracked files:
> `variants.json` and `copy_preview.json`. The render files (MP4s, PNGs, .aep projects)
> are gitignored — too large for git. If someone clicks into `output/` they'll see those two
> JSON files but no renders. That's intentional and correct.

**Why there's no `.env` file:**
> `.env` is gitignored — it contains your machine paths and API key.
> `.env.example` IS visible — that's the public template showing what to fill in.
> Anyone cloning the repo copies `.env.example` → `.env` and fills in their paths.

**The `scripts/archive/` folder:**
> Contains the dev experiments from earlier in the project (test scripts, prototype workflows).
> They're in the repo for transparency — shows the development process — but they're not
> part of the active pipeline.

---

## The Commit

Click **"1 commit"** (or the commit hash next to the file names) to see the full commit.

What you'll see:
- **Commit message:** "Initial commit — Yosuki Find Your Sound pipeline"
- **51 files changed, 11,064 insertions** — all the code added in one go
- A list of every file that was added

**If they ask why there's only one commit:**
> "This was a take-home project built iteratively, but the repo was initialised at the polished,
> final state. In a real production project, you'd see commits for each development stage —
> initial scaffolding, adding ComfyUI integration, adding international markets, etc.
> The single commit represents the delivered state."

---

## The README (auto-displayed at the bottom of the page)

GitHub automatically renders your `README.md` below the file browser.
This is the first thing a reviewer reads. It should cover:
- What the pipeline does
- How to set it up (`.env.example` → `.env`)
- How to run it

**To check what your README currently says:**
Click `README.md` in the file browser, or just scroll down on the main repo page.

---

## What a Reviewer Will Click First

In order of likelihood:

1. **README.md** — the project description. First impression.
2. **`scripts/`** — to see the pipeline scripts in order (00_, 02_, 02a_, etc.)
3. **`output/variants.json`** — to see the 112 variants and their copy in 4 languages
4. **`config.py`** — to see how paths and settings are handled
5. **`brief.json`** — to understand the creative brief structure
6. **`dashboard.py`** — to see how the UI is built
7. **`extendscript/populate_template.jsx`** — to see the AE automation side

---

## Things to Point Out If You're Sharing the Screen

**"You can see the full pipeline order just from the script names:"**
> Click into `scripts/` and show: `00_prep_assets.py` → `02_generate_backgrounds.py`
> → `02a_`, `02b_`, `02c_` → `03_populate_templates.py` → `05_deliver.py`
> The numbering tells the whole story without opening a single file.

**"variants.json shows the pipeline's output state:"**
> Click `output/variants.json` — GitHub renders JSON with syntax highlighting.
> Scroll through a few entries and point out the fields: `variant_id`, `market`,
> `tagline`, `cta`, `status: "rendered"`, `background_path`.
> "This is the pipeline's brain — every variant, its copy in 4 languages, its render status."

**".env.example shows what a new user needs to fill in:"**
> Click `.env.example` — shows all the machine-specific variables with comments.
> "This is the onboarding doc for a new machine. Copy it to .env, fill in your paths, done."

---

## The Language Bar

At the top-right of the file list you'll see a coloured bar:

`█████████████████████  ██`
`86.1% Python           13.9% JavaScript`

**What to say:**
> "86% Python — the pipeline, config, dashboard, all scripts.
> The 13.9% JavaScript is actually ExtendScript — Adobe's scripting language for After Effects,
> which uses a JavaScript-based syntax. It's the bridge between Python and After Effects."

---

## Quick Reference: What's Gitignored (not visible on GitHub)

| Not on GitHub | Why |
|---|---|
| `.env` | Contains your API key and machine paths — secret |
| `output/renders/` | MP4 render files — too large for git |
| `output/backgrounds/` | ComfyUI-generated PNGs — too large |
| `output/projects/` | Populated .aep copies — too large |
| `output/logs/` | Log files — not useful in the repo |
| `assets/product_cutouts/` | rembg-processed PNGs — auto-generated |
| `__pycache__/` | Python compiled files — auto-generated |

**What IS on GitHub:**
- All the source code
- `output/variants.json` — the pipeline's 112-variant state
- `output/copy_preview.json` — the copy in all 4 languages
- `.env.example` — the setup template
- All documentation (README, PRESENTATION guides, etc.)
