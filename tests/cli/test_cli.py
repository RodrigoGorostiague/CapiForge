import unittest
from unittest.mock import patch

from runtime.cli import _build_parser, main


class CliTest(unittest.TestCase):
    def test_parser_includes_web_command(self) -> None:
        parser = _build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["web", "--help"])

    def test_main_routes_web_command(self) -> None:
        with patch("runtime.cli._handle_web", return_value=0) as handle_web:
            result = main(["web", "--repo-root", "/tmp/demo"])
        self.assertEqual(result, 0)
        handle_web.assert_called_once_with(["--repo-root", "/tmp/demo"])

    def test_parser_no_longer_includes_tui_command(self) -> None:
        parser = _build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["tui"])
