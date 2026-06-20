import io
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from runtime.cli import _build_parser, _handle_tui, main


class CliTest(unittest.TestCase):
    def test_parser_includes_tui_command(self) -> None:
        parser = _build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["tui", "--help"])

    def test_main_routes_tui_command(self) -> None:
        with patch("runtime.cli._handle_tui", return_value=0) as handle_tui:
            result = main(["tui", "--repo-root", "/tmp/demo"])
        self.assertEqual(result, 0)
        handle_tui.assert_called_once_with(["--repo-root", "/tmp/demo"])

    def test_handle_tui_requires_tty(self) -> None:
        buffer = io.StringIO()
        with patch("sys.stdin.isatty", return_value=False), patch("sys.stdout.isatty", return_value=False):
            with redirect_stderr(buffer):
                result = _handle_tui([])
        self.assertEqual(result, 1)
        self.assertIn("interactive terminal", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
