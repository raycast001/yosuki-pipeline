"""
logger.py — Terminal output helpers for the Yosuki pipeline
=============================================================
Gives us coloured, emoji-tagged status messages so we can
see exactly what's happening as each script runs.

Usage (in any script):
    from scripts.utils.logger import log
    log.info("Starting background generation...")
    log.ok("Background saved: guitar1_black_16x9.png")
    log.warn("Retrying copy for piano_grand_JP — tagline too long")
    log.error("ComfyUI not responding at http://127.0.0.1:8188")
    log.section("STEP 2 — BACKGROUND GENERATION")
"""

import sys
import io
from datetime import datetime

# Force stdout/stderr to UTF-8 so emoji and Japanese characters print correctly
# on Windows terminals that default to cp1252
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class Logger:
    """Simple coloured terminal logger. No external dependencies needed."""

    # ANSI colour codes — these make text coloured in the terminal
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    CYAN   = "\033[96m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    GREY   = "\033[90m"
    WHITE  = "\033[97m"

    def _timestamp(self):
        """Returns current time as HH:MM:SS for log prefixes."""
        return datetime.now().strftime("%H:%M:%S")

    def info(self, message: str):
        """General information — blue/cyan."""
        print(f"{self.CYAN}[{self._timestamp()}] ℹ  {message}{self.RESET}")

    def ok(self, message: str):
        """Success — green."""
        print(f"{self.GREEN}[{self._timestamp()}] ✓  {message}{self.RESET}")

    def warn(self, message: str):
        """Warning — yellow. Pipeline continues."""
        print(f"{self.YELLOW}[{self._timestamp()}] ⚠  {message}{self.RESET}", file=sys.stderr)

    def error(self, message: str):
        """Error — red. Usually fatal."""
        print(f"{self.RED}[{self._timestamp()}] ✗  {message}{self.RESET}", file=sys.stderr)

    def section(self, title: str):
        """Big visual divider for each pipeline step."""
        bar = "─" * 60
        print(f"\n{self.BOLD}{self.WHITE}{bar}")
        print(f"  {title}")
        print(f"{bar}{self.RESET}\n")

    def progress(self, current: int, total: int, label: str):
        """Shows progress like: [3/27] Generating: guitar1_black_16x9"""
        print(f"{self.GREY}[{current}/{total}]{self.RESET} {label}")


# Single shared instance — import this everywhere
log = Logger()
