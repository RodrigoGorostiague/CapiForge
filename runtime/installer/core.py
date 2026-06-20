from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from runtime.paths import dev_repo_root, schema_path, share_root, system_share_installed

DEFAULT_CHECKOUT_ROOT = dev_repo_root()

from runtime.installer.state import (
    InstallerState,
    IntegrationPaths,
    clear_state,
    default_integration_paths,
    detect_backend,
    detect_capiforge_bin,
    detect_existing_state,
    load_state,
    save_state,
)
from runtime.installer.integration_config import (
    integration_present,
    remove_cursor_skills_artifacts,
    remove_opencode_automation_artifact,
    remove_cursor_config,
    remove_opencode_config,
    write_cursor_skills_artifacts,
    write_opencode_automation_artifact,
    verify_cursor_config,
    verify_cursor_skills,
    verify_opencode_config,
    write_cursor_config,
    write_opencode_config,
)

PACKAGE_NAME = "capiforge"
MIN_PYTHON = (3, 11)
UV_INSTALL_URL = "https://astral.sh/uv/install.sh"


@dataclass
class InstallOptions:
    checkout_root: Path
    repo_root: Path | None = None
    node_home: Path | None = None
    targets: list[str] = field(default_factory=list)
    backend: str = "auto"
    install_tui_extra: bool = True
    bootstrap_interactive: bool = False
    bootstrap_uv: bool = False
    reinstall: bool = False

    def resolved_repo_root(self) -> Path:
        if self.repo_root is not None:
            return self.repo_root.resolve()
        git_root = _git_root(self.checkout_root)
        return (git_root or self.checkout_root).resolve()

    def resolved_node_home(self, repo_root: Path) -> Path:
        if self.node_home is not None:
            return self.node_home.resolve()
        return (repo_root / ".capiforge" / "node").resolve()

    def package_spec(self) -> str:
        return "."


class InstallerError(RuntimeError):
    pass


def _git_root(path: Path) -> Path | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return Path(value) if value else None


def _run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=merged_env,
        check=False,
        capture_output=True,
        text=True,
    )


def check_python() -> str:
    python_bin = shutil.which("python3") or shutil.which("python")
    if not python_bin:
        raise InstallerError("Python 3.11+ is required but python3 was not found in PATH.")
    completed = _run([python_bin, "-c", "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)"])
    if completed.returncode != 0:
        raise InstallerError(f"Python 3.11+ is required; found {_run([python_bin, '--version']).stdout.strip()}.")
    return python_bin


def ensure_uv(*, bootstrap: bool) -> None:
    if shutil.which("uv"):
        return
    if not bootstrap and os.environ.get("CAPIFORGE_INSTALL_UV") != "1":
        raise InstallerError("uv is not installed. Install uv manually or set CAPIFORGE_INSTALL_UV=1.")
    completed = _run(["bash", "-lc", f"curl -LsSf {UV_INSTALL_URL} | sh"])
    if completed.returncode != 0:
        raise InstallerError(completed.stderr.strip() or "failed to bootstrap uv")
    local_bin = Path.home() / ".local" / "bin"
    if local_bin.exists() and str(local_bin) not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{local_bin}{os.pathsep}{os.environ.get('PATH', '')}"
    if not shutil.which("uv"):
        raise InstallerError("uv bootstrap completed but uv is still not in PATH.")


def resolve_backend(options: InstallOptions) -> str:
    backend = options.backend
    if backend == "deb":
        return "deb" if detect_system_package() else "auto"
    if backend != "auto":
        if backend == "uv":
            ensure_uv(bootstrap=options.bootstrap_uv)
        elif backend == "pipx" and not shutil.which("pipx"):
            raise InstallerError("pipx backend requested but pipx was not found in PATH.")
        return backend
    if shutil.which("uv"):
        return "uv"
    if shutil.which("pipx"):
        return "pipx"
    ensure_uv(bootstrap=options.bootstrap_uv)
    return "uv"


def detect_system_package() -> bool:
    capiforge_bin = detect_capiforge_bin()
    if not capiforge_bin:
        return False
    completed = _run([capiforge_bin, "--version"])
    if completed.returncode != 0 or not completed.stdout.strip():
        return False
    return system_share_installed()


