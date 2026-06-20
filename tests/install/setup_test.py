import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
CORE = REPO_ROOT / "scripts" / "installer_core.py"
INTEGRATION = REPO_ROOT / "scripts" / "integration_config.py"
INSTALL_SH = REPO_ROOT / "scripts" / "install.sh"


class InstallShTest(unittest.TestCase):
    def test_update_command_is_forwarded_before_checkout_root(self) -> None:
        completed = subprocess.run(
            ["bash", str(INSTALL_SH), "--no-tui-ui", "update", "--json"],
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
            capture_output=True,
            text=True,
        )
        combined = f"{completed.stdout}\n{completed.stderr}"
        self.assertNotIn("invalid choice", combined)
        self.assertNotIn("unrecognized arguments", combined)


class IntegrationConfigTest(unittest.TestCase):
    def test_cursor_merge_and_remove(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "mcp.json"
            config_path.write_text(json.dumps({"mcpServers": {"existing": {"command": "echo"}}}), encoding="utf-8")
            subprocess.run(
                [
                    "python3",
                    str(INTEGRATION),
                    "write-cursor",
                    "--config-path",
                    str(config_path),
                    "--command",
                    "/usr/local/bin/capiforge",
                    "--repo-root",
                    temp_dir,
                    "--node-home",
                    str(Path(temp_dir) / ".capiforge" / "node"),
                ],
                check=True,
            )
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertIn("existing", payload["mcpServers"])
            self.assertIn("capiforge", payload["mcpServers"])

            subprocess.run(
                ["python3", str(INTEGRATION), "remove-cursor", "--config-path", str(config_path)],
                check=True,
            )
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertNotIn("capiforge", payload.get("mcpServers", {}))
            self.assertIn("existing", payload["mcpServers"])

    def test_cursor_skills_install_and_remove(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir) / "project"
            repo_root.mkdir()
            for skill_name in (
                "capiforge-pickup-task",
                "capiforge-start-task",
                "capiforge-close-task",
                "capiforge-data-layer",
                "capiforge-record-completed-work",
            ):
                source = REPO_ROOT / "skills" / skill_name
                target = repo_root / "skills" / skill_name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, target)
            from runtime.installer.integration_config import (
                remove_cursor_skills_artifacts,
                verify_cursor_skills,
                write_cursor_skills_artifacts,
            )

            write_cursor_skills_artifacts(repo_root=str(repo_root))
            self.assertEqual(verify_cursor_skills(repo_root=str(repo_root)), [])
            remove_cursor_skills_artifacts(repo_root=str(repo_root))
            self.assertTrue(any("missing Cursor skill artifact" in issue for issue in verify_cursor_skills(repo_root=str(repo_root))))

    def test_opencode_merge_and_remove(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "opencode.json"
            config_path.write_text(json.dumps({"mcp": {"engram": {"type": "local", "command": ["engram"]}}}), encoding="utf-8")
            subprocess.run(
                [
                    "python3",
                    str(INTEGRATION),
                    "write-opencode",
                    "--config-path",
                    str(config_path),
                    "--command",
                    "/usr/local/bin/capiforge",
                    "--repo-root",
                    temp_dir,
                    "--node-home",
                    str(Path(temp_dir) / ".capiforge" / "node"),
                ],
                check=True,
            )
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertIn("capiforge", payload["mcp"])
            self.assertEqual(payload["mcp"]["capiforge"]["type"], "local")
            self.assertIn(str(config_path.parent / "skills"), payload["skills"]["paths"])

            subprocess.run(
                ["python3", str(INTEGRATION), "remove-opencode", "--config-path", str(config_path)],
                check=True,
            )
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertNotIn("capiforge", payload.get("mcp", {}))
            self.assertNotIn(str(config_path.parent / "skills"), payload.get("skills", {}).get("paths", []))


class InstallerStateTest(unittest.TestCase):
    def test_save_and_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "installer-state.json"
            env = {"PYTHONPATH": str(REPO_ROOT)}
            write = subprocess.run(
                [
                    "python3",
                    "-c",
                    (
                        "from pathlib import Path; "
                        "from runtime.installer.state import InstallerState, IntegrationPaths, save_state; "
                        "state = InstallerState("
                        "capiforge_bin='/tmp/capiforge', repo_root='/tmp/repo', node_home='/tmp/repo/.capiforge/node', "
                        "targets=['cursor'], integration_paths=IntegrationPaths(cursor_global='/tmp/mcp.json')"
                        "); "
                        f"save_state(state, Path('{state_path}'))"
                    ),
                ],
                cwd=REPO_ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(write.returncode, 0)
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["targets"], ["cursor"])


class DebInstallModeTest(unittest.TestCase):
    def test_detect_system_package_false_in_dev_checkout(self) -> None:
        from runtime.installer.core import detect_system_package
        from runtime.paths import system_share_installed

        self.assertFalse(system_share_installed())
        if shutil.which("capiforge"):
            self.assertFalse(detect_system_package())

    def test_detect_system_package_true_when_system_share_exists(self) -> None:
        from runtime.installer.core import detect_system_package

        with patch("runtime.installer.core.detect_capiforge_bin", return_value="/usr/bin/capiforge"):
            with patch("runtime.installer.core._run", return_value=type("R", (), {"returncode": 0, "stdout": "capiforge 0.1.0"})()):
                with patch("runtime.installer.core.system_share_installed", return_value=True):
                    self.assertTrue(detect_system_package())

    def test_install_binary_uses_deb_mode_when_system_package_detected(self) -> None:
        from runtime.installer.core import InstallOptions, install_binary

        options = InstallOptions(checkout_root=REPO_ROOT, targets=["cursor"])
        with patch("runtime.installer.core.detect_system_package", return_value=True):
            with patch("runtime.installer.core.detect_capiforge_bin", return_value="/usr/bin/capiforge"):
                capiforge_bin, install_mode = install_binary(options)
        self.assertEqual(capiforge_bin, "/usr/bin/capiforge")
        self.assertEqual(install_mode, "deb")


@unittest.skipUnless(shutil.which("uv") or shutil.which("pipx"), "uv or pipx required for installer core integration test")
class InstallerCoreTest(unittest.TestCase):
    def test_install_update_uninstall_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_home = Path(temp_dir) / "home"
            fake_home.mkdir()
            repo_root = Path(temp_dir) / "project"
            repo_root.mkdir()
            (repo_root / ".git").mkdir()
            local_bin = fake_home / ".local" / "bin"
            env = {
                "HOME": str(fake_home),
                "PATH": f"{local_bin}{os.pathsep}{os.environ.get('PATH', '')}",
                "PYTHONPATH": str(REPO_ROOT),
                "CAPIFORGE_INSTALL_UV": "0",
            }

            install = subprocess.run(
                [
                    "python3",
                    str(CORE),
                    "install",
                    "--repo-root",
                    str(repo_root),
                    "--cursor",
                    "--opencode",
                    "--json",
                ],
                cwd=REPO_ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            install_payload = json.loads(install.stdout)
            self.assertTrue(install_payload["ok"], install.stderr)
            self.assertTrue((fake_home / ".capiforge" / "installer-state.json").exists())
            self.assertTrue((fake_home / ".cursor" / "mcp.json").exists())
            self.assertTrue((fake_home / ".config" / "opencode" / "opencode.json").exists())
            self.assertTrue(
                (fake_home / ".config" / "opencode" / "skills" / "capiforge-record-completed-work" / "SKILL.md").exists()
            )
            self.assertTrue((repo_root / ".capiforge" / "node" / "bootstrap.json").exists())

            update = subprocess.run(
                ["python3", str(CORE), "update", "--json"],
                cwd=REPO_ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue(json.loads(update.stdout)["ok"], update.stderr)

            skill_file = fake_home / ".config" / "opencode" / "skills" / "capiforge-record-completed-work" / "SKILL.md"
            skill_file.unlink()
            verify = subprocess.run(
                ["python3", str(CORE), "verify", "--json"],
                cwd=REPO_ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            verify_payload = json.loads(verify.stdout)
            self.assertFalse(verify_payload["ok"])
            self.assertTrue(any("missing OpenCode automation artifact" in issue for issue in verify_payload["issues"]))

            restore = subprocess.run(
                ["python3", str(CORE), "update", "--json"],
                cwd=REPO_ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue(json.loads(restore.stdout)["ok"], restore.stderr)

            uninstall = subprocess.run(
                ["python3", str(CORE), "uninstall", "--json"],
                cwd=REPO_ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            summary = json.loads(uninstall.stdout)["summary"]
            self.assertTrue(summary["cleared_state"])
            self.assertFalse((fake_home / ".capiforge" / "installer-state.json").exists())
            self.assertFalse(
                (fake_home / ".config" / "opencode" / "skills" / "capiforge-record-completed-work" / "SKILL.md").exists()
            )


try:
    from runtime.installer.tui import ConfirmActionScreen, InstallerApp, MainMenuScreen, ProductTuiLaunchScreen, _launch_splash_content, _main_menu_options
    from textual.widgets import OptionList, Static
except ModuleNotFoundError:
    ConfirmActionScreen = None
    InstallerApp = None
    MainMenuScreen = None
    _main_menu_options = None
    OptionList = None
    Static = None


@unittest.skipIf(InstallerApp is None, "textual is required for installer TUI smoke test")
class InstallerTuiSmokeTest(unittest.IsolatedAsyncioTestCase):
    async def test_main_menu_renders(self) -> None:
        app = InstallerApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            option_list = app.screen.query_one("#menu-options", OptionList)
            labels = " ".join(str(option.prompt) for option in option_list.options)
            self.assertIn("Install", labels)
            self.assertIn("Update", labels)
            summary = app.screen.query_one(".installer-status", Static)
            self.assertIn("CapiForge", str(summary.render()))

    async def test_return_to_main_menu_clears_wizard_stack(self) -> None:
        app = InstallerApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(ConfirmActionScreen("verify"))
            await pilot.pause()
            app.return_to_main_menu("Done.")
            await pilot.pause()
            self.assertIsInstance(app.screen, MainMenuScreen)

    async def test_install_wizard_opens_integrations_step(self) -> None:
        app = InstallerApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            option_list = app.screen.query_one("#menu-options", OptionList)
            labels = " ".join(str(option.prompt) for option in option_list.options)
            self.assertIn("Cursor", labels)
            self.assertIn("OpenCode", labels)
            self.assertIn("[x]", labels)

    async def test_install_reaches_repo_step(self) -> None:
        app = InstallerApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("down", "down", "enter")
            await pilot.pause()
            from runtime.installer.tui import RepoRootScreen

            self.assertIsInstance(app.screen, RepoRootScreen)
            app.screen.query_one("#repo-root")

    async def test_product_tui_launch_shows_ascii_splash(self) -> None:
        app = InstallerApp()
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            app.push_screen(ProductTuiLaunchScreen())
            await pilot.pause()
            splash = app.screen.query_one("#launch-splash", Static)
            rendered = str(splash.render())
            self.assertTrue(splash.has_class("ascii") or "CapiForge" in rendered)


@unittest.skipIf(_main_menu_options is None, "textual is required for installer menu option tests")
class InstallerMenuOptionsTest(unittest.TestCase):
    def test_launch_splash_prefers_ascii_when_it_fits(self) -> None:
        content = _launch_splash_content(width=120, height=40)
        self.assertEqual(content.mode, "ascii")
        self.assertTrue(content.lines)

    def test_capiforge_tui_option_when_binary_present(self) -> None:
        with patch("runtime.installer.tui._resolve_capiforge_bin", return_value="/tmp/capiforge"):
            option_ids = [option.id for option in _main_menu_options()]
        self.assertIn("capiforge-tui", option_ids)

    def test_capiforge_tui_option_hidden_without_binary(self) -> None:
        with patch("runtime.installer.tui._resolve_capiforge_bin", return_value=None):
            option_ids = [option.id for option in _main_menu_options()]
        self.assertNotIn("capiforge-tui", option_ids)


if __name__ == "__main__":
    unittest.main()
