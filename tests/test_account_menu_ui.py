import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

from frontend.admin.admin_shell import MENU_SECTION, render_shell
from frontend.admin.change_password import open_change_password_dialog
from frontend.admin.edit_profile import open_edit_profile_dialog


class Storage:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value


class DummyPage:
    def __init__(self, width=1200):
        self.controls = []
        self.overlay = []
        self.theme_mode = ft.ThemeMode.LIGHT
        self.width = width
        self.height = 900
        self.client_storage = Storage()

    def clean(self):
        self.controls = []

    def add(self, *controls):
        self.controls.extend(controls)

    def update(self, *args):
        pass


def walk(control):
    if control is None:
        return
    yield control
    for child in getattr(control, "controls", None) or []:
        yield from walk(child)
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        yield from walk(content)
    for item in getattr(control, "items", None) or []:
        yield from walk(item)
    for action in getattr(control, "actions", None) or []:
        yield from walk(action)


def texts(control):
    return [c.value for c in walk(control) if isinstance(c, ft.Text) and c.value]


def find(root, kind):
    return [c for c in walk(root) if isinstance(c, kind)]


def clickable(control):
    handler = control.on_click
    return callable(handler) or bool(getattr(handler, "count", lambda: 0)())


def click(control):
    handler = control.on_click
    if callable(handler):
        handler(None)
    else:  # Flet 0.21 wraps Container handlers in an EventHandler
        for fn in list(handler._EventHandler__handlers):
            fn(None)


def menu_item(menu, label):
    return next(item for item in menu.items if label in texts(item))


class Shell:
    def __init__(self, width=1200, account=None, search=None, notifications=None):
        self.page = DummyPage(width)
        self.logged_out = []
        self.account_opened = []
        nav_items = [
            (ft.Icons.DESCRIPTION_OUTLINED, "Documents", lambda: ft.Text("Documents screen"), "Documents"),
            (ft.Icons.PERSON_OUTLINE, "My Account", self.account_view, MENU_SECTION),
            (ft.Icons.SETTINGS_OUTLINED, "Settings", lambda: ft.Text("Settings screen"), "Account"),
        ]
        self.password_dialogs = []
        render_shell(
            self.page, "ana", lambda: self.logged_out.append(True), nav_items, None,
            account=account if account is not None else {
                "name": "Ana Bautista", "role": "Employee", "office": "Treasury Office",
                "on_change_password": lambda: self.password_dialogs.append(True),
            },
            search=search,
            notifications=notifications,
        )

    def account_view(self):
        self.account_opened.append(True)
        return ft.Text("My Account screen")

    @property
    def root(self):
        return self.page.controls[0]

    @property
    def menu(self):
        return find(self.root, ft.PopupMenuButton)[0]

    def sidebar_labels(self):
        sidebar = self.root.controls[0]
        return texts(sidebar)

    def screen_texts(self):
        return texts(self.root.controls[1])


def test_profile_menu_shows_who_is_signed_in_and_the_account_actions():
    shell = Shell()

    labels = [texts(item) for item in shell.menu.items]
    flat = [text for item in labels for text in item]
    assert "Ana Bautista" in flat
    assert "Employee · Treasury Office" in flat
    for action in ("My account", "Change password", "Night mode", "Log out"):
        assert action in flat
    assert flat.index("Log out") == len(flat) - 1
    assert "AB" in texts(shell.menu.content)
    assert "Ana Bautista" in texts(shell.menu.content)


def test_sidebar_no_longer_holds_log_out_or_my_account():
    labels = Shell().sidebar_labels()

    assert "Log out" not in labels
    assert "My Account" not in labels
    assert "Documents" in labels and "Settings" in labels


def test_menu_actions_reach_the_account_screen_password_dialog_and_log_out():
    shell = Shell()

    menu_item(shell.menu, "My account").on_click(None)
    assert shell.account_opened
    assert "My Account screen" in shell.screen_texts()

    menu_item(shell.menu, "Change password").on_click(None)
    assert shell.password_dialogs == [True]

    menu_item(shell.menu, "Log out").on_click(None)
    assert shell.logged_out == [True]


def test_night_mode_moves_into_the_menu_and_is_remembered():
    shell = Shell()
    assert not find(shell.root, ft.Switch)

    menu_item(shell.menu, "Night mode").on_click(None)

    assert shell.page.theme_mode == ft.ThemeMode.DARK
    assert shell.page.client_storage.get("sb_night_mode") is True
    menu_item(shell.menu, "Night mode").on_click(None)
    assert shell.page.theme_mode == ft.ThemeMode.LIGHT


