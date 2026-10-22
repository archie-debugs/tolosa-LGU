"""Sessions: the SB's regular and special sessions in a term, and who attended each.

Anyone who can view documents sees this page; changing it needs the "Manage Sessions" permission,
which the backend checks on every call. A session goes Draft -> Scheduled -> Held; once held, its
attendance is corrected with a reason instead of edited (docs/adr/0003). Quorum is a warning only.
"""

from datetime import date

import flet as ft

from frontend.admin.documents import DROPDOWN_EVENT
from frontend.admin.tracking_ui import TrackingWidgets

KINDS = ["Regular", "Special"]
MARKS = ["Present", "Absent", "On leave", "Excused"]
NOT_MARKED = "none"  # dropdown key for "not marked yet"
MARK_COLORS = {"Present": ft.Colors.GREEN_700, "Absent": ft.Colors.RED_700, "On leave": ft.Colors.AMBER_800,
               "Excused": ft.Colors.BLUE_GREY_600}
STATUS_COLORS = {"Draft": ft.Colors.BLUE_GREY_600, "Scheduled": ft.Colors.BLUE_700, "Held": ft.Colors.GREEN_700}
# The button for each move a session can make.
STATUS_ACTIONS = {"Scheduled": ("Schedule", ft.Icons.EVENT_AVAILABLE), "Held": ("Mark as held", ft.Icons.TASK_ALT),
                  "Draft": ("Back to draft", ft.Icons.UNDO)}


def _date_text(value):
    try:
        return date.fromisoformat(value).strftime("%B %d, %Y")
    except (TypeError, ValueError):
        return value or "-"


def quorum_text(quorum):
    """"3 of 4 present · quorum" or what is missing, for the list and the session page."""
    if not quorum.get("in_office"):
        return "No members in office on this date"
    if quorum["unmarked"] == quorum["in_office"]:
        return "Attendance not taken yet"
    text = f"{quorum['present']} of {quorum['in_office']} present"
    if quorum["has_quorum"]:
        return text + " · quorum"
    return text + f" · no quorum ({quorum['needed']} needed)"


