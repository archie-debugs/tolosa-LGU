from fastapi.testclient import TestClient

import Backends.backend.main as main
from Backends.backend import models
from Backends.backend.core import get_password_hash
from Backends.backend.database import SessionLocal, engine

import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

from frontend.admin.settings import build_employee_settings_view, build_super_admin_settings_view
from frontend.admin.users_roles import EMPLOYEE_PERMISSION_GROUPS
from tests.test_account_menu_ui import DummyPage, walk

models.Base.metadata.create_all(bind=engine)

SYSTEM_ENDPOINTS = [
    ("GET", "/system-settings", None),
    ("PUT", "/system-settings", {"settings": {"maintenance_mode": False}}),
    ("GET", "/system-health", None),
    ("GET", "/storage/diagnostics", None),
    ("POST", "/storage/cleanup-temp", {"confirm": True}),
]


def reset_db():
    with SessionLocal() as db:
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()


def add_user(username, role, permissions):
    with SessionLocal() as db:
        db.add(models.User(
            username=username,
            hashed_password=get_password_hash("pw123"),
            role=role,
            permissions=str(permissions),
            status="Active",
            is_active=True,
        ))
        db.commit()


def headers_for(client, username):
    response = client.post("/auth/login", data={"username": username, "password": "pw123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_system_endpoints_refuse_an_employee_even_with_the_system_settings_permission():
    reset_db()
    add_user("admin", "Super Administrator", ["*"])
    add_user("clerk", "Employee", ["view_documents", "modify_system_settings"])
    add_user("member", "SB Member", ["view_documents", "modify_system_settings"])
    client = TestClient(main.app)

    for username in ("clerk", "member"):
        headers = headers_for(client, username)
        for method, path, body in SYSTEM_ENDPOINTS:
            response = client.request(method, path, headers=headers, json=body)
            assert response.status_code == 403, (username, path, response.text)

    for method, path, body in SYSTEM_ENDPOINTS:
        assert client.request(method, path, json=body).status_code == 403, path

    admin = headers_for(client, "admin")
    for method, path, body in SYSTEM_ENDPOINTS:
        response = client.request(method, path, headers=admin, json=body)
        assert response.status_code == 200, (path, response.text)


def test_system_health_reports_the_migration_version_key():
    reset_db()
    add_user("admin", "Super Administrator", ["*"])
    client = TestClient(main.app)

    payload = client.get("/system-health", headers=headers_for(client, "admin")).json()

    assert "migration_version" in payload


def test_employees_can_no_longer_be_granted_system_settings():
    labels = {label for group in EMPLOYEE_PERMISSION_GROUPS.values() for label in group}
    assert "Modify System Settings" not in labels


def words(control):
    """Every Text value and button label under `control`."""
    found = []
    for c in walk(control):
        if isinstance(c, ft.Text) and c.value:
            found.append(c.value)
        label = getattr(c, "text", None)
        if isinstance(label, str) and label:
            found.append(label)
        if isinstance(getattr(c, "content", None), str):
            found.append(c.content)
    return found


def buttons(control, label):
    return [c for c in walk(control) if isinstance(c, (ft.ElevatedButton, ft.OutlinedButton)) and label in words(c) + [getattr(c, "tooltip", None)]]


def surface_card(content, width=None, padding=24, expand=False):
    return ft.Container(content=content, padding=padding)


def section_header(title, subtitle, icon, accent_color):
    return ft.Column([ft.Text(title), ft.Text(subtitle)])


PROFILE = {
    "username": "ana", "full_name": "Ana Bautista", "email": "ana@example.com", "role": "Employee",
    "office": "Treasury Office", "status": "Active", "last_login": "2026-10-20T01:00:00+00:00",
}

ADMIN_SECTIONS = ["Administration", "Security & Sessions", "System Configuration", "System Information",
                  "User & Permission Management", "Office Management", "Audit Logs", "Active Sessions"]


class FakeApi:
    def __init__(self, fail=()):
        self.calls = []
        self.fail = set(fail)

    def __call__(self, method, path, **kwargs):
        self.calls.append((method, path))
        if path in self.fail:
            raise Exception("Super Administrator access required")
        if path == "/system-settings":
            return {"settings": {"organization_name": "LGU Tolosa", "maintenance_mode": False}}
        if path == "/system-health":
            return {"status": "operational", "migration_version": "a1b2c3", "maintenance_mode": False,
                    "components": {"database": {"status": "operational"}, "storage": {"status": "operational"}}}
        return {}


def employee_view(**overrides):
    actions = []
    view = build_employee_settings_view(
        DummyPage(), surface_card, section_header,
        profile={**PROFILE, **overrides},
        change_password=lambda: actions.append("password"),
        edit_profile=lambda: actions.append("profile"),
    )
    return view, actions


def admin_view(api=None, pages=("Users & Roles", "Active Sessions", "Audit Logs", "Settings")):
    opened = []
    view = build_super_admin_settings_view(
        DummyPage(), surface_card, section_header,
        api=api or FakeApi(),
        profile={**PROFILE, "role": "Super Administrator", "office": None},
        change_password=lambda: None,
        edit_profile=lambda: None,
        two_step=ft.Text("Two-step login"),
        open_page=opened.append,
        pages=set(pages),
    )
    return view, opened


def test_employee_settings_show_profile_password_security_and_preferences_only():
    view, actions = employee_view()
    shown = words(view)

    for section in ["My Profile", "Change Password", "Personal Security", "Preferences"]:
        assert section in shown
    assert "Treasury Office" in shown and "Employee" in shown
    for admin_only in ADMIN_SECTIONS + ["Two-step login", "Migration version"]:
        assert admin_only not in shown

    buttons(view, "Change password")[0].on_click(None)
    buttons(view, "Edit profile")[0].on_click(None)
    assert actions == ["password", "profile"]


def test_employee_settings_have_no_fields_for_role_office_or_permissions():
    view, _ = employee_view()

    assert not [c for c in walk(view) if isinstance(c, (ft.TextField, ft.Dropdown, ft.Switch, ft.Checkbox))]


def test_employee_without_an_office_sees_not_assigned():
    view, _ = employee_view(office=None)

    assert "Not assigned" in words(view)


def test_super_admin_settings_show_every_section_and_system_information():
    api = FakeApi()
    view, _ = admin_view(api)
    shown = words(view)

    for section in ["My Profile"] + ADMIN_SECTIONS + ["Preferences", "Two-step login"]:
        assert section in shown
    assert "a1b2c3" in shown
    assert ("GET", "/system-settings") in api.calls and ("GET", "/system-health") in api.calls


def test_super_admin_links_open_the_existing_pages_instead_of_duplicating_them():
    view, opened = admin_view()

    for label in ["Users & Roles", "Active Sessions", "Audit Logs"]:
        buttons(view, f"Open {label}")[0].on_click(None)

    assert opened == ["Users & Roles", "Active Sessions", "Audit Logs"]


def test_super_admin_links_skip_pages_missing_from_the_sidebar():
    view, _ = admin_view(pages=("Settings",))

    assert "Audit Logs" not in words(view)
    assert not buttons(view, "Open Users & Roles")


def test_refused_system_calls_show_an_error_instead_of_values():
    view, _ = admin_view(FakeApi(fail={"/system-settings", "/system-health"}))
    shown = " ".join(words(view))

    assert "Unable to load system settings" in shown
    assert "Unable to load system information" in shown
    assert "a1b2c3" not in shown
