"""Automated Submission Packaging Script for NetCoop AI.

Packages the clean, verified source code, documentation, and test suites into a
submission-ready ZIP file (NetCoop_AI_Submission.zip) while strictly omitting:
- .git metadata
- __pycache__ bytecode
- .pytest_cache
- Virtual environment directories
- Temporary session files and caches
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ZIP = PROJECT_ROOT / "NetCoop_AI_Submission.zip"

EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "env",
    ".session_store",
    ".idea",
    ".vscode",
    "node_modules",
    ".next",
    "dist",
    "build",
    ".gemini"
}

EXCLUDED_FILES = {
    "NetCoop_AI_Submission.zip",
    "netcoop_ai_demo.mp4",
    ".DS_Store",
    "Thumbs.db"
}

EXCLUDED_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".log",
    ".tsbuildinfo"
}


def should_exclude(file_path: Path) -> bool:
    rel = file_path.relative_to(PROJECT_ROOT)
    # Check parts
    for part in rel.parts:
        if part in EXCLUDED_DIRS:
            return True
    if file_path.name in EXCLUDED_FILES:
        return True
    if file_path.suffix in EXCLUDED_EXTENSIONS:
        return True
    # Exclude legacy Next.js app directories
    if any(rel.parts[0] == d for d in ("app", "components", "lib", "prisma")):
        return True
    return False


def build_submission_zip() -> None:
    print(f"\n=======================================================")
    print(f" NETCOOP AI — SUBMISSION PACKAGING HARNESS")
    print(f"=======================================================\n")
    print(f"Project Root: {PROJECT_ROOT}")
    print(f"Target Archive: {OUTPUT_ZIP.name}")

    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()

    included_count = 0
    with zipfile.ZipFile(OUTPUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
        for root, dirs, files in os.walk(PROJECT_ROOT):
            # Prune excluded directories in-place
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and d not in ("app", "components", "lib", "prisma")]
            for file in files:
                full_path = Path(root) / file
                if not should_exclude(full_path):
                    arcname = full_path.relative_to(PROJECT_ROOT)
                    zipf.write(full_path, arcname=arcname)
                    included_count += 1

    size_mb = OUTPUT_ZIP.stat().st_size / (1024 * 1024)
    print(f"\n[OK] Package created successfully!")
    print(f"Total files packaged: {included_count}")
    print(f"Archive file size:   {size_mb:.2f} MB")
    print(f"Saved to:            {OUTPUT_ZIP}\n")


if __name__ == "__main__":
    build_submission_zip()
