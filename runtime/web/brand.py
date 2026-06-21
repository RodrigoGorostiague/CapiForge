from __future__ import annotations

from pathlib import Path

from runtime.paths import asset_path

LOGO_FILENAME = "capiforge_logo_original_transparente.png"
ICONS_RELATIVE = Path("assets/capiforge-icons")
SPLASH_MIN_MS = 1500
SPLASH_MAX_MS = 5000


def brand_icons_dir() -> Path | None:
    path = asset_path(ICONS_RELATIVE)
    return path if path.is_dir() else None


def brand_logo_url() -> str:
    return f"/brand/{LOGO_FILENAME}"
