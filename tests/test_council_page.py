import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

from frontend.admin.council import build_members_committees_view
from tests.test_account_menu_ui import DummyPage, walk as walk_controls
from tests.test_settings_pages import surface_card

TERMS = [
    {"id": 2, "name": "13th Sangguniang Bayan", "starts_on": "2025-07-01", "ends_on": "2028-06-30", "is_current": True},
    {"id": 1, "name": "12th Sangguniang Bayan", "starts_on": "2022-07-01", "ends_on": "2025-06-30", "is_current": False},
]
MEMBERS = {
    2: [{"id": 10, "term_id": 2, "full_name": "Hon. Maria Santos", "position": "Vice Mayor", "user_id": 7, "username": "msantos",
         "left_on": None, "is_active": True},
        {"id": 11, "term_id": 2, "full_name": "Hon. Former", "position": "Regular Member", "user_id": None, "username": None,
         "left_on": "2026-01-15", "is_active": False}],
    1: [{"id": 3, "term_id": 1, "full_name": "Hon. Past Member", "position": "Regular Member", "user_id": None, "username": None,
         "left_on": None, "is_active": True}],
}
COMMITTEES = [{"id": 5, "name": "Committee on Health", "chair_member_id": 10, "chair_name": "Hon. Maria Santos", "is_active": True}]


class FakeApi:
    def __init__(self, users=None):
        self.calls = []
        self.users = users

    def __call__(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs.get("json")))
        if path == "/council/terms" and method == "GET":
            return TERMS
        if path.startswith("/council/members?term_id="):
            return MEMBERS[int(path.rsplit("=", 1)[1])]
        if path == "/council/committees" and method == "GET":
            return COMMITTEES
        if path == "/auth/users":
            if self.users is None:
                raise Exception("Permission denied")
            return self.users
        return {"id": 99, **(kwargs.get("json") or {})}


def walk(control):
    """walk_controls, plus the rows and cells of data tables."""
    for item in walk_controls(control):
        yield item
        for row in getattr(item, "rows", None) or []:
            for cell in row.cells:
                yield from walk(cell.content)


def build(api, can_manage=True):
    page = DummyPage()
    view = build_members_committees_view(page, surface_card, api, can_manage=can_manage)
    return page, view


def texts(control):
    return [item.value for item in walk(control) if isinstance(item, ft.Text) and item.value]


def button(view, label):
    return next(item for item in walk(view) if getattr(item, "text", None) == label or getattr(item, "content", None) == label)


def dialog(page):
    return next(item for item in page.overlay if isinstance(item, ft.AlertDialog))


def test_it_opens_on_the_current_term_with_members_and_committees():
    page, view = build(FakeApi())
    shown = texts(view)

    assert "Hon. Maria Santos" in shown and "Vice Mayor · login: msantos" in shown
    assert "Left 2026-01-15" in shown
    assert "Hon. Past Member" not in shown
    assert "Committee on Health" in shown


def test_readers_see_the_roster_without_any_way_to_change_it():
    page, view = build(FakeApi(), can_manage=False)

    hidden = [item for item in walk(view) if isinstance(item, ft.Row) and not item.visible]
    assert hidden and all(not item.visible for item in hidden)
    assert not [item for item in walk(view) if isinstance(item, ft.IconButton)]


def test_adding_a_member_posts_to_the_selected_term_with_the_chosen_login():
    api = FakeApi(users=[{"id": 7, "username": "msantos", "role": "SB Member", "is_active": True}])
    page, view = build(api)

    button(view, "Add member").on_click(None)
    form = dialog(page)
    fields = [item for item in walk(form.content) if isinstance(item, (ft.TextField, ft.Dropdown))]
    name, position, login = fields[0], fields[1], fields[2]
    name.value, position.value, login.value = "Hon. Jose Cruz", "Regular Member", "7"
    next(action for action in form.actions if getattr(action, "text", None) == "Save" or getattr(action, "content", None) == "Save").on_click(None)

    assert ("POST", "/council/members", {"full_name": "Hon. Jose Cruz", "position": "Regular Member", "user_id": 7, "term_id": 2}) in api.calls
    assert form.open is False


def test_without_view_users_the_login_is_hidden_and_an_edit_keeps_the_linked_login():
    api = FakeApi(users=None)
    page, view = build(api)

    edit = next(item for item in walk(view) if isinstance(item, ft.IconButton) and item.tooltip == "Edit")
    edit.on_click(None)
    form = dialog(page)
    login = [item for item in walk(form.content) if isinstance(item, ft.Dropdown)][1]
    assert login.visible is False
    assert "Linking a login needs the View Users permission." in texts(form.content)
    next(action for action in form.actions if getattr(action, "text", None) == "Save" or getattr(action, "content", None) == "Save").on_click(None)

    assert ("PUT", "/council/members/10",
            {"full_name": "Hon. Maria Santos", "position": "Vice Mayor", "user_id": 7, "left_on": None}) in api.calls


def test_a_bad_date_is_reported_in_the_dialog_and_nothing_is_sent():
    api = FakeApi()
    page, view = build(api)

    button(view, "Add term").on_click(None)
    form = dialog(page)
    name, starts, ends = [item for item in walk(form.content) if isinstance(item, ft.TextField)]
    name.value, starts.value, ends.value = "14th Sangguniang Bayan", "July 2028", "2031-06-30"
    next(action for action in form.actions if getattr(action, "text", None) == "Save" or getattr(action, "content", None) == "Save").on_click(None)

    assert form.open is True
    assert "Starts on must be a date like 2025-07-01." in texts(form.content)
    assert not [call for call in api.calls if call[0] == "POST"]


def test_deactivating_a_committee_keeps_its_name_and_chair():
    api = FakeApi()
    page, view = build(api)

    next(item for item in walk(view) if isinstance(item, ft.IconButton) and item.tooltip == "Deactivate").on_click(None)

    assert ("PUT", "/council/committees/5", {"name": "Committee on Health", "chair_member_id": 10, "is_active": False}) in api.calls