def test_settings_page_has_no_night_mode_switch():
    shell = Shell()

    settings_tile = next(c for c in walk(shell.root.controls[0]) if isinstance(c, ft.Container) and clickable(c) and texts(c) == ["Settings"])
    click(settings_tile)

    assert "Settings screen" in shell.screen_texts()
    assert not find(shell.root, ft.Switch)


def test_phone_width_shows_only_the_initials():
    shell = Shell(width=390)

    button = texts(shell.menu.content)
    assert "AB" in button
    assert "Ana Bautista" not in button


def test_menu_falls_back_to_the_username_without_a_profile():
    shell = Shell(account={})

    assert "ana" in texts(shell.menu.content)
    assert "AN" in texts(shell.menu.content)
    assert "Change password" not in [t for item in shell.menu.items for t in texts(item)]


class FakeApi:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def __call__(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if self.error:
            raise Exception(self.error)
        return {"message": "Your password has been changed."}


def password_dialog(api):
    page = DummyPage()
    dialog = ft.AlertDialog()
    open_change_password_dialog(page, dialog, api)
    current, new, confirm = find(dialog.content, ft.TextField)
    submit = next(b for b in walk(dialog) if "Change password" in texts(b) or getattr(b, "text", None) == "Change password")
    return dialog, (current, new, confirm), submit


def press(button):
    while getattr(button, "on_click", None) is None and getattr(button, "content", None) is not None:
        button = button.content
    button.on_click(None)


def test_change_password_checks_the_fields_before_calling_the_backend():
    api = FakeApi()
    dialog, (current, new, confirm), submit = password_dialog(api)
    assert dialog.open is True
    assert all(field.password for field in (current, new, confirm))

    press(submit)
    assert "Enter your current password." in texts(dialog.content)

    current.value, new.value, confirm.value = "pw123456", "newpass99", "newpass98"
    press(submit)
    assert "The new passwords do not match." in texts(dialog.content)

    new.value = confirm.value = "short"
    press(submit)
    assert "Use at least 8 characters." in texts(dialog.content)
    assert api.calls == []


def test_change_password_shows_the_backend_reason():
    api = FakeApi(error="Your current password is incorrect.")
    dialog, (current, new, confirm), submit = password_dialog(api)
    current.value, new.value, confirm.value = "wrong", "newpass99", "newpass99"

    press(submit)

    assert "Your current password is incorrect." in texts(dialog.content)
    assert dialog.open is True


def test_change_password_success_posts_and_confirms():
    api = FakeApi()
    dialog, (current, new, confirm), submit = password_dialog(api)
    current.value, new.value, confirm.value = "pw123456", "newpass99", "newpass99"

    press(submit)

    assert api.calls == [("POST", "/auth/me/password", {"json": {
        "current_password": "pw123456", "new_password": "newpass99", "confirm_password": "newpass99",
    }})]
    shown = texts(dialog)
    assert any("Your password has been changed." in text for text in shown)
    assert any("signed out" in text for text in shown)
    assert not find(dialog.content, ft.TextField)


class ProfileApi:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def __call__(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if self.error:
            raise Exception(self.error)
        return {"full_name": kwargs["json"]["full_name"], "email": kwargs["json"]["email"]}


def profile_dialog(api, saved):
    page = DummyPage()
    dialog = ft.AlertDialog()
    open_edit_profile_dialog(page, dialog, api, {"full_name": "Ana Bautista", "email": "ana@example.com", "username": "ana"},
                             on_saved=saved.append)
    name, email = find(dialog.content, ft.TextField)
    return dialog, name, email


def test_edit_profile_saves_through_the_own_account_endpoint():
    api, saved = ProfileApi(), []
    dialog, name, email = profile_dialog(api, saved)
    assert (name.value, email.value) == ("Ana Bautista", "ana@example.com")

    name.value = "Ana B. Reyes"
    press(next(b for b in walk(dialog) if "Save changes" in texts(b) or getattr(b, "text", None) == "Save changes"))

    assert api.calls == [("PUT", "/auth/me", {"json": {"full_name": "Ana B. Reyes", "email": "ana@example.com"}})]
    assert saved == [{"full_name": "Ana B. Reyes", "email": "ana@example.com"}]
    assert dialog.open is False


def test_edit_profile_checks_fields_and_shows_the_backend_reason():
    api, saved = ProfileApi(error="Enter a valid email address."), []
    dialog, name, email = profile_dialog(api, saved)
    save = next(b for b in walk(dialog) if "Save changes" in texts(b) or getattr(b, "text", None) == "Save changes")

    name.value = " "
    press(save)
    assert "Full name is required." in texts(dialog.content)
    assert api.calls == []

    name.value, email.value = "Ana", "nope"
    press(save)
    assert "Enter a valid email address." in texts(dialog.content)
    assert dialog.open is True and saved == []


def resize(page, width):
    page.width = width
    handler = getattr(page, "on_resized", None) or getattr(page, "on_resize", None)
    handler(None)


def menu_button(shell):
    return next((b for b in find(shell.root, ft.IconButton) if b.icon == ft.Icons.MENU), None)


def drawer_open(shell):
    stack = shell.root
    return isinstance(stack, ft.Stack) and stack.controls[2].visible is True


def test_desktop_keeps_the_sidebar_beside_the_screen():
    shell = Shell(width=1280)

    assert isinstance(shell.root, ft.Row)
    assert menu_button(shell) is None
    assert "Documents" in texts(shell.root.controls[0])


def test_phone_width_folds_the_sidebar_into_a_drawer():
    shell = Shell(width=390)

    assert isinstance(shell.root, ft.Stack)
    assert not drawer_open(shell)
    button = menu_button(shell)
    assert button is not None

    button.on_click(None)
    assert drawer_open(shell)
    assert "Documents" in texts(shell.root.controls[2])

    documents_tile = next(c for c in walk(shell.root.controls[2]) if isinstance(c, ft.Container) and clickable(c) and texts(c) == ["Documents"])
    click(documents_tile)
    assert not drawer_open(shell)
    assert "Documents screen" in texts(shell.root.controls[0])


def test_tapping_outside_the_drawer_closes_it():
    shell = Shell(width=390)
    menu_button(shell).on_click(None)

    click(shell.root.controls[1])

    assert not drawer_open(shell)


def test_resizing_switches_between_sidebar_and_drawer_and_keeps_the_screen():
    shell = Shell(width=1280)
    menu_item(shell.menu, "My account").on_click(None)

    resize(shell.page, 390)
    assert isinstance(shell.root, ft.Stack)
    assert "My Account screen" in texts(shell.root.controls[0])
    assert "Ana Bautista" not in texts(shell.menu.content)

    resize(shell.page, 1280)
    assert isinstance(shell.root, ft.Row)
    assert "My Account screen" in texts(shell.root.controls[1])
    assert "Ana Bautista" in texts(shell.menu.content)


def fire(control, event):
    handler = getattr(control, event)
    if callable(handler):
        handler(None)
    else:  # Flet 0.21 wraps some handlers in an EventHandler
        for fn in list(handler._EventHandler__handlers):
            fn(None)


class Search:
    def __init__(self, items=None, error=None):
        self.queries = []
        self.opened = []
        self.items = items if items is not None else [
            {"id": 1, "tracking_number": "DOC-000001", "title": "Budget Ordinance", "document_type": "Ordinance",
             "current_office": "Records Office", "archived": False},
            {"id": 9, "tracking_number": "DOC-000009", "title": "Old Budget", "document_type": None,
             "current_office": None, "archived": True},
        ]
        self.error = error

    def find(self, text):
        self.queries.append(text)
        if self.error:
            raise Exception(self.error)
        return self.items

    def config(self):
        return {"find": self.find, "open": self.opened.append}


def search_box(shell):
    return next(c for c in find(shell.root, ft.TextField) if c.hint_text == "Search documents, tracking number, or title...")


def results_panel(shell):
    return next(c for c in walk(shell.root) if getattr(c, "data", None) == "search-results")


def run_search(shell, text):
    box = search_box(shell)
    box.value = text
    fire(box, "on_submit")


def test_no_search_box_without_a_search_function():
    shell = Shell()
    assert not [c for c in find(shell.root, ft.TextField) if c.hint_text == "Search documents, tracking number, or title..."]


def test_search_lists_matches_under_the_bar_and_opens_one():
    search = Search()
    shell = Shell(search=search.config())
    assert results_panel(shell).visible is False

    run_search(shell, "  budget ")

    assert search.queries == ["budget"]
    panel = results_panel(shell)
    assert panel.visible is True
    shown = texts(panel)
    assert "DOC-000001" in shown and "Budget Ordinance" in shown
    assert "Ordinance · Records Office" in shown
    assert "Archived" in shown

    row = next(c for c in walk(panel) if isinstance(c, ft.Container) and clickable(c) and "DOC-000001" in texts(c))
    click(row)
    assert search.opened == [search.items[0]]
    assert results_panel(shell).visible is False


def test_search_explains_no_matches_errors_and_short_queries():
    search = Search(items=[])
    shell = Shell(search=search.config())

    run_search(shell, "zzz")
    assert any("No documents match" in t and "zzz" in t for t in texts(results_panel(shell)))

    run_search(shell, "a")
    assert search.queries == ["zzz"]
    assert any("at least 2 characters" in t for t in texts(results_panel(shell)))

    shell_error = Shell(search=Search(error="Permission denied").config())
    run_search(shell_error, "budget")
    assert "Permission denied" in texts(results_panel(shell_error))


def test_search_results_can_be_closed():
    shell = Shell(search=Search().config())
    run_search(shell, "budget")

    close = next(b for b in find(results_panel(shell), ft.IconButton) if b.icon == ft.Icons.CLOSE)
    close.on_click(None)

    assert results_panel(shell).visible is False


def test_phone_width_search_box_fills_the_bar():
    shell = Shell(width=390, search=Search().config())

    box = search_box(shell)
    assert box.expand is True
    run_search(shell, "budget")
    assert results_panel(shell).visible is True


class Notifications:
    def __init__(self, unread=2, error=None):
        self.loads = 0
        self.seen_calls = 0
        self.opened = []
        self.error = error
        self.items = [
            {"id": "incoming:1", "kind": "incoming", "document_id": 1, "tracking_number": "DOC-000001", "title": "Budget",
             "message": "Sent to your office by Records Office. Waiting for receipt.", "at": "2026-10-20T08:00:00+00:00", "unread": True},
            {"id": "overdue:2", "kind": "overdue", "document_id": 2, "tracking_number": "DOC-000002", "title": "Market fees",
             "message": "Overdue by 1 day.", "at": "2026-10-19T16:00:00+00:00", "unread": unread > 1},
        ]
        self.unread = unread

    def load(self):
        self.loads += 1
        if self.error:
            raise Exception(self.error)
        return {"unread": self.unread, "items": self.items}

    def seen(self):
        self.seen_calls += 1
        self.unread = 0
        for item in self.items:
            item["unread"] = False

    def config(self):
        return {"load": self.load, "seen": self.seen, "open": self.opened.append}


def bell(shell):
    return next((b for b in find(shell.root, ft.IconButton) if b.icon in (ft.Icons.NOTIFICATIONS_OUTLINED, ft.Icons.NOTIFICATIONS_ACTIVE)), None)


def badge_texts(shell):
    holder = next((c for c in walk(shell.root) if getattr(c, "data", None) == "notification-badge"), None)
    return texts(holder) if holder is not None and holder.visible is not False else []


def notification_panel(shell):
    return next(c for c in walk(shell.root) if getattr(c, "data", None) == "notifications-panel")


def test_no_bell_without_notifications():
    assert bell(Shell()) is None


def test_bell_shows_the_unread_count_and_refreshes_on_every_screen_change():
    feed = Notifications()
    shell = Shell(notifications=feed.config())

    assert badge_texts(shell) == ["2"]
    loads = feed.loads
    tile = next(c for c in walk(shell.root.controls[0]) if isinstance(c, ft.Container) and clickable(c) and texts(c) == ["Documents"])
    click(tile)
    assert feed.loads == loads + 1


def test_opening_the_bell_lists_items_marks_them_read_and_opens_a_document():
    feed = Notifications()
    shell = Shell(notifications=feed.config())
    assert notification_panel(shell).visible is False

    bell(shell).on_click(None)

    panel = notification_panel(shell)
    assert panel.visible is True
    shown = texts(panel)
    assert "DOC-000001" in shown and "Sent to your office by Records Office. Waiting for receipt." in shown
    assert "Overdue by 1 day." in shown
    assert feed.seen_calls == 1
    assert badge_texts(shell) == []

    row = next(c for c in walk(panel) if isinstance(c, ft.Container) and clickable(c) and "DOC-000002" in texts(c))
    click(row)
    assert feed.opened == [feed.items[1]]
    assert notification_panel(shell).visible is False


def test_nothing_to_show_and_load_errors_are_explained():
    feed = Notifications(unread=0)
    feed.items = []
    shell = Shell(notifications=feed.config())
    assert badge_texts(shell) == []
    bell(shell).on_click(None)
    assert "Nothing needs your attention right now." in texts(notification_panel(shell))
    assert feed.seen_calls == 0

    broken = Shell(notifications=Notifications(error="Backend unreachable").config())
    assert badge_texts(broken) == []
    bell(broken).on_click(None)
    assert any("Backend unreachable" in t for t in texts(notification_panel(broken)))


def test_large_counts_are_capped():
    feed = Notifications(unread=42)
    shell = Shell(notifications=feed.config())
    assert badge_texts(shell) == ["9+"]
