"""
05_deliver.py — Organize renders into delivery folders + upload to Google Drive
===============================================================================
PURPOSE:
  Takes raw renders from output/renders/ and organizes them into a clean
  delivery structure at output/delivery/{MARKET}/{product_category}/{ratio}/

  Optionally uploads to Google Drive if GOOGLE_DRIVE_FOLDER_ID is set in .env

LOCAL OUTPUT STRUCTURE:
  output/delivery/
  ├── US/
  │   ├── saxophone/
  │   │   ├── billboard/    sax_signature_US_billboard.mp4
  │   │   ├── 16x9/         sax_signature_US_16x9.mp4
  │   │   └── 1x1/          sax_signature_US_1x1.mp4
  │   ├── pianos/
  │   │   └── piano_grand/
  │   │       ├── billboard/
  │   │       └── 16x9/
  │   └── guitars/
  │       └── guitar_paulie_black/
  │           ├── billboard/
  │           ├── 16x9/
  │           └── 1x1/
  ├── JP/ ...
  ├── DE/ ...
  └── BR/ ...

GOOGLE DRIVE SETUP (one-time):
  1. Go to https://console.cloud.google.com
  2. Create a new project → Enable "Google Drive API"
  3. Create OAuth credentials → Download as credentials.json
  4. Put credentials.json in this pipeline folder (it's gitignored)
  5. Set GOOGLE_DRIVE_FOLDER_ID in your .env file (the ID of your target Drive folder)
  6. First run opens a browser for Google login — token.json is saved for future runs

RUN:
  python scripts/05_deliver.py
  python scripts/05_deliver.py --no-drive    # Skip Drive upload
  python scripts/05_deliver.py --market US   # Only deliver US renders
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import os
os.environ["PYTHONIOENCODING"] = "utf-8"


from config import (
    DELIVERY_DIR,
    GOOGLE_DRIVE_FOLDER_ID,
    RENDERS_DIR,
    VARIANTS_JSON,
)
from scripts.utils.logger import log


# ─────────────────────────────────────────────
# PRODUCT CATEGORY MAP
# Maps product_id prefix → category folder name used in delivery structure
# ─────────────────────────────────────────────
def get_category(product_id: str) -> str:
    """Returns the top-level category folder for this product."""
    if product_id.startswith("sax"):
        return "saxophone"
    elif product_id.startswith("piano"):
        return "pianos"
    elif product_id.startswith("guitar"):
        return "guitars"
    return "other"


def get_delivery_path(variant: dict) -> Path:
    """
    Builds the local delivery path for a variant.
    Example: output/delivery/US/guitars/guitar_paulie_black/16x9/
    """
    market   = variant["market"]
    category = get_category(variant["product_id"])
    product  = variant["product_id"]

    # Clean up the ratio name for use as a folder
    # billboard_970x250 → billboard
    ratio_folder = variant["ratio"].replace("_970x250", "").replace("16x9", "16x9").replace("1x1", "1x1")
    if "billboard" in ratio_folder:
        ratio_folder = "billboard"

    return DELIVERY_DIR / market / category / product / ratio_folder


def deliver_locally(variants: list[dict], market_filter: str | None) -> tuple[int, int]:
    """
    Copies rendered .mp4 files into the organized delivery folder structure.
    Returns (success_count, failed_count).
    """
    success = 0
    failed  = 0

    for v in variants:
        if market_filter and v["market"] != market_filter:
            continue

        # Process both "rendered" (new) and "delivered" (re-run) variants
        if v.get("status") not in ("rendered", "delivered"):
            continue

        vid = v["variant_id"]
        source = RENDERS_DIR / f"{vid}.mp4"

        if not source.exists():
            log.warn(f"Render file not found — skipping: {source.name}")
            failed += 1
            continue

        # Build destination path
        dest_dir  = get_delivery_path(v)
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Clean filename: {product_id}_{market}_{ratio}.mp4
        ratio_clean = v["ratio"].replace("_970x250", "")
        dest_name = f"{v['product_id']}_{v['market']}_{ratio_clean}.mp4"
        dest_path = dest_dir / dest_name

        shutil.copy2(source, dest_path)
        log.ok(f"  Copied: {dest_path.relative_to(DELIVERY_DIR)}")
        v["status"] = "delivered"
        success += 1

    return success, failed


# ─────────────────────────────────────────────
# GOOGLE DRIVE UPLOAD
# ─────────────────────────────────────────────

def get_drive_service():
    """
    Authenticates with Google Drive API and returns a service object.
    On first run, opens a browser for OAuth login.
    After that, uses the saved token.json.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        log.error("Google API libraries not installed.")
        log.error("Run: pip install google-api-python-client google-auth-oauthlib")
        return None

    SCOPES = ["https://www.googleapis.com/auth/drive.file"]
    creds = None
    token_path = Path("token.json")
    creds_path = Path("credentials.json")

    if not creds_path.exists():
        log.error("credentials.json not found.")
        log.error("Download it from Google Cloud Console → APIs & Services → Credentials")
        return None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as token:
            token.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


