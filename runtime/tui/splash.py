from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SPLASH_DURATION_SECONDS = 1.5
ASCII_LOGO_PATH = Path("assets/capiforge-icons/capiforge-ascii.txt")
FALLBACK_BRAND = "CapiForge"
SPLASH_HORIZONTAL_PADDING = 4
SPLASH_VERTICAL_PADDING = 4


@dataclass(frozen=True)
class SplashContent:
    mode: str
    lines: tuple[str, ...]


def load_splash_art(*, repo_root: str | Path) -> str:
    logo_path = Path(repo_root) / ASCII_LOGO_PATH
    try:
        return logo_path.read_text(encoding="utf-8")
    except OSError:
        return ""


def build_splash_content(
    *,
    available_width: int,
    available_height: int,
    ascii_art: str,
    fallback_brand: str = FALLBACK_BRAND,
) -> SplashContent:
    ascii_lines = _normalized_ascii_lines(ascii_art)
    if ascii_lines and _fits_available_space(
        available_width=available_width,
        available_height=available_height,
        lines=ascii_lines,
    ):
        return SplashContent(mode="ascii", lines=ascii_lines)
    return SplashContent(
        mode="text",
        lines=_build_fallback_lines(
            available_width=available_width,
            available_height=available_height,
            fallback_brand=fallback_brand,
        ),
    )


def _normalized_ascii_lines(ascii_art: str) -> tuple[str, ...]:
    if not ascii_art.strip():
        return ()
    return tuple(line.rstrip() for line in ascii_art.splitlines() if line.strip())


def _fits_available_space(*, available_width: int, available_height: int, lines: tuple[str, ...]) -> bool:
    required_width = max(len(line) for line in lines) + SPLASH_HORIZONTAL_PADDING
    required_height = len(lines) + SPLASH_VERTICAL_PADDING
    return available_width >= required_width and available_height >= required_height


def _build_fallback_lines(*, available_width: int, available_height: int, fallback_brand: str) -> tuple[str, ...]:
    if available_height <= 0:
        return ()
    if available_width <= 0:
        return ("",)
    return (fallback_brand[:available_width],)
