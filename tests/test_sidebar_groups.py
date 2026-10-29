import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

from frontend.admin.admin_shell import render_shell
from tests.test_account_menu_ui import DummyPage, click, clickable, texts, walk

TYPES = (("Ordinance", "Ordinances"), ("Resolution", "Resolutions"), ("Letter Request", "Letter Requests"))


def nav_items():
    def screen(name):
        return lambda: ft.Text(f"{name} screen")

    items = [(ft.Icons.DASHBOARD_OUTLINED, "Dashboard", screen("Dashboard"), None),
             (ft.Icons.DESCRIPTION_OUTLINED, "Documents", screen("Documents"), "Documents")]
    items += [(ft.Icons.GAVEL_OUTLINED, name, screen(name), "Documents", "Documents", name) for _, name in TYPES]
    items.append((ft.Icons.ARCHIVE_OUTLINED, "Archived Documents", screen("Archived Documents"), "Documents"))
    items += [(ft.Icons.GAVEL_OUTLINED, f"Archived {name}", screen(f"Archived {name}"), "Documents", "Archived Documents", name)
              for _, name in TYPES]
    return items


class Sidebar:
    def __init__(self, selected=0):
        self.page = DummyPage()
        render_shell(self.page, "ana", lambda: None, nav_items(), None, initial_selected_index=selected)

    @property
    def root(self):
        return self.page.controls[0]

    def labels(self):
        return texts(self.root.controls[0])

    def screen(self):
        return texts(self.root.controls[1])

    def tile(self, label):
        sidebar = self.root.controls[0]
        return next(c for c in walk(sidebar) if isinstance(c, ft.Container) and clickable(c) and label in texts(c)
                    and not str(c.data or "").startswith("toggle:"))

    def arrow(self, group):
        return next(c for c in walk(self.root.controls[0]) if isinstance(c, ft.Container) and c.data == f"toggle:{group}")


def test_the_type_pages_stay_hidden_until_their_group_opens():
    sidebar = Sidebar()

    assert "Documents" in sidebar.labels() and "Archived Documents" in sidebar.labels()
    assert "Ordinances" not in sidebar.labels()


def test_opening_documents_opens_its_types_and_only_those():
    sidebar = Sidebar()

    click(sidebar.tile("Documents"))

    labels = sidebar.labels()
    assert labels[labels.index("Documents") + 1:labels.index("Documents") + 4] == ["Ordinances", "Resolutions", "Letter Requests"]
    assert labels.count("Ordinances") == 1, "the archived group stays closed"
    assert "Documents screen" in sidebar.screen()


def test_a_type_page_keeps_its_group_open_and_shows_that_page():
    sidebar = Sidebar()
    click(sidebar.tile("Archived Documents"))

    click(sidebar.tile("Resolutions"))

    assert "Archived Resolutions screen" in sidebar.screen()
    assert sidebar.labels().count("Resolutions") == 1


def test_the_arrow_opens_and_closes_a_group_without_leaving_the_page():
    sidebar = Sidebar()

    click(sidebar.arrow("Documents"))
    assert "Ordinances" in sidebar.labels()
    assert "Dashboard screen" in sidebar.screen()

    click(sidebar.arrow("Documents"))
    assert "Ordinances" not in sidebar.labels()


def test_leaving_a_group_closes_it():
    sidebar = Sidebar(selected=1)
    assert "Ordinances" in sidebar.labels()

    click(sidebar.tile("Dashboard"))

    assert "Ordinances" not in sidebar.labels()
