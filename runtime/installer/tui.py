from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Input, OptionList, Static
from textual.widgets.option_list import Option

from runtime.paths import asset_path, dev_repo_root, default_repo_root
from runtime.installer.state import detect_capiforge_bin, detect_existing_state, load_state
from runtime.tui.splash import SPLASH_DURATION_SECONDS, SplashContent, build_splash_content, load_splash_art
from runtime.installer.core import (
    InstallOptions,
    InstallerError,
    run_install,
    run_uninstall,
    run_update,
    run_verify,
)


@dataclass
class InstallDraft:
    cursor: bool = True
    opencode: bool = False
    repo_root: str = ""
    install_tui_extra: bool = True


@dataclass
class UninstallDraft:
    remove_bootstrap: bool = False


CHECKOUT_ROOT = dev_repo_root()


def _default_repo_root() -> str:
    return str(default_repo_root())


COMPACT_ASCII_PATH = asset_path("assets/capiforge-icons/capiforge-ascii-compact.txt")
LAUNCH_SPLASH_SECONDS = SPLASH_DURATION_SECONDS


def _launch_splash_content(*, width: int, height: int) -> SplashContent:
    full_art = load_splash_art()
    content = build_splash_content(
        available_width=max(20, width),
        available_height=max(8, height),
        ascii_art=full_art,
    )
    if content.mode == "ascii":
        return content
    try:
        compact_art = COMPACT_ASCII_PATH.read_text(encoding="utf-8")
    except OSError:
        return content
    return build_splash_content(
        available_width=max(20, width),
        available_height=max(8, height),
        ascii_art=compact_art,
    )


def _toggle_label(checked: bool, label: str) -> str:
    mark = "x" if checked else " "
    return f"[{mark}] {label}"


def _status_summary() -> str:
    state = load_state() or detect_existing_state(checkout_root=CHECKOUT_ROOT)
    lines = ["CapiForge installer for local MCP + task workflows."]
    if state is None:
        lines.append("Status: not installed")
    else:
        lines.append(f"Installed: {state.capiforge_bin or 'unknown'}")
        lines.append(f"Repo: {state.repo_root}")
        if state.targets:
            lines.append(f"Integrations: {', '.join(state.targets)}")
    return "\n".join(lines)


def _resolve_capiforge_bin() -> str | None:
    state = load_state()
    if state and state.capiforge_bin and Path(state.capiforge_bin).exists():
        return state.capiforge_bin
    return detect_capiforge_bin()


def _capiforge_installed() -> bool:
    return _resolve_capiforge_bin() is not None


def _main_menu_options() -> list[Option]:
    options = [
        Option("Install", id="install"),
        Option("Update", id="update"),
        Option("Uninstall", id="uninstall"),
        Option("Verify", id="verify"),
    ]
    if _capiforge_installed():
        options.append(Option("Open CapiForge TUI", id="capiforge-tui"))
    options.append(Option("Quit", id="quit"))
    return options


class MenuScreen(Screen):
    """Reusable contextual menu with title, subtitle, and keyboard hints."""

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=False),
        Binding("q", "quit_app", "Quit", show=False),
    ]

    def __init__(
        self,
        *,
        title: str,
        subtitle: str,
        hint: str = "↑↓ navigate · Enter select · Esc back · q quit",
        show_back: bool = True,
    ) -> None:
        super().__init__()
        self.menu_title = title
        self.menu_subtitle = subtitle
        self.menu_hint = hint
        self.show_back = show_back

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(self.menu_title, classes="installer-title"),
            Static(self.menu_subtitle, classes="installer-subtitle"),
            Static(_status_summary(), classes="installer-status"),
            OptionList(id="menu-options"),
            Static(self.menu_hint, classes="installer-hint"),
            classes="installer-shell",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._populate_options()
        self.query_one("#menu-options", OptionList).focus()

    def _populate_options(self) -> None:
        pass

    def set_options(self, options: list[Option]) -> None:
        option_list = self.query_one("#menu-options", OptionList)
        option_list.clear_options()
        for option in options:
            option_list.add_option(option)
        if option_list.option_count:
            option_list.highlighted = 0

    def action_go_back(self) -> None:
        if self.show_back:
            self.app.pop_screen()

    def action_quit_app(self) -> None:
        self.app.exit(0)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.handle_option(event.option.id or "")

    def handle_option(self, option_id: str) -> None:
        raise NotImplementedError


