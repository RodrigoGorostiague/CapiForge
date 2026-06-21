from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Sequence

from runtime.paths import default_repo_root
from runtime.web.context import WebContext

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8741
DEFAULT_REFRESH_SECONDS = 0


def build_parser(*, prog: str = "capiforge web") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--repo-root", default=str(default_repo_root()))
    parser.add_argument("--node-home")
    parser.add_argument("--as-of")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-open", action="store_true", help="Do not open a browser tab")
    parser.add_argument(
        "--refresh",
        type=int,
        default=DEFAULT_REFRESH_SECONDS,
        choices=(0, 15, 30, 60),
        help="Polling fallback interval in seconds for sync verification (0=off; realtime is primary)",
    )
    parser.add_argument(
        "--no-realtime",
        action="store_true",
        help="Disable SSE realtime updates (useful for tests/CI)",
    )
    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = "capiforge web") -> int:
    args = build_parser(prog=prog).parse_args(list(argv) if argv is not None else None)
    try:
        import uvicorn
    except ImportError:
        from runtime.web.deps import web_deps_install_hint

        print(web_deps_install_hint(checkout_hint=str(Path(args.repo_root).resolve())), file=sys.stderr)
        return 1

    from runtime.web.app import create_app

    node_home = Path(args.node_home) if args.node_home else None
    ctx = WebContext(
        repo_root=Path(args.repo_root),
        node_home=node_home,
        as_of=args.as_of,
        refresh_seconds=args.refresh,
        realtime_enabled=not args.no_realtime,
    )
    app = create_app(ctx)
    url = f"http://{args.host}:{args.port}/"

    if not args.no_open:

        def _open_browser() -> None:
            time.sleep(0.6)
            webbrowser.open(url)

        threading.Thread(target=_open_browser, daemon=True).start()

    print(f"CapiForge web UI at {url}", file=sys.stderr)
    print("Press Ctrl+C to stop.", file=sys.stderr)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0
