import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build-deb.sh"

_HAS_DEB_BUILD = bool(shutil.which("debuild") and shutil.which("dpkg"))


def _run_json(args: list[str], *, env: dict[str, str], cwd: Path) -> dict:
    completed = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _find_built_deb() -> Path:
    candidates = sorted(
        REPO_ROOT.parent.glob("capiforge_*_all.deb"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError("capiforge .deb artifact not found after debuild")
    return candidates[0]


@unittest.skipUnless(_HAS_DEB_BUILD, "debuild and dpkg required for deb integration test")
class DebIntegrationTest(unittest.TestCase):
    def test_dpkg_install_init_adopt_verify(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            instdir = temp / "instdir"
            instdir.mkdir()
            home = temp / "home"
            home.mkdir()
            project = temp / "project"
            project.mkdir()
            node_home = project / ".capiforge" / "node"

            build = subprocess.run(
                ["bash", str(BUILD_SCRIPT)],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, msg=f"{build.stdout}\n{build.stderr}")

            deb = _find_built_deb()
            install = subprocess.run(
                [
                    "dpkg",
                    "--instdir",
                    str(instdir),
                    "--force-not-root",
                    "--force-depends",
                    "--force-all",
                    "-i",
                    str(deb),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(install.returncode, 0, msg=f"{install.stdout}\n{install.stderr}")

            bin_dir = instdir / "usr" / "bin"
            share_root = instdir / "usr" / "share" / "capiforge"
            self.assertTrue((bin_dir / "capiforge").is_file())
            self.assertTrue((share_root / "storage" / "node-schema.sql").is_file())

            env = {
                **os.environ,
                "HOME": str(home),
                "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
                "CAPIFORGE_SHARE": str(share_root),
            }

            capiforge = str(bin_dir / "capiforge")
            capinstall = str(bin_dir / "capinstall")
            bootstrap_args = [
                "--repo-root",
                str(project),
                "--node-home",
                str(node_home),
                "--non-interactive",
            ]

            for command in ("init", "adopt"):
                completed = subprocess.run(
                    [capiforge, command, *bootstrap_args],
                    cwd=project,
                    env=env,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 0, msg=f"{command}: {completed.stderr}")

            status = _run_json([capiforge, "status", *bootstrap_args], env=env, cwd=project)
            self.assertEqual(status.get("data", {}).get("bootstrap_state"), "adopted")

            verify = _run_json([capinstall, "--no-wizard", "verify", "--json"], env=env, cwd=project)
            self.assertTrue(verify.get("ok"), msg=str(verify.get("issues")))


if __name__ == "__main__":
    unittest.main()