class MainMenuScreen(MenuScreen):
    def __init__(self) -> None:
        super().__init__(
            title="CapiForge",
            subtitle="What would you like to do?",
            hint="↑↓ navigate · Enter select · q quit",
            show_back=False,
        )

    def refresh_view(self) -> None:
        self.query_one(".installer-status", Static).update(_status_summary())
        self._populate_options()

    def on_screen_resume(self) -> None:
        self.refresh_view()

    def _populate_options(self) -> None:
        self.set_options(_main_menu_options())

    def handle_option(self, option_id: str) -> None:
        if option_id == "install":
            self.app.push_screen(IntegrationsScreen(InstallDraft(repo_root=_default_repo_root())))
        elif option_id == "update":
            self.app.push_screen(ConfirmActionScreen("update"))
        elif option_id == "uninstall":
            self.app.push_screen(UninstallOptionsScreen(UninstallDraft()))
        elif option_id == "verify":
            self.app.push_screen(ConfirmActionScreen("verify"))
        elif option_id == "capiforge-tui":
            self.app.request_product_tui_launch()
        elif option_id == "quit":
            self.app.exit(0)


class IntegrationsScreen(MenuScreen):
    BINDINGS = MenuScreen.BINDINGS + [Binding("space", "toggle_highlighted", "Toggle", show=True)]

    def __init__(self, draft: InstallDraft) -> None:
        super().__init__(
            title="Install · Integrations",
            subtitle="Step 1 of 4 · Where will you use CapiForge?",
            hint="↑↓ navigate · Space toggle · Enter on Continue · Esc back",
        )
        self.draft = draft
        self._keys = ("cursor", "opencode")

    def _populate_options(self) -> None:
        self._refresh_options()

    def _refresh_options(self) -> None:
        self.set_options(
            [
                Option(_toggle_label(self.draft.cursor, "Cursor MCP integration"), id="cursor"),
                Option(_toggle_label(self.draft.opencode, "OpenCode MCP integration"), id="opencode"),
                Option("Continue →", id="continue"),
            ]
        )

    def action_toggle_highlighted(self) -> None:
        option_list = self.query_one("#menu-options", OptionList)
        highlighted = option_list.highlighted_option
        if highlighted is None or highlighted.id not in self._keys:
            return
        if highlighted.id == "cursor":
            self.draft.cursor = not self.draft.cursor
        elif highlighted.id == "opencode":
            self.draft.opencode = not self.draft.opencode
        index = option_list.highlighted
        self._refresh_options()
        if index is not None:
            option_list.highlighted = min(index, len(option_list.options) - 1)

    def handle_option(self, option_id: str) -> None:
        if option_id in self._keys:
            return
        if option_id != "continue":
            return
        if not self.draft.cursor and not self.draft.opencode:
            self.notify("Select at least one integration.", severity="warning")
            return
        self.app.push_screen(RepoRootScreen(self.draft))


