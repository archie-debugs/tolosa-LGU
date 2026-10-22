"""Settings: one page for Super Administrators and one for Employees.

The backend decides what each role may do; these pages only show the controls the role can use.
Nobody changes their own role, office or permissions here: a Super Administrator sets those in Users & Roles.
"""

import flet as ft

from frontend.admin.tracking_ui import TrackingWidgets, local_time

LABEL_WIDTH = 150

DEFAULT_SYSTEM_SETTINGS = {
    "organization_name": "LGU Tolosa",
    "system_name": "LGU Tolosa Legislative Document Tracking System",
    "public_portal_enabled": True,
    "maintenance_mode": False,
    "session_timeout_minutes": 60,
    "upload_max_size_mb": 25,
}

# Pages a Super Administrator reaches from Settings: (icon, heading, what it is for, sidebar label).
ADMIN_PAGES = [
    (ft.Icons.PEOPLE_ALT_OUTLINED, "User & Permission Management",
     "Create employee accounts, assign roles and offices, and set permissions.", "Users & Roles"),
    (ft.Icons.LOCATION_CITY_OUTLINED, "Office Management",
     "Add, edit, activate and deactivate offices (in Users & Roles).", "Users & Roles"),
    (ft.Icons.SECURITY_OUTLINED, "Active Sessions",
     "See who is signed in and sign out a session.", "Active Sessions"),
    (ft.Icons.HISTORY_OUTLINED, "Audit Logs",
     "Review administrative and security events.", "Audit Logs"),
    (ft.Icons.CAMPAIGN_OUTLINED, "Homepage Announcements",
     "Edit the announcements shown on the public homepage.", "Announcements"),
]


def format_datetime(value):
    local = local_time(value)
    return local.strftime("%b %d, %Y %I:%M %p") if local else "Not recorded"


def build_employee_settings_view(page, surface_card, section_header, *, profile, change_password, edit_profile):
    """`profile` is GET /auth/me. `change_password()` and `edit_profile()` open the existing dialogs."""
    ui = TrackingWidgets(page)
    return _settings_page(surface_card, section_header, "Your profile, password and preferences.", [
        _profile_card(ui, surface_card, section_header, profile, edit_profile,
                      note="Your role, office and permissions are managed by a Super Administrator."),
        _card(surface_card, section_header, "Change Password", "Keep your account secure.", ft.Icons.LOCK_RESET, [
            _row(ui, "Password", ft.OutlinedButton("Change password", icon=ft.Icons.LOCK_RESET, on_click=lambda _: change_password())),
            ui.hint("Changing your password signs you out on every other device."),
        ]),
        _card(surface_card, section_header, "Personal Security", "Your recent sign-in activity.", ft.Icons.SHIELD_OUTLINED, [
            _row(ui, "Last login", _value(ui, format_datetime(profile.get("last_login")))),
            _row(ui, "Account status", _value(ui, (profile.get("status") or "Active").title())),
            ui.hint("If you see a sign-in you don't recognise, change your password and tell a Super Administrator."),
        ]),
        _preferences_card(ui, surface_card, section_header),
    ])


def build_super_admin_settings_view(page, surface_card, section_header, *, api, profile, change_password, edit_profile,
                                    two_step, open_page, pages):
    """`api(method, path, **kwargs)` returns parsed JSON or raises with the backend's detail.
    `two_step` is the two-step login row. `open_page(label)` opens a sidebar page; `pages` are the labels this user has."""
    ui = TrackingWidgets(page)
    links = [entry for entry in ADMIN_PAGES if entry[3] in pages]
    return _settings_page(surface_card, section_header, "Your account, administration and system configuration.", [
        _profile_card(ui, surface_card, section_header, profile, edit_profile),
        _card(surface_card, section_header, "Administration", "User, office, session and audit management have their own pages.",
              ft.Icons.ADMIN_PANEL_SETTINGS_OUTLINED, [_admin_link(ui, entry, open_page) for entry in links]),
        _card(surface_card, section_header, "Security & Sessions", "Your password, two-step login and sign-ins.", ft.Icons.SHIELD_OUTLINED, [
            _row(ui, "Password", ft.OutlinedButton("Change password", icon=ft.Icons.LOCK_RESET, on_click=lambda _: change_password())),
            two_step,
            _row(ui, "Last login", _value(ui, format_datetime(profile.get("last_login")))),
            ui.hint("Changing your password signs you out on every other device. See everyone's sessions in Active Sessions."),
        ]),
        _system_configuration_card(page, ui, surface_card, section_header, api),
        _system_information_card(ui, surface_card, section_header, api),
        _preferences_card(ui, surface_card, section_header),
    ])


