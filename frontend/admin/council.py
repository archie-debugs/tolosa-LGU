"""Members & Committees: the SB term, its member roster, and the standing committees.

Anyone who can view documents sees this page; changing it needs the "Manage Members And Committees"
permission, which the backend checks on every call. Nothing is deleted: members get a "left on" date
and committees are deactivated (docs/adr/0002).
"""

from datetime import date, datetime

import flet as ft

from frontend.admin.documents import DROPDOWN_EVENT
from frontend.admin.todays_documents import picked_date
from frontend.admin.tracking_ui import TrackingWidgets

POSITIONS = ["Vice Mayor", "Regular Member", "Liga ng mga Barangay President", "SK Federation President", "IPMR"]
NO_LOGIN = "none"  # dropdown key for "no login" / "no chair" / "type it in"


def _parse_date(value, label):
    text = (value or "").strip()
    if not text:
        raise ValueError(f"Pick the {label.lower()} date.")
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise ValueError(f"{label} must be a date like 2025-07-01.")


def date_field(page, label, value, width=200, clearable=False):
    """A date box that can't be typed in: clicking it opens a calendar. Returns (field, control to show).

    `clearable` adds a button to empty it, for optional dates.
    """
    field = ft.TextField(label=label, hint_text="Pick a date", value=value or "", width=width, read_only=True,
                         suffix_icon=ft.Icons.CALENDAR_MONTH_OUTLINED)

    def picked(e):
        day = picked_date(e.control.value)
        if day:
            field.value = day.isoformat()
            page.update()

    def pick(_):
        # One picker per page, shared by every date box; it fills whichever box opened it last.
        picker = getattr(page, "_council_date_picker", None)
        if picker is None:
            picker = page._council_date_picker = ft.DatePicker(first_date=datetime(2000, 1, 1), last_date=datetime(2100, 12, 31))
        picker.on_change = picked
        try:
            current = date.fromisoformat(field.value)
        except ValueError:
            current = None
        picker.value = datetime.combine(current, datetime.min.time()) if current else None
        if hasattr(picker, "pick_date"):  # older Flet: the picker lives in the overlay
            if picker not in page.overlay:
                page.overlay.append(picker)
                page.update()
            picker.pick_date()
        else:
            page.open(picker)

    def clear(_):
        field.value = ""
        page.update()

    # A see-through layer over the box takes the click, since a read-only text field keeps it.
    box = ft.Stack([field, ft.Container(left=0, top=0, right=0, bottom=0, on_click=pick)], width=width)
    if clearable:
        box = ft.Row([box, ft.IconButton(ft.Icons.CLOSE, tooltip="Clear the date", on_click=clear)], spacing=4)
    return field, box


