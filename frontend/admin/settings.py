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


def initials(profile):
    name = profile.get("full_name") or profile.get("username") or "?"
    return "".join(part[0] for part in name.split()[:2]).upper() or "?"


def build_employee_settings_view(page, *, profile, change_password, edit_profile):
    """`profile` is GET /auth/me. `change_password()` and `edit_profile()` open the existing dialogs."""
    ui = TrackingWidgets(page)
    return _settings_page(ui, "Your profile, password and preferences.", left=[
        _profile_card(ui, profile, edit_profile,
                      note="Your role, office and permissions are managed by a Super Administrator."),
        _preferences_card(ui),
    ], right=[
        _card(ui, "Change Password", "Keep your account secure.", ft.Icons.LOCK_RESET, [
            _row(ui, "Password", ft.OutlinedButton("Change password", icon=ft.Icons.LOCK_RESET, on_click=lambda _: change_password())),
            _note(ui, "Changing your password signs you out on every other device."),
        ]),
        _card(ui, "Personal Security", "Your recent sign-in activity.", ft.Icons.SHIELD_OUTLINED, [
            _row(ui, "Last login", _value(ui, format_datetime(profile.get("last_login")))),
            _row(ui, "Account status", _status(ui, profile.get("status") or "Active")),
            _note(ui, "If you see a sign-in you don't recognise, change your password and tell a Super Administrator.", ft.Icons.WARNING_AMBER),
        ]),
    ])


def build_super_admin_settings_view(page, *, api, profile, change_password, edit_profile, two_step, open_page, pages):
    """`api(method, path, **kwargs)` returns parsed JSON or raises with the backend's detail.
    `two_step` is the two-step login row. `open_page(label)` opens a sidebar page; `pages` are the labels this user has."""
    ui = TrackingWidgets(page)
    links = [entry for entry in ADMIN_PAGES if entry[3] in pages]
    return _settings_page(ui, "Your account, administration and system configuration.", left=[
        _profile_card(ui, profile, edit_profile),
        _card(ui, "Security & Sessions", "Your password, two-step login and sign-ins.", ft.Icons.SHIELD_OUTLINED, [
            _row(ui, "Password", ft.OutlinedButton("Change password", icon=ft.Icons.LOCK_RESET, on_click=lambda _: change_password())),
            two_step,
            _row(ui, "Last login", _value(ui, format_datetime(profile.get("last_login")))),
            _note(ui, "Changing your password signs you out on every other device. See everyone's sessions in Active Sessions."),
        ]),
        _preferences_card(ui),
    ], right=[
        _card(ui, "Administration", "User, office, session and audit management have their own pages.",
              ft.Icons.ADMIN_PANEL_SETTINGS_OUTLINED, [_admin_link(ui, entry, open_page) for entry in links] or [
                  ui.empty_box("Your account has none of the administration pages.")]),
        _system_configuration_card(page, ui, api),
        _system_information_card(ui, api),
    ])


