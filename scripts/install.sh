#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CORE="${REPO_ROOT}/scripts/installer_core.py"
TUI_MODULE="runtime.installer.tui"

usage() {
    cat <<'EOF'
Usage: capinstall [command] [options]

Interactive installer wizard for CapiForge (default when run in a TTY).

Commands:
  install       Install capiforge, bootstrap repo, and configure selected integrations
  update        Refresh installed binary, bootstrap, and registered integrations
  verify        Check capiforge binary, bootstrap, and integration configs
  uninstall     Remove capiforge binary, integration entries, and installer state
  setup         Alias for install

Options:
  --cursor              Configure Cursor MCP integration
  --opencode            Configure OpenCode MCP integration
  --targets LIST        Comma-separated targets: cursor,opencode
  --repo-root PATH      Repository to bootstrap (default: git root or checkout)
  --node-home PATH      Node home (default: <repo-root>/.capiforge/node)
  --no-tui-extra        Install without the optional textual extra
  --backend BACKEND     Installation backend: auto (default), uv, pipx
  --remove-bootstrap    Uninstall also deletes .capiforge bootstrap data
  --non-interactive     Disable interactive bootstrap lock recovery
  --interactive         Allow interactive bootstrap lock recovery
  --no-tui-ui           Force CLI mode instead of Textual wizard
  --json                Emit machine-readable JSON from installer core

Environment:
  CAPIFORGE_INSTALL_UV=1   Bootstrap uv automatically when it is missing

Examples:
  ./capinstall
  ./capinstall install --cursor --opencode --non-interactive
  ./capinstall update --non-interactive
  ./capinstall uninstall --remove-bootstrap --non-interactive
  ./capinstall --no-tui-ui verify --json
EOF
}

log() {
    printf 'capiforge-install: %s\n' "$*" >&2
}

die() {
    printf 'capiforge-install: error: %s\n' "$*" >&2
    exit 1
}

launch_tui() {
    export PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
    if command -v uv >/dev/null 2>&1; then
        exec uv run --directory "${REPO_ROOT}" python -m "${TUI_MODULE}" "$@"
    fi
    if ! python3 -c "import textual" >/dev/null 2>&1; then
        die "Textual is required for the installer TUI. Install with: uv tool install --editable '.[tui]' --directory '${REPO_ROOT}' or rerun with --no-tui-ui."
    fi
    exec python3 -m "${TUI_MODULE}" "$@"
}

invoke_core() {
    local command="$1"
    shift
    local -a args=(--checkout-root "${REPO_ROOT}")
    if [[ "${CAPIFORGE_INSTALL_UV:-0}" == "1" ]]; then
        args+=(--bootstrap-uv)
    fi
    export PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
    exec python3 "${CORE}" "${command}" "${args[@]}" "$@"
}

parse_and_dispatch() {
    local -a passthrough=()
    local command=""
    local force_cli=0

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help)
                usage
                exit 0
                ;;
            --no-tui-ui)
                force_cli=1
                shift
                ;;
            install|update|verify|uninstall|setup)
                if [[ -z "${command}" ]]; then
                    command="$1"
                else
                    passthrough+=("$1")
                fi
                shift
                ;;
            *)
                passthrough+=("$1")
                shift
                ;;
        esac
    done

    if [[ -z "${command}" ]]; then
        if [[ "${force_cli}" -eq 0 ]] && [[ -t 0 && -t 1 ]]; then
            launch_tui
        fi
        command="install"
    fi

    if [[ "${command}" == "setup" ]]; then
        command="install"
    fi

    invoke_core "${command}" "${passthrough[@]}"
}

parse_and_dispatch "$@"
