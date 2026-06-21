from __future__ import annotations


def web_deps_install_hint(*, checkout_hint: str | None = None) -> str:
    checkout = checkout_hint or "<repo>"
    return (
        "Web dependencies are not installed in this capiforge environment.\n"
        "\n"
        "Developer checkout (repo .venv):\n"
        "  uv sync --extra web\n"
        "  uv run capiforge web --refresh 15\n"
        "\n"
        "Global capiforge (~/.local/bin/capiforge via capinstall / uv tool):\n"
        f"  ./capinstall update\n"
        f"  uv tool install --reinstall --editable '.[web]' --directory {checkout}\n"
        "\n"
        "Note: `uv sync --extra web` only updates the repo .venv; it does not change ~/.local/bin/capiforge."
    )