def _settings_page(ui, subtitle, left, right):
    return ft.Column([
        ui.banner("Settings", subtitle, ft.Icons.SETTINGS),
        ft.ResponsiveRow(
            [
                ft.Column(left, spacing=16, col={"xs": 12, "lg": 5}),
                ft.Column(right, spacing=16, col={"xs": 12, "lg": 7}),
            ],
            spacing=16,
            run_spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
    ], spacing=16)


def _card(ui, title, subtitle, icon, rows):
    return ft.Container(
        content=ft.Column([ui.card_title(title, icon, subtitle=subtitle), ft.Divider(height=1, color=ui.line_color()), *rows], spacing=14),
        padding=20,
        bgcolor=ui.card_color(),
        border=ft.border.all(1, ui.line_color()),
        border_radius=18,
    )


def _row(ui, label, control):
    return ft.Row([
        ft.Text(label, size=12, color=ui.muted_color(), width=LABEL_WIDTH),
        control,
    ], spacing=12, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def _value(ui, text, color=None):
    return ft.Text(text, size=13, weight=ft.FontWeight.W_500, color=color or ui.body_color())


def _status(ui, status):
    """A status as a coloured chip: green when it is working, amber when it needs attention, red otherwise."""
    status = str(status or "unknown")
    key = status.lower()
    color = ft.Colors.GREEN_700 if key in {"operational", "ok", "active"} else ft.Colors.AMBER_800 if key in {"warning", "manual"} else ft.Colors.RED_700
    return ft.Row([ft.Container(width=8, height=8, border_radius=4, bgcolor=color), ui.chip(status.title(), color)], spacing=6, tight=True,
                  vertical_alignment=ft.CrossAxisAlignment.CENTER)


def _note(ui, text, icon=ft.Icons.INFO_OUTLINE):
    return ft.Container(
        content=ft.Row([ft.Icon(icon, size=16, color=ui.accent()), ft.Text(text, size=12, color=ui.body_color(), expand=True)], spacing=10,
                       vertical_alignment=ft.CrossAxisAlignment.START),
        padding=ft.Padding(12, 10, 12, 10),
        bgcolor=ui.tint(),
        border_radius=10,
    )


def _profile_card(ui, profile, edit_profile, note=None):
    hint = "You can change your name and email."
    if note:
        hint = f"{hint} {note}"
    chips = [ui.chip(profile.get("role") or "No role", ft.Colors.BLUE_700)]
    chips.append(ui.chip(profile.get("office") or "Not assigned", ft.Colors.TEAL_700 if profile.get("office") else ft.Colors.BLUE_GREY_500))
    identity = ft.Row(
        [
            ft.Container(
                content=ft.Text(initials(profile), size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                width=72, height=72, border_radius=36,
                alignment=ft.Alignment(0, 0),
                gradient=ft.LinearGradient(begin=ft.Alignment(-1, -1), end=ft.Alignment(1, 1), colors=["#1A56B5", "#0E3A86"]),
            ),
            ft.Column(
                [
                    ft.Text(profile.get("full_name") or "Not provided", size=19, weight=ft.FontWeight.BOLD, color=ui.link_color()),
                    ft.Text(f"@{profile.get('username') or 'Not provided'}", size=13, color=ui.muted_color()),
                    ft.Row(chips, spacing=6, wrap=True),
                ],
                spacing=4,
                expand=True,
            ),
        ],
        spacing=18,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    return ft.Container(
        content=ft.Column([
            ui.card_title("My Profile", ft.Icons.PERSON_OUTLINE, subtitle="Your account information."),
            ft.Divider(height=1, color=ui.line_color()),
            identity,
            ft.Divider(height=1, color=ui.line_color()),
            _row(ui, "Full name", _value(ui, profile.get("full_name") or "Not provided")),
            _row(ui, "Username", _value(ui, profile.get("username") or "Not provided")),
            _row(ui, "Email", _value(ui, profile.get("email") or "Not provided")),
            _row(ui, "Role", _value(ui, profile.get("role") or "Not provided")),
            _row(ui, "Office", _value(ui, profile.get("office") or "Not assigned")),
            _row(ui, "Account created", _value(ui, format_datetime(profile.get("created_at")))),
            _note(ui, hint),
            ft.Row([
                ft.ElevatedButton("Edit profile", icon=ft.Icons.EDIT_OUTLINED, on_click=lambda _: edit_profile()),
            ], alignment=ft.MainAxisAlignment.END),
        ], spacing=14),
        padding=20,
        bgcolor=ui.card_color(),
        border=ft.border.all(1, ui.line_color()),
        border_radius=18,
    )


def _preferences_card(ui):
    return _card(ui, "Preferences", "How the workspace looks on this device.", ft.Icons.PALETTE_OUTLINED, [
        _row(ui, "Night mode", _value(ui, "Switch it on or off from your profile menu at the top right.")),
    ])


def _admin_link(ui, entry, open_page):
    icon, title, description, label = entry
    return ft.Container(
        content=ft.Row([
            ft.Container(
                content=ft.Icon(icon, size=22, color=ui.accent()),
                width=44, height=44, border_radius=12,
                alignment=ft.Alignment(0, 0),
                bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.BLUE_700),
            ),
            ft.Column([
                ft.Text(title, size=14, weight=ft.FontWeight.W_600, color=ui.link_color()),
                ui.hint(description),
            ], spacing=2, expand=True),
            ft.OutlinedButton("Open", icon=ft.Icons.ARROW_FORWARD, on_click=lambda _: open_page(label), tooltip=f"Open {label}"),
        ], spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding(10, 8, 10, 8),
        bgcolor=ui.tone("#F7FAFE", "#1B2430"),
        border=ft.border.all(1, ui.line_color()),
        border_radius=12,
    )


def _field(ui, label, control, width=None):
    """A configuration field with its name above it."""
    ui.style_field(control)
    control.width = width
    return ft.Column([ft.Text(label, size=13, weight=ft.FontWeight.W_600, color=ui.heading_color()), control], spacing=6, width=width)


def _toggle(ui, title, description, switch):
    return ft.Container(
        content=ft.Row([
            ft.Column([
                ft.Text(title, size=13, weight=ft.FontWeight.W_600, color=ui.heading_color()),
                ui.hint(description),
            ], spacing=2, expand=True),
            switch,
        ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding(14, 10, 10, 10),
        bgcolor=ui.tone("#F7FAFE", "#1B2430"),
        border=ft.border.all(1, ui.line_color()),
        border_radius=12,
    )


def _system_configuration_card(page, ui, api):
    values = dict(DEFAULT_SYSTEM_SETTINGS)
    message = ft.Text("", size=12, visible=False)
    try:
        stored = api("GET", "/system-settings").get("settings") or {}
        values.update({key: value for key, value in stored.items() if key in values})
    except Exception as exc:
        message.value = f"Unable to load system settings: {exc}"
        message.color = ft.Colors.RED_700
        message.visible = True

    org_name = ft.TextField(value=str(values["organization_name"]))
    system_name = ft.TextField(value=str(values["system_name"]))
    maintenance = ft.Switch(value=bool(values["maintenance_mode"]), active_color=ft.Colors.AMBER_800, tooltip="Maintenance Mode")
    public_portal = ft.Switch(value=bool(values["public_portal_enabled"]), active_color=ft.Colors.GREEN_700, tooltip="Public Portal Enabled")
    session_timeout = ft.TextField(value=str(values["session_timeout_minutes"]), suffix_text="minutes", keyboard_type=ft.KeyboardType.NUMBER)
    upload_size = ft.TextField(value=str(values["upload_max_size_mb"]), suffix_text="MB", keyboard_type=ft.KeyboardType.NUMBER)

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
        return ft.Text(text.upper(), size=11, weight=ft.FontWeight.BOLD, color=ui.muted_color(), style=ft.TextStyle(letter_spacing=1))

    return _card(ui, "System Configuration", "Application-wide settings.", ft.Icons.SETTINGS_APPLICATIONS_OUTLINED, [
        group("Organization Information"),
        ft.ResponsiveRow([
            ft.Container(_field(ui, "Organization Name", org_name), col={"xs": 12, "md": 5}),
            ft.Container(_field(ui, "System Name", system_name), col={"xs": 12, "md": 7}),
        ], spacing=12, run_spacing=12),
        group("Operational Controls"),
        _toggle(ui, "Maintenance Mode", "Reported as under maintenance in System Information while it is on.", maintenance),
        _toggle(ui, "Public Portal Enabled", "Whether the public homepage and document tracking are open.", public_portal),
        group("Storage and Session Settings"),
        ft.Row([
            _field(ui, "Session Timeout", session_timeout, width=200),
            _field(ui, "Max Upload Size", upload_size, width=200),
        ], wrap=True, spacing=16, run_spacing=12),
        message,
        ft.Row([
            ft.FilledButton("Save system settings", icon=ft.Icons.SAVE_OUTLINED, on_click=save, height=44),
        ], alignment=ft.MainAxisAlignment.END),
    ])


def _system_information_card(ui, api):
    try:
        health = api("GET", "/system-health")
    except Exception as exc:
        rows = [_row(ui, "Backend", _status(ui, "unavailable")), _note(ui, f"Unable to load system information: {exc}", ft.Icons.ERROR_OUTLINE)]
    else:
        components = health.get("components") or {}
        backup = components.get("backup") or {}
        backup_detail = backup.get("detail") if isinstance(backup.get("detail"), dict) else {}
        rows = [
            _row(ui, "Overall", _status(ui, health.get("status"))),
            _row(ui, "Backend", _status(ui, "operational")),
            _row(ui, "Database", _status(ui, (components.get("database") or {}).get("status"))),
            _row(ui, "Document storage", _status(ui, (components.get("storage") or {}).get("status"))),
            _row(ui, "Backups", _status(ui, backup.get("status"))),
            _row(ui, "Last backup", _value(ui, format_datetime(backup_detail.get("last_backup_at")) if backup_detail.get("last_backup_at") else "None recorded")),
            *[_note(ui, problem, ft.Icons.WARNING_AMBER) for problem in backup_detail.get("problems") or []],
            _row(ui, "Migration version", _value(ui, health.get("migration_version") or "Not recorded")),
            _row(ui, "Maintenance mode", _value(ui, "On" if health.get("maintenance_mode") else "Off")),
            _row(ui, "Checked", _value(ui, format_datetime(health.get("generated_at")))),
        ]
    return _card(ui, "System Information", "Backend, database and migration status.", ft.Icons.INFO_OUTLINE, rows)
