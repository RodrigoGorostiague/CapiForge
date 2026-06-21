import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from runtime.web.folder_picker import pick_folder_native
except ModuleNotFoundError:
    pick_folder_native = None


@unittest.skipIf(pick_folder_native is None, "Web dependencies are not installed")
class FolderPickerTest(unittest.TestCase):
    def test_requires_display(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = pick_folder_native()
        self.assertFalse(result.ok)
        self.assertIn("entorno gráfico", result.message)

    def test_uses_zenity_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            selected = Path(tempdir) / "my-project"
            selected.mkdir()
            with patch.dict("os.environ", {"DISPLAY": ":0"}, clear=False):
                with patch("runtime.web.folder_picker.shutil.which", side_effect=lambda cmd: cmd if cmd == "zenity" else None):
                    with patch("runtime.web.folder_picker.subprocess.run") as run:
                        run.return_value.returncode = 0
                        run.return_value.stdout = f"{selected}\n"
                        result = pick_folder_native(initial_dir=Path(tempdir))
            self.assertTrue(result.ok)
            self.assertEqual(result.path, str(selected.resolve()))

    def test_cancelled_selection(self) -> None:
        with patch.dict("os.environ", {"DISPLAY": ":0"}, clear=False):
            with patch("runtime.web.folder_picker.shutil.which", side_effect=lambda cmd: cmd if cmd == "zenity" else None):
                with patch("runtime.web.folder_picker.subprocess.run") as run:
                    run.return_value.returncode = 1
                    run.return_value.stdout = ""
                    result = pick_folder_native()
        self.assertFalse(result.ok)
        self.assertIn("cancelada", result.message.lower())