def install_binary(options: InstallOptions) -> tuple[str, str]:
    if detect_system_package():
        capiforge_bin = detect_capiforge_bin()
        if not capiforge_bin:
            raise InstallerError("system capiforge package detected but binary is not in PATH")
        return capiforge_bin, "deb"

    check_python()
    backend = resolve_backend(options)
    spec = options.package_spec()
    checkout = options.checkout_root.resolve()
    if backend == "uv":
        command = ["uv", "tool", "install", "--editable", spec, "--directory", str(checkout)]
        if options.reinstall:
            command.insert(3, "--reinstall")
    elif backend == "pipx":
        if options.reinstall:
            _run(["pipx", "reinstall", PACKAGE_NAME])
        command = ["pipx", "install", "--force", "--editable", str(checkout)]
    else:
        raise InstallerError(f"unsupported backend: {backend}")

    completed = _run(command)
    if completed.returncode != 0:
        raise InstallerError(completed.stderr.strip() or completed.stdout.strip() or "binary install failed")

    capiforge_bin = detect_capiforge_bin()
    if not capiforge_bin:
        local_bin = Path.home() / ".local" / "bin"
        raise InstallerError(f"capiforge installed but not found in PATH; add {local_bin} to PATH.")
    return capiforge_bin, backend


def _bootstrap_args(options: InstallOptions, repo_root: Path, node_home: Path) -> list[str]:
    args = ["--repo-root", str(repo_root), "--node-home", str(node_home)]
    if not options.bootstrap_interactive:
        args.append("--non-interactive")
    return args


def bootstrap_repo(*, capiforge_bin: str, options: InstallOptions, repo_root: Path, node_home: Path) -> dict:
    for command in ("init", "adopt"):
        completed = _run([capiforge_bin, command, *_bootstrap_args(options, repo_root, node_home)])
        if completed.returncode != 0:
            raise InstallerError(completed.stderr.strip() or f"capiforge {command} failed")

    completed = _run([capiforge_bin, "status", *_bootstrap_args(options, repo_root, node_home)])
    if completed.returncode != 0:
        raise InstallerError(completed.stderr.strip() or "capiforge status failed")
    payload = json.loads(completed.stdout)
    if payload.get("data", {}).get("bootstrap_state") != "adopted":
        raise InstallerError(f"expected adopted bootstrap state; got {payload.get('data', {}).get('bootstrap_state')}")
    return payload


def write_integrations(
    *,
    capiforge_bin: str,
    checkout_root: Path,
    repo_root: Path,
    node_home: Path,
    targets: list[str],
    integration_paths: IntegrationPaths,
) -> IntegrationPaths:
    paths = IntegrationPaths(
        cursor_global=integration_paths.cursor_global,
        cursor_project=integration_paths.cursor_project,
        opencode=integration_paths.opencode,
    )
    if "cursor" in targets:
        cursor_global = Path(paths.cursor_global or default_integration_paths(repo_root=repo_root).cursor_global or "")
        cursor_project = Path(paths.cursor_project or default_integration_paths(repo_root=repo_root).cursor_project or "")
        write_cursor_config(
            config_path=cursor_global,
            capiforge_bin=capiforge_bin,
            repo_root=str(repo_root),
            node_home=str(node_home),
        )
        write_cursor_config(
            config_path=cursor_project,
            capiforge_bin=capiforge_bin,
            repo_root=str(repo_root),
            node_home=str(node_home),
        )
        paths.cursor_global = str(cursor_global)
        paths.cursor_project = str(cursor_project)
        write_cursor_skills_artifacts(repo_root=str(repo_root))
    if "opencode" in targets:
        opencode_path = Path(paths.opencode or default_integration_paths(repo_root=repo_root).opencode or "")
        write_opencode_config(
            config_path=opencode_path,
            capiforge_bin=capiforge_bin,
            repo_root=str(repo_root),
            node_home=str(node_home),
        )
        write_opencode_automation_artifact(config_path=opencode_path, repo_root=str(checkout_root))
        paths.opencode = str(opencode_path)
    return paths


def remove_integrations(state: InstallerState) -> list[str]:
    removed: list[str] = []
    paths = state.integration_paths
    if paths.cursor_global:
        if remove_cursor_config(config_path=Path(paths.cursor_global)):
            removed.append(paths.cursor_global)
    if paths.cursor_project:
        if remove_cursor_config(config_path=Path(paths.cursor_project)):
            removed.append(paths.cursor_project)
    if state.repo_root:
        remove_cursor_skills_artifacts(repo_root=state.repo_root)
    if paths.opencode:
        remove_opencode_automation_artifact(config_path=Path(paths.opencode))
        if remove_opencode_config(config_path=Path(paths.opencode)):
            removed.append(paths.opencode)
    return removed


def verify_binary(*, install_mode: str | None = None) -> list[str]:
    issues: list[str] = []
    capiforge_bin = detect_capiforge_bin()
    if not capiforge_bin:
        issues.append("capiforge is not available in PATH")
        return issues
    completed = _run([capiforge_bin, "--version"])
    if completed.returncode != 0 or not completed.stdout.strip():
        issues.append("capiforge --version failed")
    completed = _run([capiforge_bin, "mcp", "--help"])
    if completed.returncode != 0:
        issues.append("capiforge mcp --help failed")
    if install_mode == "deb" and not system_share_installed():
        issues.append("installer state expects deb package but share data is missing")
    return issues