class RepoRootScreen(MenuScreen):
    BINDINGS = MenuScreen.BINDINGS + [Binding("enter", "submit_repo", "Continue", show=False)]

    def __init__(self, draft: InstallDraft) -> None:
        super().__init__(
            title="Install · Repository",
            subtitle="Step 2 of 4 · Which repo should CapiForge bootstrap?",
            hint="Edit path below · Enter continue · Esc back",
        )
        self.draft = draft

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(self.menu_title, classes="installer-title"),
            Static(self.menu_subtitle, classes="installer-subtitle"),
            Static(f"Node home: {Path(self.draft.repo_root or _default_repo_root()) / '.capiforge' / 'node'}", classes="installer-note"),
            Input(value=self.draft.repo_root or _default_repo_root(), id="repo-root"),
            OptionList(Option("Continue →", id="continue"), id="menu-options"),
            Static(self.menu_hint, classes="installer-hint"),
            classes="installer-shell",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._populate_options()
        self.query_one("#repo-root", Input).focus()

    def _populate_options(self) -> None:
        option_list = self.query_one("#menu-options", OptionList)
        if option_list.option_count:
            option_list.highlighted = 0

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "repo-root":
            self._continue()

    def action_submit_repo(self) -> None:
        self._continue()

    def handle_option(self, option_id: str) -> None:
        if option_id == "continue":
            self._continue()

    def _continue(self) -> None:
        repo_root = self.query_one("#repo-root", Input).value.strip()
        if not repo_root:
            self.notify("Repository path is required.", severity="warning")
            return
        self.draft.repo_root = repo_root
        self.app.push_screen(TuiExtraScreen(self.draft))


class TuiExtraScreen(MenuScreen):
    def __init__(self, draft: InstallDraft) -> None:
        super().__init__(
            title="Install · Options",
            subtitle="Step 3 of 4 · Include the optional terminal UI?",
            hint="↑↓ navigate · Enter select · Esc back",
        )
        self.draft = draft

    def _populate_options(self) -> None:
        yes = self.draft.install_tui_extra
        self.set_options(
            [
                Option(_toggle_label(yes, "Yes — install Textual TUI extra"), id="yes"),
                Option(_toggle_label(not yes, "No — CLI only"), id="no"),
                Option("Continue →", id="continue"),
            ]
        )

    def handle_option(self, option_id: str) -> None:
        if option_id == "yes":
            self.draft.install_tui_extra = True
            self._populate_options()
        elif option_id == "no":
            self.draft.install_tui_extra = False
            self._populate_options()
        elif option_id == "continue":
            self.app.push_screen(InstallConfirmScreen(self.draft))


class InstallConfirmScreen(MenuScreen):
    def __init__(self, draft: InstallDraft) -> None:
        super().__init__(
            title="Install · Confirm",
            subtitle="Step 4 of 4 · Review and start installation",
            hint="↑↓ navigate · Enter select · Esc back",
        )
        self.draft = draft

    def _populate_options(self) -> None:
        targets = []
        if self.draft.cursor:
            targets.append("Cursor")
        if self.draft.opencode:
            targets.append("OpenCode")
        summary = "\n".join(
            [
                f"Integrations: {', '.join(targets)}",
                f"Repository: {self.draft.repo_root}",
                f"TUI extra: {'yes' if self.draft.install_tui_extra else 'no'}",
            ]
        )
        self.query_one(".installer-subtitle", Static).update(f"Step 4 of 4 · Review\n{summary}")
        self.set_options(
            [
                Option("Start installation", id="start"),
                Option("Back", id="back"),
            ]
        )

    def handle_option(self, option_id: str) -> None:
        if option_id == "back":
            self.app.pop_screen()
            return
        if option_id == "start":
            self.app.push_screen(InstallProgressScreen(self.draft))


