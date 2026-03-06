"""
config.py — Yosuki Pipeline Configuration
==========================================
This is the ONE file that knows about your specific machine setup.
Everything else imports from here — no paths live anywhere else.

📝 HOW TO SET UP ON A NEW MACHINE:
1. Copy `.env.example` to `.env`
2. Fill in YOUR machine paths in `.env`
3. That's it — all scripts read from here automatically

The .env file is gitignored so your personal paths and API keys
are never uploaded to GitHub.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file so ANTHROPIC_API_KEY and others are available via os.getenv()
load_dotenv()


# ─────────────────────────────────────────────
# DIRECTORIES
# ─────────────────────────────────────────────

# Root of this pipeline repo (the folder containing this file)
BASE_DIR = Path(__file__).parent

# Where the original Yosuki asset bundle lives (read-only — we never move these)
ASSET_BUNDLE_DIR = Path(os.getenv("ASSET_BUNDLE_DIR", "F:/Adobe_FDE Take-Home/Assets/fde_asset_bundle"))

# Where rembg-processed transparent cutouts are saved
PRODUCT_CUTOUTS_DIR = BASE_DIR / "assets" / "product_cutouts"

# Output folders (all auto-created by the pipeline)
OUTPUT_DIR        = BASE_DIR / "output"
BACKGROUNDS_DIR   = OUTPUT_DIR / "backgrounds"    # ComfyUI-generated scene images
PROJECTS_DIR      = OUTPUT_DIR / "projects"       # Populated .aep copies
RENDERS_DIR       = OUTPUT_DIR / "renders"        # Raw .mp4 files from aerender
DELIVERY_DIR      = OUTPUT_DIR / "delivery"       # Final organized output
LOGS_DIR          = OUTPUT_DIR / "logs"

# Source template and script folders
AE_TEMPLATES_DIR      = BASE_DIR / "ae_templates"
EXTENDSCRIPT_DIR      = BASE_DIR / "extendscript"
COMFYUI_WORKFLOWS_DIR = BASE_DIR / "comfyui_workflows"


# ─────────────────────────────────────────────
# KEY FILES
# ─────────────────────────────────────────────

BRIEF_JSON        = BASE_DIR / "brief.json"          # The creative brief you edit per campaign
VARIANTS_JSON     = OUTPUT_DIR / "variants.json"     # Auto-generated, tracks all 112 render states
COPY_PREVIEW_JSON = OUTPUT_DIR / "copy_preview.json" # Staging file for copy review before applying


# ─────────────────────────────────────────────
# API KEYS (loaded from .env — never hardcode these)
# ─────────────────────────────────────────────

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Google Drive: set this to your target Drive folder ID to enable upload.
# Leave blank ("") to skip Drive upload and use local delivery only.
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")


# ─────────────────────────────────────────────
# EXTERNAL TOOLS
# ─────────────────────────────────────────────

# Path to aerender.exe — the command-line renderer for After Effects
AERENDER_PATH = os.getenv(
    "AERENDER_PATH",
    r"C:\Program Files\Adobe\Adobe After Effects 2026\Support Files\aerender.exe"
)

# ComfyUI local server URL
COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188")

# Where ComfyUI Desktop saves generated images on your machine
COMFYUI_OUTPUT_DIR = Path(os.getenv("COMFYUI_OUTPUT_DIR", "G:/ComfyUI/output"))

# ─────────────────────────────────────────────
# CINEMA 4D
# ─────────────────────────────────────────────

# Path to Cinema 4D executable
C4D_EXE = Path(os.getenv(
    "C4D_EXE",
    r"C:\Program Files\Maxon Cinema 4D 2026\Cinema 4D.exe"
))

# Where C4D saves greyscale renders used as ControlNet inputs
C4D_RENDERS_DIR = Path(os.getenv("C4D_RENDERS_DIR", "F:/Adobe_FDE Take-Home/Assets/renders"))

# C4D render paths per scene — auto-finds the newest matching file in C4D_RENDERS_DIR.
# C4D appends an incrementing number to each render (_001, _002, etc.).
# This way re-rendering never requires updating .env.
def _latest_render(pattern: str) -> Path:
    matches = sorted(C4D_RENDERS_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else C4D_RENDERS_DIR / pattern.replace("*", "001")

C4D_RENDERS = {
    "sax":    _latest_render("saxophone_model1_16x9_*.png"),
    "piano":  _latest_render("piano_grand_16x9_*.png"),
    "guitar": _latest_render("guitar_16x9_*.png"),
}

# C4D Python scripts launched by the dashboard's "Step 1" buttons
C4D_SCRIPTS = {
    "Saxophone": Path(os.getenv("C4D_SCRIPT_SAX",   r"F:\Adobe_FDE Take-Home\Assets\Python_scripts\yosuki_saxophone_16x9.py")),
    "Piano":     Path(os.getenv("C4D_SCRIPT_PIANO", r"F:\Adobe_FDE Take-Home\Assets\Python_scripts\yosuki_piano_16x9.py")),
    "Guitar":    Path(os.getenv("C4D_SCRIPT_GUITAR",r"F:\Adobe_FDE Take-Home\Assets\Python_scripts\yosuki_guitar_16x9.py")),
    "All":       Path(os.getenv("C4D_SCRIPT_ALL",   r"F:\Adobe_FDE Take-Home\Assets\Python_scripts\yosuki_c4d_pipeline_v3.py")),
}


# ─────────────────────────────────────────────
# CLAUDE MODEL
# ─────────────────────────────────────────────

# Which Claude model to use for copy generation
# claude-opus-4-6 = most creative/capable; claude-haiku-4-5-20251001 = faster/cheaper for testing
CLAUDE_MODEL = "claude-opus-4-6"


# ─────────────────────────────────────────────
# RENDER SETTINGS
# ─────────────────────────────────────────────

# The Output Module Template name in After Effects
# Make sure this template exists in your AE preferences
AE_OUTPUT_MODULE = "H.264 - Match Render Settings - 15 Mbps"

# Name of the main composition inside every .aep template
# This must match exactly what's in your AE template files
AE_MAIN_COMP_NAME = "MAIN_COMP"


# ─────────────────────────────────────────────
# ASPECT RATIO DIMENSIONS (for ComfyUI image generation)
# ─────────────────────────────────────────────

# These are the pixel sizes ComfyUI will generate backgrounds at.
# Billboard is 3× the actual size (2910×750 → scales to 970×250) for sharpness.
RATIO_DIMENSIONS = {
    "billboard_970x250": (2910, 750),   # 3× for crispness
    "16x9":              (1920, 1080),
    "1x1":               (1080, 1080),
}