def _settings_page(surface_card, section_header, subtitle, cards):
    return ft.Column([
        surface_card(section_header("Settings", subtitle, ft.Icons.SETTINGS_OUTLINED, ft.Colors.BLUE_700), padding=18),
        *cards,
    ], spacing=16)


def _card(surface_card, section_header, title, subtitle, icon, rows):
    return surface_card(ft.Column([
        section_header(title, subtitle, icon, ft.Colors.BLUE_700),
        ft.Divider(height=1),
        *rows,
    ], spacing=12), padding=18)


def _row(ui, label, control):
    return ft.Row([
        ft.Text(label, size=12, color=ui.muted_color(), width=LABEL_WIDTH),
        control,
    ], spacing=12, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def _value(ui, text, color=None):
    return ft.Text(text, size=13, weight=ft.FontWeight.W_500, color=color or ui.body_color())


def _profile_card(ui, surface_card, section_header, profile, edit_profile, note=None):
    rows = [
        _row(ui, "Full name", _value(ui, profile.get("full_name") or "Not provided")),
        _row(ui, "Username", _value(ui, profile.get("username") or "Not provided")),
        _row(ui, "Email", _value(ui, profile.get("email") or "Not provided")),
        _row(ui, "Role", _value(ui, profile.get("role") or "Not provided")),
        _row(ui, "Office", _value(ui, profile.get("office") or "Not assigned")),
        _row(ui, "Account created", _value(ui, format_datetime(profile.get("created_at")))),
        ft.Row([
            ft.ElevatedButton("Edit profile", icon=ft.Icons.EDIT_OUTLINED, on_click=lambda _: edit_profile()),
        ], alignment=ft.MainAxisAlignment.END),
    ]
    hint = "You can change your name and email."
    if note:
        hint = f"{hint} {note}"
    rows.insert(-1, ui.hint(hint))
    return _card(surface_card, section_header, "My Profile", "Your account information.", ft.Icons.PERSON_OUTLINE, rows)


def _preferences_card(ui, surface_card, section_header):
    return _card(surface_card, section_header, "Preferences", "How the workspace looks on this device.", ft.Icons.PALETTE_OUTLINED, [
        _row(ui, "Night mode", _value(ui, "Switch it on or off from your profile menu at the top right.")),
    ])


def _admin_link(ui, entry, open_page):
    icon, title, description, label = entry
    return ft.Row([
        ft.Icon(icon, size=20, color=ft.Colors.BLUE_700),
        ft.Column([
            ft.Text(title, size=13, weight=ft.FontWeight.W_600, color=ui.heading_color()),
            ui.hint(description),
        ], spacing=2, expand=True),
        ft.OutlinedButton("Open", on_click=lambda _: open_page(label), tooltip=f"Open {label}"),
    ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def _system_configuration_card(page, ui, surface_card, section_header, api):
    values = dict(DEFAULT_SYSTEM_SETTINGS)
    message = ft.Text("", size=12, visible=False)
    try:
        stored = api("GET", "/system-settings").get("settings") or {}
        values.update({key: value for key, value in stored.items() if key in values})
    except Exception as exc:
        message.value = f"Unable to load system settings: {exc}"
        message.color = ft.Colors.RED_700
        message.visible = True

    org_name = ft.TextField(label="Organization Name", value=str(values["organization_name"]), width=360)
    system_name = ft.TextField(label="System Name", value=str(values["system_name"]), width=360)
    maintenance = ft.Switch(label="Maintenance Mode", value=bool(values["maintenance_mode"]))
    public_portal = ft.Switch(label="Public Portal Enabled", value=bool(values["public_portal_enabled"]))
    session_timeout = ft.TextField(label="Session Timeout (minutes)", value=str(values["session_timeout_minutes"]), width=180)
    upload_size = ft.TextField(label="Max Upload Size (MB)", value=str(values["upload_max_size_mb"]), width=180)

    def save(_):
        try:
            api("PUT", "/system-settings", json={"settings": {
                "organization_name": (org_name.value or "").strip() or DEFAULT_SYSTEM_SETTINGS["organization_name"],
                "system_name": (system_name.value or "").strip() or DEFAULT_SYSTEM_SETTINGS["system_name"],
                "maintenance_mode": bool(maintenance.value),
                "public_portal_enabled": bool(public_portal.value),
                "session_timeout_minutes": int(str(session_timeout.value or "60").strip() or "60"),
                "upload_max_size_mb": int(str(upload_size.value or "25").strip() or "25"),
            }})
            message.value, message.color = "System settings saved.", ft.Colors.GREEN_700
        except ValueError:
            message.value, message.color = "Session timeout and upload size must be whole numbers.", ft.Colors.RED_700
        except Exception as exc:
            message.value, message.color = f"Unable to save system settings: {str(exc)[:180]}", ft.Colors.RED_700
        message.visible = True
        page.update()

    def group(text):
        return ft.Text(text, size=13, weight=ft.FontWeight.W_600, color=ui.body_color())

    return _card(surface_card, section_header, "System Configuration", "Application-wide settings.", ft.Icons.SETTINGS_APPLICATIONS_OUTLINED, [
        group("Organization Information"),
        ft.Row([org_name, system_name], wrap=True, spacing=12),
        group("Operational Controls"),
        ft.Row([maintenance, public_portal], wrap=True, spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        group("Storage and Session Settings"),
        ft.Row([session_timeout, upload_size], wrap=True, spacing=12),
        message,
        ft.Row([
            ft.ElevatedButton("Save system settings", icon=ft.Icons.SAVE_OUTLINED, on_click=save),
        ], alignment=ft.MainAxisAlignment.END),
    ])


def _system_information_card(ui, surface_card, section_header, api):
    def status_text(status):
        status = str(status or "unknown")
        color = ft.Colors.GREEN_700 if status in {"operational", "ok"} else ft.Colors.AMBER_800 if status in {"warning", "manual"} else ft.Colors.RED_700
        return _value(ui, status.title(), color)

    try:
        health = api("GET", "/system-health")
    except Exception as exc:
        rows = [_row(ui, "Backend", status_text("unavailable")), ui.hint(f"Unable to load system information: {exc}")]
    else:
        components = health.get("components") or {}
        rows = [
            _row(ui, "Overall", status_text(health.get("status"))),
            _row(ui, "Backend", status_text("operational")),
            _row(ui, "Database", status_text((components.get("database") or {}).get("status"))),
            _row(ui, "Document storage", status_text((components.get("storage") or {}).get("status"))),
            _row(ui, "Migration version", _value(ui, health.get("migration_version") or "Not recorded")),
            _row(ui, "Maintenance mode", _value(ui, "On" if health.get("maintenance_mode") else "Off")),
            _row(ui, "Checked", _value(ui, format_datetime(health.get("generated_at")))),
        ]
    return _card(surface_card, section_header, "System Information", "Backend, database and migration status.", ft.Icons.INFO_OUTLINE, rows)