def get_or_create_folder(service, name: str, parent_id: str) -> str:
    """
    Gets a Drive folder by name under parent_id, creating it if it doesn't exist.
    Returns the folder ID.
    """
    # Search for existing folder
    query = (
        f"name='{name}' and "
        f"'{parent_id}' in parents and "
        f"mimeType='application/vnd.google-apps.folder' and "
        f"trashed=false"
    )
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    # Create it
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def upload_to_drive(service, local_path: Path, folder_id: str, filename: str) -> bool:
    """Uploads a single file to Drive. Replaces existing file if already there."""
    try:
        from googleapiclient.http import MediaFileUpload

        media = MediaFileUpload(str(local_path), mimetype="video/mp4", resumable=True)

        # Check if file already exists in Drive
        query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
        existing = service.files().list(q=query, fields="files(id)").execute().get("files", [])

        if existing:
            # Update the existing file's content instead of uploading a duplicate
            file_id = existing[0]["id"]
            service.files().update(fileId=file_id, media_body=media).execute()
            log.ok(f"  Updated in Drive: {filename}")
        else:
            # New file — create it
            metadata = {"name": filename, "parents": [folder_id]}
            service.files().create(body=metadata, media_body=media, fields="id").execute()
            log.ok(f"  Uploaded to Drive: {filename}")

        return True
    except Exception as e:
        log.error(f"  Drive upload failed for {filename}: {e}")
        return False


def deliver_to_drive(service, variants: list[dict], root_folder_id: str, market_filter: str | None):
    """
    Mirrors the local delivery folder structure in Google Drive.
    Creates folders as needed and uploads each MP4.
    """
    log.info("Uploading to Google Drive...")
    drive_success = 0
    drive_failed  = 0

    # Cache folder IDs to avoid repeated API calls
    folder_cache = {}

    def get_folder(path_parts: list[str]) -> str:
        """Recursively gets/creates nested Drive folders, using cache."""
        key = "/".join(path_parts)
        if key in folder_cache:
            return folder_cache[key]

        parent_id = root_folder_id
        for part in path_parts:
            folder_id = get_or_create_folder(service, part, parent_id)
            parent_id = folder_id

        folder_cache[key] = parent_id
        return parent_id

    for v in variants:
        if market_filter and v["market"] != market_filter:
            continue

        if v.get("status") != "delivered":
            continue

        vid = v["variant_id"]
        ratio_clean = v["ratio"].replace("_970x250", "")
        filename = f"{v['product_id']}_{v['market']}_{ratio_clean}.mp4"
        local_path = get_delivery_path(v) / filename

        if not local_path.exists():
            log.warn(f"  Delivery file not found: {filename}")
            drive_failed += 1
            continue

        # Build the Drive folder path
        category = get_category(v["product_id"])
        ratio_folder = "billboard" if "billboard" in v["ratio"] else v["ratio"]
        folder_parts = [v["market"], category, v["product_id"], ratio_folder]

        target_folder_id = get_folder(folder_parts)

        log.info(f"  Uploading: {filename}")
        ok = upload_to_drive(service, local_path, target_folder_id, filename)
        if ok:
            drive_success += 1
        else:
            drive_failed += 1

    log.ok(f"Drive upload: {drive_success} uploaded, {drive_failed} failed")


def run(market_filter: str | None = None, skip_drive: bool = False):
    log.section("STEP 5 — DELIVERY")

    # ── Load variants.json ─────────────────────────────────────────
    if not VARIANTS_JSON.exists():
        log.error("variants.json not found.")
        sys.exit(1)

    with open(VARIANTS_JSON, encoding="utf-8") as f:
        variants = json.load(f)

    # ── Local delivery ─────────────────────────────────────────────
    log.info("Organizing files locally...")
    success, failed = deliver_locally(variants, market_filter)
    print()
    log.ok(f"Local delivery: {success} files organized, {failed} failed")
    log.info(f"Output: {DELIVERY_DIR}")

    # Save updated statuses
    with open(VARIANTS_JSON, "w", encoding="utf-8") as f:
        json.dump(variants, f, ensure_ascii=False, indent=2)

    # ── Google Drive upload ────────────────────────────────────────
    if skip_drive:
        log.info("Drive upload skipped (--no-drive flag).")
        return

    if not GOOGLE_DRIVE_FOLDER_ID:
        log.info("GOOGLE_DRIVE_FOLDER_ID not set in .env — skipping Drive upload.")
        log.info("To enable Drive upload: add GOOGLE_DRIVE_FOLDER_ID to your .env file.")
        return

    print()
    service = get_drive_service()
    if service:
        deliver_to_drive(service, variants, GOOGLE_DRIVE_FOLDER_ID, market_filter)
    else:
        log.warn("Could not connect to Google Drive — local delivery only.")

    print()
    log.ok("Pipeline complete! Check output/delivery/ for your files.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Organize and deliver rendered files.")
    parser.add_argument("--market",   type=str,  default=None, help="Deliver a single market only.")
    parser.add_argument("--no-drive", action="store_true",     help="Skip Google Drive upload.")
    args = parser.parse_args()
    run(market_filter=args.market, skip_drive=args.no_drive)