def verify_state(state: InstallerState) -> list[str]:
    issues = verify_binary(install_mode=state.install_mode)
    capiforge_bin = detect_capiforge_bin() or state.capiforge_bin
    repo_root = Path(state.repo_root)
    node_home = Path(state.node_home)
    if "cursor" in state.targets and state.integration_paths.cursor_global:
        issues.extend(
            verify_cursor_config(
                config_path=Path(state.integration_paths.cursor_global),
                capiforge_bin=capiforge_bin,
                repo_root=str(repo_root),
                node_home=str(node_home),
            )
        )
        if repo_root.exists():
            issues.extend(verify_cursor_skills(repo_root=str(repo_root)))
    if "opencode" in state.targets and state.integration_paths.opencode:
        issues.extend(
            verify_opencode_config(
                config_path=Path(state.integration_paths.opencode),
                capiforge_bin=capiforge_bin,
                repo_root=str(repo_root),
                node_home=str(node_home),
            )
        )
    if repo_root.exists():
        completed = _run(
            [capiforge_bin, "status", "--repo-root", str(repo_root), "--node-home", str(node_home), "--non-interactive"]
        )
        if completed.returncode != 0:
            issues.append("bootstrap status check failed")
        else:
            payload = json.loads(completed.stdout)
            if payload.get("data", {}).get("bootstrap_state") != "adopted":
                issues.append("bootstrap state is not adopted")
    else:
        issues.append(f"repo_root does not exist: {repo_root}")
    return issues


def run_install(options: InstallOptions) -> InstallerState:
    if not options.targets:
        raise InstallerError("at least one integration target is required: cursor and/or opencode")
    repo_root = options.resolved_repo_root()
    node_home = options.resolved_node_home(repo_root)
    capiforge_bin, install_mode = install_binary(options)
    bootstrap_repo(capiforge_bin=capiforge_bin, options=options, repo_root=repo_root, node_home=node_home)
    integration_paths = write_integrations(
        capiforge_bin=capiforge_bin,
        checkout_root=options.checkout_root.resolve(),
        repo_root=repo_root,
        node_home=node_home,
        targets=options.targets,
        integration_paths=default_integration_paths(repo_root=repo_root),
    )
    backend = install_mode if install_mode == "deb" else resolve_backend(options)
    state = InstallerState(
        install_mode=install_mode,
        backend=backend,
        capiforge_bin=capiforge_bin,
        repo_root=str(repo_root),
        node_home=str(node_home),
        checkout_root=str(options.checkout_root.resolve()),
        install_tui_extra=options.install_tui_extra,
        targets=list(options.targets),
        integration_paths=integration_paths,
    )
    save_state(state)
    issues = verify_state(state)
    if issues:
        raise InstallerError("; ".join(issues))
    return state


def run_update(options: InstallOptions, *, state: InstallerState | None = None) -> InstallerState:
    existing = state or load_state() or detect_existing_state(checkout_root=options.checkout_root)
    if existing is None:
        raise InstallerError("no existing installation state found; run install first")

    merged = InstallOptions(
        checkout_root=options.checkout_root,
        repo_root=Path(existing.repo_root),
        node_home=Path(existing.node_home),
        targets=existing.targets or options.targets,
        backend=existing.backend if existing.backend not in {"unknown", "deb"} else options.backend,
        install_tui_extra=existing.install_tui_extra,
        bootstrap_interactive=options.bootstrap_interactive,
        bootstrap_uv=options.bootstrap_uv,
        reinstall=True,
    )
    if not merged.targets:
        raise InstallerError("cannot update without known integration targets")

    capiforge_bin, install_mode = install_binary(merged)
    repo_root = Path(existing.repo_root)
    node_home = Path(existing.node_home)
    if repo_root.exists():
        bootstrap_repo(capiforge_bin=capiforge_bin, options=merged, repo_root=repo_root, node_home=node_home)
    integration_paths = write_integrations(
        capiforge_bin=capiforge_bin,
        checkout_root=options.checkout_root.resolve(),
        repo_root=repo_root,
        node_home=node_home,
        targets=merged.targets,
        integration_paths=existing.integration_paths,
    )
    existing.capiforge_bin = capiforge_bin
    existing.install_mode = install_mode
    existing.backend = install_mode if install_mode == "deb" else resolve_backend(merged)
    existing.integration_paths = integration_paths
    existing.checkout_root = str(options.checkout_root.resolve())
    save_state(existing)
    issues = verify_state(existing)
    if issues:
        raise InstallerError("; ".join(issues))
    return existing