def build_sessions_view(page, surface_card, api, *, can_manage):
    """`api(method, path, **kwargs)` returns parsed JSON or raises with the backend's detail."""
    ui = TrackingWidgets(page)
    state = {"terms": [], "term_id": None, "sessions": [], "next_numbers": {}, "session": None}
    message = ft.Text("", size=12, visible=False)
    body = ft.Column(spacing=16)
    term_choice = ft.Dropdown(label="Term", width=320, options=[], **{DROPDOWN_EVENT: lambda _: select_term(term_choice.value)})

    def show(text, ok=True):
        message.value, message.color, message.visible = text, ft.Colors.GREEN_700 if ok else ft.Colors.RED_700, True

    def call(method, path, **kwargs):
        try:
            return api(method, path, **kwargs)
        except Exception as exc:
            show(str(exc)[:200], ok=False)
            return None

    def load_list():
        state["terms"] = call("GET", "/council/terms") or []
        if state["term_id"] not in {term["id"] for term in state["terms"]}:
            current = next((term for term in state["terms"] if term.get("is_current")), None)
            state["term_id"] = (current or (state["terms"][0] if state["terms"] else {})).get("id")
        listing = (call("GET", f"/council/sessions?term_id={state['term_id']}") or {}) if state["term_id"] else {}
        state["sessions"] = listing.get("sessions") or []
        state["next_numbers"] = listing.get("next_numbers") or {}

    def update():
        render()
        page.update()

    def select_term(value):
        state["term_id"] = int(value) if value else None
        message.visible = False
        load_list()
        update()

    def open_session(session_id):
        detail = call("GET", f"/council/sessions/{session_id}")
        if detail is not None:
            state["session"] = detail
            message.visible = False
        update()

    def back_to_list():
        state["session"] = None
        message.visible = False
        load_list()
        update()

    # ----- the list of sessions -----

    def session_row(item):
        quorum = item["quorum"]
        warn = quorum["unmarked"] < quorum["in_office"] and not quorum["has_quorum"]
        return ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text(item["title"], size=15, weight=ft.FontWeight.W_600, color=ui.link_color()),
                    ft.Text(f"{_date_text(item['held_on'])} · {quorum_text(quorum)}", size=12,
                            color=ft.Colors.AMBER_800 if warn else ui.muted_color()),
                ], spacing=2, expand=True),
                ui.chip(item["status"], STATUS_COLORS.get(item["status"], ft.Colors.BLUE_GREY_600)),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, color=ui.muted_color()),
            ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding(14, 10, 8, 10),
            bgcolor=ui.tone("#F7FAFE", "#1B2430"),
            border_radius=12,
            on_click=lambda _, session_id=item["id"]: open_session(session_id),
        )

    def list_controls():
        term_choice.options = [ft.dropdown.Option(key=str(item["id"]), text=item["name"] + (" (current)" if item.get("is_current") else ""))
                               for item in state["terms"]]
        term_choice.value = str(state["term_id"]) if state["term_id"] else None
        if not state["terms"]:
            empty = "No term yet. Add the SB term under Members & Committees first."
        else:
            empty = "No sessions in this term yet." + (" Add the first one." if can_manage else "")
        return [
            ui.banner("Sessions", "The SB's regular and special sessions, and who attended each.", ft.Icons.EVENT_NOTE),
            message,
            surface_card(ft.Column([
                ui.card_title("Sessions in the term", ft.Icons.EVENT_NOTE_OUTLINED,
                              subtitle="Regular and special sessions are numbered separately within a term."),
                ft.Row([term_choice], spacing=12, wrap=True),
                ft.Row([ft.ElevatedButton("Add session", icon=ft.Icons.ADD, on_click=lambda _: open_details_form())],
                       visible=can_manage and bool(state["term_id"])),
                ft.Column([session_row(item) for item in state["sessions"]] or [ui.empty_box(empty)], spacing=8),
            ], spacing=14), padding=20),
        ]

    # ----- one session -----

    def attendance_row(row, held):
        detail = row["position"]
        lines = [
            ft.Text(row["full_name"], size=14, weight=ft.FontWeight.W_600, color=ui.heading_color()),
            ft.Text(detail, size=12, color=ui.muted_color()),
        ]
        corrections = [entry for entry in row.get("history") or [] if entry.get("is_correction")]
        for entry in corrections:
            lines.append(ft.Text(f"Corrected to {entry['mark']} by {entry.get('recorded_by') or '-'}: {entry.get('note') or ''}",
                                 size=11, color=ft.Colors.AMBER_800))
        latest = (row.get("history") or [{}])[0]
        if row.get("note") and not latest.get("is_correction"):  # a correction's note is its reason, shown above
            lines.append(ft.Text(row["note"], size=12, color=ui.body_color()))
        trailing = []
        if can_manage and not held:
            mark_field = ft.Dropdown(width=170, dense=True, value=row.get("mark") or NOT_MARKED,
                                     options=[ft.dropdown.Option(key=NOT_MARKED, text="Not marked")] + [ft.dropdown.Option(value) for value in MARKS])
            note_field = ft.TextField(hint_text="Note (optional)", value=row.get("note") or "", width=220, dense=True)
            pending[row["member_id"]] = (mark_field, note_field)
            trailing = [mark_field, note_field]
        else:
            mark = row.get("mark")
            trailing.append(ui.chip(mark or "Not marked", MARK_COLORS.get(mark, ft.Colors.BLUE_GREY_400)))
            if can_manage and held:
                trailing.append(ft.IconButton(ft.Icons.EDIT_NOTE, icon_color=ui.accent(), tooltip="Correct",
                                              on_click=lambda _, r=row: open_correction(r)))
        return ft.Container(
            content=ft.ResponsiveRow([
                ft.Column(lines, spacing=2, col={"xs": 12, "md": 5}),
                ft.Row(trailing, spacing=8, wrap=True, alignment=ft.MainAxisAlignment.END, col={"xs": 12, "md": 7},
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding(14, 10, 10, 10),
            bgcolor=ui.tone("#F7FAFE", "#1B2430"),
            border_radius=12,
        )

    pending = {}

    def save_attendance():
        marks = [{"member_id": member_id, "mark": None if mark.value in (None, NOT_MARKED) else mark.value,
                  "note": (note.value or "").strip() or None}
                 for member_id, (mark, note) in pending.items()]
        result = call("PUT", f"/council/sessions/{state['session']['id']}/attendance", json={"marks": marks})
        if result is not None:
            state["session"] = result
            show("Attendance saved.")
        update()

    def mark_everyone_present():
        for mark, _ in pending.values():
            if mark.value in (None, NOT_MARKED):
                mark.value = "Present"
        page.update()

    def change_status(status):
        session = state["session"]
        if status == "Held":
            quorum = session["quorum"]
            warnings = []
            if quorum["unmarked"]:
                warnings.append(f"{quorum['unmarked']} member(s) are not marked.")
            if not quorum["has_quorum"]:
                warnings.append(f"Only {quorum['present']} of {quorum['in_office']} are marked present; quorum is {quorum['needed']}.")
            confirm("Mark as held?", [
                ft.Text("Once the session is held, attendance can only be corrected with a reason, and its number and date are fixed."),
                *[ft.Text(text, color=ft.Colors.AMBER_800) for text in warnings],
            ], "Mark as held", lambda: apply_status(status))
        else:
            apply_status(status)

    def apply_status(status):
        result = call("POST", f"/council/sessions/{state['session']['id']}/status", json={"status": status})
        if result is not None:
            state["session"] = result
            show(f"{result['title']} is now {status}.")
        update()

    def delete_session():
        session = state["session"]

        def go():
            if call("DELETE", f"/council/sessions/{session['id']}") is not None:
                show(f"Deleted the draft {session['title']}.")
                state["session"] = None
                load_list()
            update()
        confirm("Delete this draft?", [ft.Text(f"The {session['title']} of {_date_text(session['held_on'])} and its attendance will be removed.")],
                "Delete", go)

    def session_controls():
        session = state["session"]
        held = session["status"] == "Held"
        pending.clear()
        quorum = session["quorum"]
        warn = quorum["unmarked"] < quorum["in_office"] and not quorum["has_quorum"]
        actions = []
        if can_manage:
            for status in session["next_statuses"]:
                label, icon = STATUS_ACTIONS[status]
                button = ft.ElevatedButton if status != "Draft" else ft.OutlinedButton
                actions.append(button(label, icon=icon, on_click=lambda _, s=status: change_status(s)))
            if not held:
                actions.append(ft.OutlinedButton("Edit details", icon=ft.Icons.EDIT_OUTLINED, on_click=lambda _: open_details_form(session)))
            if session["status"] == "Draft":
                actions.append(ft.TextButton("Delete draft", icon=ft.Icons.DELETE_OUTLINE, on_click=lambda _: delete_session()))
        rows = [attendance_row(row, held) for row in session["attendance"]]
        attendance_actions = []
        if can_manage and not held and rows:
            attendance_actions = [ft.Row([
                ft.ElevatedButton("Save attendance", icon=ft.Icons.SAVE_OUTLINED, on_click=lambda _: save_attendance()),
                ft.OutlinedButton("Mark the rest present", icon=ft.Icons.DONE_ALL, on_click=lambda _: mark_everyone_present()),
            ], spacing=8, wrap=True)]
        subtitle = ("Held: changes are corrections with a reason." if held
                    else "Members of the term who were in office on the session date.")
        return [
            ft.Row([ft.TextButton("All sessions", icon=ft.Icons.ARROW_BACK, on_click=lambda _: back_to_list())]),
            ui.banner(session["title"], f"{session.get('term_name') or ''} · {_date_text(session['held_on'])}", ft.Icons.EVENT_NOTE),
            message,
            surface_card(ft.Column([
                ft.Row([
                    ui.chip(session["status"], STATUS_COLORS.get(session["status"], ft.Colors.BLUE_GREY_600)),
                    ft.Text(quorum_text(quorum), size=13, weight=ft.FontWeight.W_600,
                            color=ft.Colors.AMBER_800 if warn else ui.body_color()),
                ], spacing=12, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                *([ft.Row(actions, spacing=8, wrap=True)] if actions else []),
            ], spacing=12), padding=20),
            surface_card(ft.Column([
                ui.card_title("Attendance", ft.Icons.HOW_TO_REG_OUTLINED, subtitle=subtitle),
                *attendance_actions,
                ft.Column(rows or [ui.empty_box("No members were in office on this date. Check the roster under Members & Committees.")], spacing=8),
            ], spacing=14), padding=20),
        ]

    def render():
        body.controls = session_controls() if state["session"] else list_controls()

    # ----- dialogs -----

    dialog_error = ft.Text("", size=12, color=ft.Colors.RED_700, visible=False)
    dialog = ft.AlertDialog(modal=True, title=ft.Text(""), content=ft.Column([], tight=True, spacing=12, width=440), actions=[])
    page.overlay.append(dialog)

    def open_dialog(title, fields, button, on_save):
        def save(_):
            try:
                on_save()
            except ValueError as exc:
                dialog_error.value, dialog_error.visible = str(exc), True
                page.update()
                return
            dialog.open = False
            update()
        dialog.title = ft.Text(title, size=18, weight=ft.FontWeight.BOLD)
        dialog_error.visible = False
        dialog.content.controls = [*fields, dialog_error]
        dialog.actions = [ft.TextButton("Cancel", on_click=lambda _: close_dialog()), ft.ElevatedButton(button, on_click=save)]
        dialog.open = True
        page.update()

    def close_dialog():
        dialog.open = False
        page.update()

    def confirm(title, lines, button, action):
        open_dialog(title, lines, button, action)

    def dialog_call(method, path, **kwargs):
        try:
            return api(method, path, **kwargs)
        except Exception as exc:
            raise ValueError(str(exc)[:200])

    def open_details_form(session=None):
        kind = ft.Dropdown(label="Kind", value=(session or {}).get("kind", "Regular"), width=180,
                           options=[ft.dropdown.Option(value) for value in KINDS],
                           **{DROPDOWN_EVENT: lambda _: suggest_number()})
        number = ft.TextField(label="Number in the term", width=180,
                              value=str((session or {}).get("number") or state["next_numbers"].get("Regular", 1)))
        held_on = ft.TextField(label="Date", hint_text="YYYY-MM-DD", width=200, value=(session or {}).get("held_on") or "")

        def suggest_number():
            if session is None:
                number.value = str(state["next_numbers"].get(kind.value, 1))
                page.update()

        def on_save():
            if not (number.value or "").strip().isdigit() or int(number.value) < 1:
                raise ValueError("The number must be a whole number like 12.")
            try:
                day = date.fromisoformat((held_on.value or "").strip()).isoformat()
            except ValueError:
                raise ValueError("The date must look like 2026-10-22.")
            payload = {"kind": kind.value, "number": int(number.value), "held_on": day}
            if session:
                state["session"] = dialog_call("PUT", f"/council/sessions/{session['id']}", json=payload)
                show("Session details saved.")
            else:
                state["session"] = dialog_call("POST", "/council/sessions", json={**payload, "term_id": state["term_id"]})
                show(f"Added the {state['session']['title']} as a draft.")
        open_dialog("Edit session" if session else "Add session",
                    [ft.Row([kind, number], spacing=12, wrap=True), held_on,
                     ui.hint("A new session starts as a draft. Schedule it when the date is set, and mark it held afterwards.")],
                    "Save", on_save)

    def open_correction(row):
        mark = ft.Dropdown(label="Correct mark", value=row.get("mark"), width=200, options=[ft.dropdown.Option(value) for value in MARKS])
        reason = ft.TextField(label="Reason (required)", multiline=True, min_lines=1, max_lines=3)

        def on_save():
            if not mark.value:
                raise ValueError("Choose the correct mark.")
            if not (reason.value or "").strip():
                raise ValueError("Say why the attendance is being corrected.")
            state["session"] = dialog_call("POST", f"/council/sessions/{state['session']['id']}/attendance/corrections",
                                           json={"member_id": row["member_id"], "mark": mark.value, "reason": reason.value.strip()})
            show(f"Corrected {row['full_name']}'s attendance.")
        open_dialog(f"Correct {row['full_name']}", [mark, reason, ui.hint("The earlier mark stays in the record.")], "Save correction", on_save)

    load_list()
    render()
    return body
