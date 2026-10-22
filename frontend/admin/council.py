"""Members & Committees: the SB term, its member roster, and the standing committees.

Anyone who can view documents sees this page; changing it needs the "Manage Members And Committees"
permission, which the backend checks on every call. Nothing is deleted: members get a "left on" date
and committees are deactivated (docs/adr/0002).
"""

from datetime import date

import flet as ft

from frontend.admin.documents import DROPDOWN_EVENT
from frontend.admin.tracking_ui import TrackingWidgets

POSITIONS = ["Vice Mayor", "Regular Member", "Liga ng mga Barangay President", "SK Federation President", "IPMR"]
NO_LOGIN = "none"  # dropdown key for "no login" / "no chair"


def _parse_date(value, label):
    text = (value or "").strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise ValueError(f"{label} must be a date like 2025-07-01.")


def build_members_committees_view(page, surface_card, section_header, api, *, can_manage):
    """`api(method, path, **kwargs)` returns parsed JSON or raises with the backend's detail."""
    ui = TrackingWidgets(page)
    state = {"terms": [], "term_id": None, "members": [], "committees": [], "users": None}
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

        member_rows = []
        for member in state["members"]:
            status = "Current" if member.get("is_active") else f"Left {member.get('left_on')}"
            actions = [ft.IconButton(ft.Icons.EDIT_OUTLINED, tooltip="Edit", on_click=lambda _, m=member: open_member(m))] if can_manage else []
            member_rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(member["full_name"], size=12)),
                ft.DataCell(ft.Text(member["position"], size=12)),
                ft.DataCell(ft.Text(member.get("username") or "-", size=12)),
                ft.DataCell(ft.Text(status, size=12, color=ft.Colors.GREEN_700 if member.get("is_active") else ui.muted_color())),
                ft.DataCell(ft.Row(actions, spacing=2)),
            ]))
        members_area.controls = [
            ft.DataTable(columns=[ft.DataColumn(ft.Text(name)) for name in ("Name", "Position", "Login", "Status", "")],
                         rows=member_rows, column_spacing=24),
        ] if member_rows else [ui.hint("No members in this term yet.")]

        committee_rows = []
        for committee in state["committees"]:
            active = committee.get("is_active")
            actions = [
                ft.IconButton(ft.Icons.EDIT_OUTLINED, tooltip="Edit", on_click=lambda _, c=committee: open_committee(c)),
                ft.IconButton(ft.Icons.PAUSE_CIRCLE_OUTLINE if active else ft.Icons.PLAY_CIRCLE_OUTLINE,
                              tooltip="Deactivate" if active else "Activate", on_click=lambda _, c=committee: toggle_committee(c)),
            ] if can_manage else []
            committee_rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(committee["name"], size=12)),
                ft.DataCell(ft.Text(committee.get("chair_name") or "-", size=12)),
                ft.DataCell(ft.Text("Active" if active else "Inactive", size=12, color=ft.Colors.GREEN_700 if active else ui.muted_color())),
                ft.DataCell(ft.Row(actions, spacing=2)),
            ]))
        committees_area.controls = [
            ft.DataTable(columns=[ft.DataColumn(ft.Text(name)) for name in ("Committee", "Chair", "Status", "")],
                         rows=committee_rows, column_spacing=24),
        ] if committee_rows else [ui.hint("No committees yet.")]

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
        starts = ft.TextField(label="Starts on", hint_text="YYYY-MM-DD", value=(item or {}).get("starts_on", ""), width=200)
        ends = ft.TextField(label="Ends on", hint_text="YYYY-MM-DD", value=(item or {}).get("ends_on", ""), width=200)

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
        open_dialog("Edit term" if item else "Add term", [name, ft.Row([starts, ends], spacing=12)], on_save)

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
        left = ft.TextField(label="Left on (only if they left before the term ends)", hint_text="YYYY-MM-DD",
                            value=(item or {}).get("left_on") or "", visible=item is not None)

        def on_save():
            if users:
                user_id = None if login.value in (None, NO_LOGIN) else int(login.value)
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
        fields = [name, position, login] + ([login_hint] if login_hint else []) + [left]
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
        surface_card(section_header("Members & Committees", "The SB term, its members, and the standing committees.",
                                    ft.Icons.GROUPS_OUTLINED, ft.Colors.GREEN_700), padding=18),
        message,
        surface_card(ft.Column([
            ft.Text("Term and members", size=15, weight=ft.FontWeight.W_600, color=ui.heading_color()),
            ft.Row([term_choice, term_dates], spacing=12, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            manage(
                ft.OutlinedButton("Add term", icon=ft.Icons.ADD, on_click=lambda _: open_term()),
                ft.OutlinedButton("Edit term", icon=ft.Icons.EDIT_OUTLINED, on_click=lambda _: open_term(term()) if term() else None),
                ft.ElevatedButton("Add member", icon=ft.Icons.PERSON_ADD_ALT, on_click=lambda _: open_member()),
            ),
            members_area,
        ], spacing=12), padding=18),
        surface_card(ft.Column([
            ft.Text("Committees", size=15, weight=ft.FontWeight.W_600, color=ui.heading_color()),
            manage(ft.ElevatedButton("Add committee", icon=ft.Icons.ADD, on_click=lambda _: open_committee())),
            committees_area,
        ], spacing=12), padding=18),
    ], spacing=16)
