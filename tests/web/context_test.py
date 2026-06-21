import unittest

from runtime.web.context import page_path, view_route_to_name


class WebContextRouteTest(unittest.TestCase):
    def test_project_page_maps_to_home_nav_view(self) -> None:
        self.assertEqual(view_route_to_name("project_page"), "project_home")

    def test_project_page_path(self) -> None:
        self.assertEqual(page_path("project_page"), "/project-page")


if __name__ == "__main__":
    unittest.main()