class InstallProgressScreen(Screen):
    BINDINGS = [Binding("escape", "pop_screen", "Back", show=False)]

    def __init__(self, draft: InstallDraft) -> None:
        super().__init__()
        self.draft = draft

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("Install · Running", classes="installer-title"),
            Static("Installing capiforge and writing integration config…", classes="installer-subtitle"),
            Static("", id="progress-log", classes="installer-log"),
            Static("Please wait…", classes="installer-hint"),
            classes="installer-shell",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.run_install_flow()

    @work(thread=True)
    def run_install_flow(self) -> None:
        log = self.query_one("#progress-log", Static)
        targets: list[str] = []
        if self.draft.cursor:
            targets.append("cursor")
        if self.draft.opencode:
            targets.append("opencode")
        options = InstallOptions(
            checkout_root=CHECKOUT_ROOT,
            repo_root=Path(self.draft.repo_root),
            targets=targets,
            install_tui_extra=self.draft.install_tui_extra,
        )
        try:
            state = run_install(options)
            lines = [
                "Install complete.",
                "",
                f"Binary: {state.capiforge_bin}",
                f"Repo: {state.repo_root}",
                f"Integrations: {', '.join(state.targets)}",
                "",
                "Next steps:",
            ]
            if "cursor" in state.targets:
                lines.append("• Cursor: reload MCP servers or restart Cursor.")
            if "opencode" in state.targets:
                lines.append("• OpenCode: restart OpenCode to reload MCP config.")
            log.update("\n".join(lines))
            self.app.call_from_thread(self.app.return_to_main_menu, "Install complete.")
        except InstallerError as exc:
            log.update(f"Install failed:\n\n{exc}\n\nEsc to go back.")


class ConfirmActionScreen(MenuScreen):
    def __init__(self, action: str) -> None:
        title = action.title()
        super().__init__(
            title=f"{title} · Confirm",
            subtitle=f"Run {action} using saved installer state?",
            hint="↑↓ navigate · Enter select · Esc back",
        )
        self.action = action

    def _populate_options(self) -> None:
        self.set_options(
            [
                Option(f"Run {self.action}", id="run"),
                Option("Back", id="back"),
            ]
        )

    def handle_option(self, option_id: str) -> None:
        if option_id == "back":
            self.app.pop_screen()
            return
        if option_id == "run":
            self.app.push_screen(ActionProgressScreen(self.action))


class ActionProgressScreen(Screen):
    BINDINGS = [Binding("escape", "pop_screen", "Back", show=False)]

    def __init__(self, action: str) -> None:
        super().__init__()
        self.action = action

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(f"{self.action.title()} · Running", classes="installer-title"),
            Static("", id="progress-log", classes="installer-log"),
            Static("Esc to return to menu", classes="installer-hint"),
            classes="installer-shell",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.run_action()

    @work(thread=True)
    def run_action(self) -> None:
        log = self.query_one("#progress-log", Static)
        try:
            if self.action == "update":
                state = run_update(InstallOptions(checkout_root=CHECKOUT_ROOT, reinstall=True))
                log.update(
                    "\n".join(
                        [
                            "Update complete.",
                            "",
                            f"Binary: {state.capiforge_bin}",
                            f"Integrations: {', '.join(state.targets)}",
                            "",
                            "Reload Cursor MCP / restart OpenCode if configs changed.",
                        ]
                    )
                )
                self.app.call_from_thread(self.app.return_to_main_menu, "Update complete.")
            elif self.action == "verify":
                payload = run_verify()
                if payload["ok"]:
                    log.update("Verify OK.\n\n" + str(payload.get("state")))
                    self.app.call_from_thread(self.app.return_to_main_menu, "Verify OK.")
                else:
                    log.update("Verify failed:\n\n- " + "\n- ".join(payload["issues"]) + "\n\nEsc to go back.")
            else:
                log.update(f"Unsupported action: {self.action}")
        except InstallerError as exc:
            log.update(f"{self.action.title()} failed:\n\n{exc}\n\nEsc to go back.")


