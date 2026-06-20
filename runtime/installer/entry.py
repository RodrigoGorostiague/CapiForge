from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    force_cli = "--no-tui-ui" in args
    if not force_cli and sys.stdin.isatty() and sys.stdout.isatty():
        from runtime.installer.tui import main as tui_main

        return tui_main(args)
    from runtime.installer.core import main as core_main

    return core_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