def run_uninstall(*, remove_bootstrap: bool = False, state: InstallerState | None = None) -> dict:
    existing = state or load_state() or detect_existing_state()
    summary = {"removed_integrations": [], "removed_binary": False, "removed_bootstrap": False, "cleared_state": False}
    if existing is not None:
        summary["removed_integrations"] = remove_integrations(existing)
        if existing.install_mode == "deb":
            summary["removed_binary"] = False
            summary["system_package_retained"] = True
        else:
            backend = existing.backend if existing.backend in {"uv", "pipx"} else detect_backend(existing.capiforge_bin)
            if backend == "uv":
                completed = _run(["uv", "tool", "uninstall", PACKAGE_NAME])
                summary["removed_binary"] = completed.returncode == 0
            elif backend == "pipx":
                completed = _run(["pipx", "uninstall", PACKAGE_NAME])
                summary["removed_binary"] = completed.returncode == 0
        if remove_bootstrap:
            node_home = Path(existing.node_home)
            repo_node = Path(existing.repo_root) / ".capiforge"
            for path in (node_home, repo_node):
                if path.exists():
                    shutil.rmtree(path)
            summary["removed_bootstrap"] = True
    clear_state()
    summary["cleared_state"] = True
    return summary


def run_verify(*, state: InstallerState | None = None) -> dict:
    existing = state or load_state() or detect_existing_state()
    if existing is None:
        issues = verify_binary()
    else:
        issues = verify_state(existing)
    return {"ok": not issues, "issues": issues, "state": existing.to_dict() if existing else None}


def _parse_targets(raw: str | None, flags: argparse.Namespace) -> list[str]:
    targets: list[str] = []
    if flags.cursor:
        targets.append("cursor")
    if flags.opencode:
        targets.append("opencode")
    if raw:
        for item in raw.split(","):
            value = item.strip().lower()
            if value and value not in targets:
                targets.append(value)
    normalized = [target for target in targets if target in {"cursor", "opencode"}]
    return normalized


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--checkout-root", default=str(DEFAULT_CHECKOUT_ROOT))
    common.add_argument("--repo-root")
    common.add_argument("--node-home")
    common.add_argument("--backend", default="auto", choices=("auto", "uv", "pipx"))
    common.add_argument("--no-tui-extra", action="store_true")
    common.add_argument("--bootstrap-uv", action="store_true")
    common.add_argument("--interactive", action="store_true")
    common.add_argument("--json", action="store_true")
    common.add_argument("--cursor", action="store_true")
    common.add_argument("--opencode", action="store_true")
    common.add_argument("--targets")

    parser = argparse.ArgumentParser(description="CapiForge installer core")
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser("install", parents=[common], help="install capiforge and integrations")
    install_parser.set_defaults(reinstall=False)

    update_parser = subparsers.add_parser("update", parents=[common], help="refresh installed components")
    update_parser.set_defaults(reinstall=True)

    subparsers.add_parser("verify", parents=[common], help="verify installation health")
    uninstall_parser = subparsers.add_parser("uninstall", parents=[common], help="remove capiforge and integrations")
    uninstall_parser.add_argument("--remove-bootstrap", action="store_true")
    subparsers.add_parser("detect-state", parents=[common], help="detect existing installation state")
    return parser


def _options_from_args(args: argparse.Namespace) -> InstallOptions:
    return InstallOptions(
        checkout_root=Path(args.checkout_root),
        repo_root=Path(args.repo_root).resolve() if args.repo_root else None,
        node_home=Path(args.node_home).resolve() if args.node_home else None,
        targets=_parse_targets(args.targets, args),
        backend=args.backend,
        install_tui_extra=not args.no_tui_extra,
        bootstrap_interactive=args.interactive,
        bootstrap_uv=args.bootstrap_uv,
        reinstall=getattr(args, "reinstall", False),
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    options = _options_from_args(args)

    try:
        if args.command == "install":
            result = run_install(options)
            payload = {"ok": True, "state": result.to_dict()}
        elif args.command == "update":
            result = run_update(options)
            payload = {"ok": True, "state": result.to_dict()}
        elif args.command == "verify":
            payload = run_verify()
        elif args.command == "uninstall":
            payload = {"ok": True, "summary": run_uninstall(remove_bootstrap=args.remove_bootstrap)}
        elif args.command == "detect-state":
            state = load_state() or detect_existing_state(checkout_root=options.checkout_root)
            payload = {"ok": True, "state": state.to_dict() if state else None}
        else:
            raise InstallerError(f"unsupported command: {args.command}")
    except InstallerError as exc:
        payload = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"capiforge-install: error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
