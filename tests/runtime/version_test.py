"""Tests for the single-source version module."""

import unittest

from runtime.version import __version__


class VersionModuleTest(unittest.TestCase):
    def test_version_is_semver_string(self) -> None:
        parts = __version__.split(".")
        self.assertEqual(len(parts), 3)
        for part in parts:
            self.assertTrue(part.isdigit())


if __name__ == "__main__":
    unittest.main()