class UninstallOptionsScreen(MenuScreen):
    BINDINGS = MenuScreen.BINDINGS + [Binding("space", "toggle_highlighted", "Toggle", show=True)]

    def __init__(self, draft: UninstallDraft) -> None:
        super().__init__(
            title="Uninstall · Options",
            subtitle="Remove CapiForge binary, MCP entries, and installer state.",
            hint="↑↓ navigate · Space toggle bootstrap · Enter on Continue · Esc back",
        )
        self.draft = draft

    def _populate_options(self) -> None:
        self.set_options(
            [
                Option(
                    _toggle_label(self.draft.remove_bootstrap, "Also delete bootstrap data (.capiforge/node)"),
                    id="bootstrap",
                ),
                Option("Continue →", id="continue"),
            ]
        )

    def action_toggle_highlighted(self) -> None:
        option_list = self.query_one("#menu-options", OptionList)
        highlighted = option_list.highlighted_option
        if highlighted is None or highlighted.id != "bootstrap":
            return
        self.draft.remove_bootstrap = not self.draft.remove_bootstrap
        index = option_list.highlighted
        self._populate_options()
        if index is not None:
            option_list.highlighted = min(index, len(option_list.options) - 1)

    def handle_option(self, option_id: str) -> None:
        if option_id == "bootstrap":
            return
        if option_id == "continue":
            self.app.push_screen(UninstallConfirmScreen(self.draft))


class UninstallConfirmScreen(MenuScreen):
    def __init__(self, draft: UninstallDraft) -> None:
        super().__init__(
            title="Uninstall · Confirm",
            subtitle="This removes capiforge and registered MCP integration entries.",
            hint="↑↓ navigate · Enter select · Esc back",
        )
        self.draft = draft

    def _populate_options(self) -> None:
        extra = "Bootstrap data will also be deleted." if self.draft.remove_bootstrap else "Bootstrap data will be kept."
        self.query_one(".installer-subtitle", Static).update(
            "This removes capiforge and registered MCP integration entries.\n" + extra
        )
        self.set_options(
            [
                Option("Uninstall now", id="start"),
                Option("Back", id="back"),
            ]
        )

    def handle_option(self, option_id: str) -> None:
        if option_id == "back":
            self.app.pop_screen()
            return
        if option_id == "start":
            self.app.push_screen(UninstallProgressScreen(self.draft))


class UninstallProgressScreen(Screen):
    BINDINGS = [Binding("escape", "pop_screen", "Back", show=False)]

    def __init__(self, draft: UninstallDraft) -> None:
        super().__init__()
        self.draft = draft

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("Uninstall · Running", classes="installer-title"),
            Static("", id="progress-log", classes="installer-log"),
            Static("Esc to return to menu", classes="installer-hint"),
            classes="installer-shell",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.run_uninstall_flow()

    @work(thread=True)
    def run_uninstall_flow(self) -> None:
        log = self.query_one("#progress-log", Static)
        try:
            summary = run_uninstall(remove_bootstrap=self.draft.remove_bootstrap)
            log.update(
                "\n".join(
                    [
                        "Uninstall complete.",
                        "",
                        f"Removed integrations: {summary['removed_integrations']}",
                        f"Removed binary: {summary['removed_binary']}",
                        f"Removed bootstrap: {summary['removed_bootstrap']}",
                        f"Cleared installer state: {summary['cleared_state']}",
                    ]
                )
            )
            self.app.call_from_thread(self.app.return_to_main_menu, "Uninstall complete.")
        except InstallerError as exc:
            log.update(f"Uninstall failed:\n\n{exc}\n\nEsc to go back.")


