import unittest

from runtime.shared.splash import build_splash_content


class SplashContentTest(unittest.TestCase):
    def test_builds_text_fallback_when_ascii_too_large(self) -> None:
        art = "\n".join("X" * 120 for _ in range(40))
        content = build_splash_content(available_width=40, available_height=12, ascii_art=art)
        self.assertEqual(content.mode, "text")
        self.assertTrue(content.lines)