def build_members_committees_view(page, surface_card, api, *, can_manage):
    """`api(method, path, **kwargs)` returns parsed JSON or raises with the backend's detail."""
    ui = TrackingWidgets(page)
    state = {"terms": [], "term_id": None, "members": [], "committees": [], "users": None, "accounts": []}
    message = ft.Text("", size=12, visible=False)
    term_choice = ft.Dropdown(label="Term", width=320, options=[], **{DROPDOWN_EVENT: lambda _: select_term(term_choice.value)})
    term_dates = ui.hint("")
    members_area = ft.Column(spacing=8)
    committees_area = ft.Column(spacing=8)

    def show(text, ok=True):
        message.value, message.color, message.visible = text, ft.Colors.GREEN_700 if ok else ft.Colors.RED_700, True

    def call(method, path, **kwargs):
        try:
            return api(method, path, **kwargs)
        except Exception as exc:
            show(str(exc)[:200], ok=False)
            return None

    def load():
        state["terms"] = call("GET", "/council/terms") or []
        state["committees"] = call("GET", "/council/committees") or []
        if can_manage:
            state["accounts"] = call("GET", "/council/member-accounts") or []
        if state["users"] is None and can_manage:
            try:
                state["users"] = [user for user in api("GET", "/auth/users") if user.get("is_active", True)]
            except Exception:
                state["users"] = []  # needs View Users; members can still be added without a login
        if state["term_id"] not in {term["id"] for term in state["terms"]}:
            current = next((term for term in state["terms"] if term.get("is_current")), None)
            state["term_id"] = (current or (state["terms"][0] if state["terms"] else {})).get("id")
        load_members()

    def load_members():
        state["members"] = (call("GET", f"/council/members?term_id={state['term_id']}") or []) if state["term_id"] else []

    def term(term_id=None):
        term_id = term_id or state["term_id"]
        return next((item for item in state["terms"] if item["id"] == term_id), None)

    def render():
        term_choice.options = [ft.dropdown.Option(key=str(item["id"]), text=item["name"] + (" (current)" if item.get("is_current") else ""))
                               for item in state["terms"]]
        term_choice.value = str(state["term_id"]) if state["term_id"] else None
        selected = term()
        term_dates.value = f"{selected['starts_on']} to {selected['ends_on']}" if selected else "No term yet. Add the current SB term first."

        members_area.controls = [
            row(member["full_name"], f"{member['position']} · login: {member.get('username') or 'none'}",
                "Current" if member.get("is_active") else f"Left {member.get('left_on')}", member.get("is_active"),
                [ft.IconButton(ft.Icons.EDIT_OUTLINED, icon_color=ui.accent(), tooltip="Edit", on_click=lambda _, m=member: open_member(m))])
            for member in state["members"]
        ] or [ui.empty_box("No members in this term yet." if state["term_id"] else "No term yet. Add the current SB term first.")]

        committees_area.controls = [
            row(committee["name"], f"Chair: {committee.get('chair_name') or 'none yet'}",
                "Active" if committee.get("is_active") else "Inactive", committee.get("is_active"),
                [ft.IconButton(ft.Icons.EDIT_OUTLINED, icon_color=ui.accent(), tooltip="Edit", on_click=lambda _, c=committee: open_committee(c)),
                 ft.IconButton(ft.Icons.PAUSE_CIRCLE_OUTLINE if committee.get("is_active") else ft.Icons.PLAY_CIRCLE_OUTLINE,
                               icon_color=ui.accent(), tooltip="Deactivate" if committee.get("is_active") else "Activate",
                               on_click=lambda _, c=committee: toggle_committee(c))])
            for committee in state["committees"]
        ] or [ui.empty_box("No committees yet.")]

    def row(title, detail, status, active, actions):
        """One member or committee, in the rounded row style the other admin lists use."""
        return ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text(title, size=15, weight=ft.FontWeight.W_600, color=ui.link_color()),
                    ft.Text(detail, size=12, color=ui.muted_color()),
                ], spacing=2, expand=True),
                ui.chip(status, ft.Colors.GREEN_700 if active else ft.Colors.BLUE_GREY_500),
                *(actions if can_manage else []),
            ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding(14, 8, 8, 8),
            bgcolor=ui.tone("#F7FAFE", "#1B2430"),
            border_radius=12,
        )

    def refresh():
        load()
        render()
        page.update()

    def select_term(value):
        state["term_id"] = int(value) if value else None
        load_members()
        render()
        page.update()

    # One dialog, refilled for each form.
    dialog_error = ft.Text("", size=12, color=ft.Colors.RED_700, visible=False)
    dialog = ft.AlertDialog(modal=True, title=ft.Text(""), content=ft.Column([], tight=True, spacing=12, width=440), actions=[])
    page.overlay.append(dialog)
    def open_dialog(title, fields, on_save):
        def save(_):
            try:
                payload = on_save()
            except ValueError as exc:
                dialog_error.value, dialog_error.visible = str(exc), True
                page.update()
                return
            if payload is not None:
                dialog.open = False
                refresh()
        dialog.title = ft.Text(title, size=18, weight=ft.FontWeight.BOLD)
        dialog_error.visible = False
        dialog.content.controls = [*fields, dialog_error]
        dialog.actions = [ft.TextButton("Cancel", on_click=lambda _: close_dialog()), ft.ElevatedButton("Save", on_click=save)]
        dialog.open = True
        page.update()

    def close_dialog():
        dialog.open = False
        page.update()

    def saved(result, text):
        if result is not None:
            show(text)
        return result

    def dialog_call(method, path, **kwargs):
        # Errors stay in the open dialog instead of the page message.
        try:
            return api(method, path, **kwargs)
        except Exception as exc:
            raise ValueError(str(exc)[:200])

    def open_term(item=None):
        name = ft.TextField(label="Name", hint_text="e.g. 13th Sangguniang Bayan", value=(item or {}).get("name", ""))
        starts, starts_box = date_field(page, "Starts on", (item or {}).get("starts_on"))
        ends, ends_box = date_field(page, "Ends on", (item or {}).get("ends_on"))

        def on_save():
            payload = {"name": (name.value or "").strip(), "starts_on": _parse_date(starts.value, "Starts on"),
                       "ends_on": _parse_date(ends.value, "Ends on")}
            if not payload["name"]:
                raise ValueError("Give the term a name.")
            if item:
                return saved(dialog_call("PUT", f"/council/terms/{item['id']}", json=payload), "Term saved.")
            result = saved(dialog_call("POST", "/council/terms", json=payload), "Term added.")
            state["term_id"] = result["id"]
            return result
        open_dialog("Edit term" if item else "Add term", [name, ft.Row([starts_box, ends_box], spacing=12)], on_save)

    def open_member(item=None):
        name = ft.TextField(label="Full name", hint_text="e.g. Hon. Maria Santos", value=(item or {}).get("full_name", ""))
        position = ft.Dropdown(label="Position", value=(item or {}).get("position", "Regular Member"),
                               options=[ft.dropdown.Option(value) for value in POSITIONS])
        users = state["users"] or []
        login = ft.Dropdown(label="Login (optional)", value=str((item or {}).get("user_id") or NO_LOGIN),
                            options=[ft.dropdown.Option(key=NO_LOGIN, text="No login")]
                            + [ft.dropdown.Option(key=str(user["id"]), text=f"{user['username']} ({user.get('role') or '-'})") for user in users],
                            visible=bool(users))
        login_hint = ui.hint("Linking a login needs the View Users permission.") if not users else None
        left, left_box = date_field(page, "Left on", (item or {}).get("left_on"), clearable=True)
        left_box.visible = item is not None
        left_hint = ui.hint("Left on: only if they left before the term ends.")
        left_hint.visible = item is not None
        # Adding: pick an SB Member account to fill in the name, position and login from it.
        taken = {member.get("user_id") for member in state["members"] if member.get("is_active")}
        accounts = {str(account["id"]): account for account in state["accounts"] if account["id"] not in taken}

        def pick_account(_):
            account = accounts.get(picker.value)
            if account:
                name.value = account["full_name"]
                position.value = account.get("sb_position") or position.value
                login.value = str(account["id"])
                page.update()

        picker = ft.Dropdown(label="SB Member", value=NO_LOGIN, visible=item is None and bool(accounts),
                             options=[ft.dropdown.Option(key=NO_LOGIN, text="Not listed: type it in")]
                             + [ft.dropdown.Option(key=key, text=f"{account['full_name']} · {account.get('sb_position') or 'no position set'}")
                                for key, account in accounts.items()],
                             **{DROPDOWN_EVENT: pick_account})

        def on_save():
            if users:
                user_id = None if login.value in (None, NO_LOGIN) else int(login.value)
            elif picker.value in accounts:
                user_id = int(picker.value)
            else:
                user_id = (item or {}).get("user_id")  # can't see logins: keep whatever is linked
            payload = {"full_name": (name.value or "").strip(), "position": position.value, "user_id": user_id}
            if not payload["full_name"]:
                raise ValueError("Enter the member's full name.")
            if item:
                payload["left_on"] = _parse_date(left.value, "Left on") if (left.value or "").strip() else None
                return saved(dialog_call("PUT", f"/council/members/{item['id']}", json=payload), "Member saved.")
            if not state["term_id"]:
                raise ValueError("Add a term first.")
            return saved(dialog_call("POST", "/council/members", json={**payload, "term_id": state["term_id"]}), "Member added.")
        fields = [picker, name, position, login] + ([login_hint] if login_hint else []) + [left_hint, left_box]
        open_dialog("Edit member" if item else f"Add member to the {(term() or {}).get('name', 'term')}", fields, on_save)

    def chair_options(current_id=None):
        members = [member for member in state["members"] if member.get("is_active") or member["id"] == current_id]
        return [ft.dropdown.Option(key=NO_LOGIN, text="No chair yet")] + [
            ft.dropdown.Option(key=str(member["id"]), text=member["full_name"]) for member in members
        ]

    def open_committee(item=None):
        name = ft.TextField(label="Committee name", hint_text="e.g. Committee on Health", value=(item or {}).get("name", ""))
        chair = ft.Dropdown(label="Chair", value=str((item or {}).get("chair_member_id") or NO_LOGIN),
                            options=chair_options((item or {}).get("chair_member_id")))

        def on_save():
            payload = {"name": (name.value or "").strip(), "chair_member_id": None if chair.value in (None, NO_LOGIN) else int(chair.value),
                       "is_active": (item or {}).get("is_active", True)}
            if not payload["name"]:
                raise ValueError("Enter the committee's name.")
            if item:
                return saved(dialog_call("PUT", f"/council/committees/{item['id']}", json=payload), "Committee saved.")
            return saved(dialog_call("POST", "/council/committees", json=payload), "Committee added.")
        open_dialog("Edit committee" if item else "Add committee", [name, chair, ui.hint("The chair is chosen from the members of the selected term.")], on_save)

    def toggle_committee(item):
        payload = {"name": item["name"], "chair_member_id": item.get("chair_member_id"), "is_active": not item.get("is_active")}
        if saved(call("PUT", f"/council/committees/{item['id']}", json=payload),
                 f"{item['name']} {'activated' if payload['is_active'] else 'deactivated'}.") is not None:
            refresh()
        else:
            page.update()

    load()
    render()

    def manage(*buttons):
        return ft.Row(list(buttons), spacing=8, wrap=True, visible=can_manage)

    return ft.Column([
        ui.banner("Members & Committees", "The SB term, its members, and the standing committees.", ft.Icons.GROUPS),
        message,
        surface_card(ft.Column([
            ui.card_title("Term and members", ft.Icons.PERSON_OUTLINE, subtitle="Members are never deleted; give them a date if they leave."),
            ft.Row([term_choice, term_dates], spacing=12, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            manage(
                ft.OutlinedButton("Add term", icon=ft.Icons.ADD, on_click=lambda _: open_term()),
                ft.OutlinedButton("Edit term", icon=ft.Icons.EDIT_OUTLINED, on_click=lambda _: open_term(term()) if term() else None),
                ft.ElevatedButton("Add member", icon=ft.Icons.PERSON_ADD_ALT, on_click=lambda _: open_member()),
            ),
            members_area,
        ], spacing=14), padding=20),
        surface_card(ft.Column([
            ui.card_title("Committees", ft.Icons.GROUPS_OUTLINED, subtitle="Committees are deactivated, not deleted, since measures are referred to them."),
            manage(ft.ElevatedButton("Add committee", icon=ft.Icons.ADD, on_click=lambda _: open_committee())),
            committees_area,
        ], spacing=14), padding=20),
    ], spacing=16)