class ProductTuiLaunchScreen(Screen):
    """Brief ASCII splash before handing off to capiforge tui."""

    BINDINGS = [
        Binding("escape", "launch_now", "Skip", show=False),
        Binding("enter", "launch_now", "Skip", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(id="launch-splash"),
            Static("Opening CapiForge TUI…  Enter to skip", classes="installer-hint launch-splash-hint"),
            classes="installer-shell launch-splash-shell",
        )

    def on_mount(self) -> None:
        self._render_splash()
        self.set_timer(LAUNCH_SPLASH_SECONDS, self._launch_now)

    def on_resize(self, _event) -> None:
        self._render_splash()

    def on_key(self, event) -> None:
        event.stop()
        self._launch_now()

    def action_launch_now(self) -> None:
        self._launch_now()

    def _render_splash(self) -> None:
        splash = _launch_splash_content(width=self.size.width, height=self.size.height)
        widget = self.query_one("#launch-splash", Static)
        widget.set_classes(splash.mode)
        widget.update("\n".join(splash.lines) if splash.lines else "CapiForge")

    def _launch_now(self) -> None:
        if getattr(self.app, "launch_product_tui", False):
            return
        self.app.launch_product_tui = True
        self.app.exit(0)


class InstallerApp(App):
    launch_product_tui = False

    CSS = """
    Screen {
        background: #0d1117;
        color: #e6edf3;
    }

    .installer-shell {
        height: 1fr;
        padding: 1 2;
    }

    .installer-title {
        text-style: bold;
        color: #58a6ff;
        padding-bottom: 1;
    }

    .installer-subtitle {
        color: #c9d1d9;
        padding-bottom: 1;
    }

    .installer-status {
        color: #8b949e;
        padding-bottom: 1;
    }

    .installer-note {
        color: #8b949e;
        padding-bottom: 1;
    }

    .installer-hint {
        color: #6e7681;
        padding-top: 1;
    }

    OptionList {
        height: auto;
        max-height: 12;
        border: solid #30363d;
        background: #161b22;
        padding: 0 1;
        margin: 1 0;
    }

    OptionList:focus {
        border: solid #58a6ff;
    }

    OptionList > .option-list--option {
        padding: 0 1;
    }

    OptionList > .option-list--option-highlighted {
        background: #21262d;
        color: #58a6ff;
        text-style: bold;
    }

    Input {
        margin-bottom: 1;
        border: solid #30363d;
        background: #161b22;
        padding: 0 1;
    }

    Input:focus {
        border: solid #58a6ff;
    }

    .installer-log {
        height: 1fr;
        border: solid #30363d;
        background: #161b22;
        padding: 1;
        margin-top: 1;
    }

    .launch-splash-shell {
        align: center middle;
        height: 1fr;
    }

    #launch-splash {
        width: 100%;
        content-align: center middle;
        text-align: center;
        color: #58a6ff;
    }

    #launch-splash.ascii {
        color: #7fd1ff;
    }

    .launch-splash-hint {
        text-align: center;
        padding-top: 1;
    }

    Footer {
        background: #161b22;
        color: #8b949e;
    }
    """

    BINDINGS = [Binding("q", "quit", "Quit")]

    def request_product_tui_launch(self) -> None:
        if not _capiforge_installed():
            self.notify("capiforge is not installed yet.", severity="warning")
            return
        self.push_screen(ProductTuiLaunchScreen())

    def return_to_main_menu(self, message: str | None = None) -> None:
        while self.screen_stack and not isinstance(self.screen, MainMenuScreen):
            self.pop_screen()
        if not isinstance(self.screen, MainMenuScreen):
            self.push_screen(MainMenuScreen())
        else:
            self.screen.refresh_view()
        if message:
            self.notify(message)

    def on_mount(self) -> None:
        self.push_screen(MainMenuScreen())


def _launch_product_tui() -> int:
    capiforge_bin = _resolve_capiforge_bin()
    if not capiforge_bin:
        print("capiforge is not installed.", file=sys.stderr)
        return 1

    env = os.environ.copy()
    if (CHECKOUT_ROOT / "pyproject.toml").exists():
        pythonpath = str(CHECKOUT_ROOT)
        if env.get("PYTHONPATH"):
            pythonpath = f"{pythonpath}{os.pathsep}{env['PYTHONPATH']}"
        env["PYTHONPATH"] = pythonpath
    os.execvpe(capiforge_bin, [capiforge_bin, "tui"], env)
    return 1


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(prog="capinstall-tui")


def main(argv: list[str] | None = None) -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("The installer TUI requires an interactive terminal.", file=sys.stderr)
        return 1
    build_parser().parse_args(list(argv) if argv is not None else None)
    app = InstallerApp()
    result = app.run()
    if app.launch_product_tui:
        return _launch_product_tui()
    return 0 if result is None else result


if __name__ == "__main__":
    raise SystemExit(main())
