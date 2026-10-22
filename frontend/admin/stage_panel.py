"""The Stage section of a measure's details: its current stage, its history, and changing or correcting it.

Only ordinances and resolutions have a stage (GLOSSARY.md: Measure, Stage). The backend decides which
moves are allowed; a correction can set any stage but needs a reason (docs/adr/0003).
"""

from datetime import date

import flet as ft

from frontend.admin.documents import DROPDOWN_EVENT
from frontend.admin.tracking_ui import TrackingWidgets, stage_color

IN_COMMITTEE = "In Committee"


def _date_text(value):
    try:
        return date.fromisoformat(value).strftime("%b %d, %Y")
    except (TypeError, ValueError):
        return value or "-"


def build_stage_section(page, api, document_id, *, can_change, on_saved=None):
    """The Stage section, or None when the document isn't a measure or the user may not see its stage.

    `api(method, path, **kwargs)` returns parsed JSON or raises with the backend's detail.
    `on_saved()` runs after a change or correction is recorded.
    """
    ui = TrackingWidgets(page)
    try:
        data = api("GET", f"/documents/{document_id}/stage")
    except Exception:
        return None
    if not data.get("is_measure"):
        return None

    section = ft.Column(spacing=10)
    state = {"data": data, "form": None, "message": ("", False), "committees": None}

    def committees():
        if state["committees"] is None:
            try:
                state["committees"] = api("GET", "/council/committees?active_only=true")
            except Exception:
                state["committees"] = []
        return state["committees"]

    def history_row(entry):
        detail = [_date_text(entry.get("effective_on"))]
        if entry.get("committee"):
            detail.append(entry["committee"])
        if entry.get("changed_by"):
            detail.append(f"by {entry['changed_by']}")
        lines = [
            ft.Row([
                ft.Text(entry["stage"], size=13, weight=ft.FontWeight.W_600, color=ui.heading_color()),
                *([ui.chip("Correction", ft.Colors.AMBER_800)] if entry.get("is_correction") else []),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Text(" · ".join(detail), size=12, color=ui.muted_color()),
        ]
        if entry.get("note"):
            lines.append(ft.Text(entry["note"], size=12, color=ui.body_color(), selectable=True))
        return ft.Container(ft.Column(lines, spacing=2), padding=ft.Padding(0, 6, 0, 6))

    def form(correcting):
        """Change (allowed moves) or correction (any stage, with a reason)."""
        info = state["data"]
        choices = info["stages"] if correcting else info["allowed"]
        stage_field = ft.Dropdown(label="Correct stage" if correcting else "New stage", width=260,
                                  options=[ft.dropdown.Option(choice) for choice in choices],
                                  **{DROPDOWN_EVENT: lambda _: show_fields()})
        date_field = ft.TextField(label="Date it happened", hint_text="YYYY-MM-DD, blank for today", width=220)
        committee_field = ft.Dropdown(label="Committee", width=320, visible=False,
                                      options=[ft.dropdown.Option(key=str(item["id"]), text=item["name"]) for item in committees()])
        needs_number = not (info.get("document_number") and info.get("series_year"))
        number_field = ft.TextField(label=f"{info['kind'].title()} number", width=160, visible=False)
        year_field = ft.TextField(label="Series year", hint_text="blank for the date's year", width=180, visible=False)
        note_field = ft.TextField(label="Reason (required)" if correcting else "Note (optional)", multiline=True, min_lines=1, max_lines=3)

        def show_fields():
            chosen = stage_field.value
            committee_field.visible = chosen == IN_COMMITTEE
            enacting = needs_number and chosen in info["stages"] and _is_enacted(info, chosen)
            number_field.visible = year_field.visible = enacting
            page.update()

        def save(_):
            if not stage_field.value:
                return say("Choose a stage.", error=True)
            body = {"stage": stage_field.value}
            if (date_field.value or "").strip():
                try:
                    body["effective_on"] = date.fromisoformat(date_field.value.strip()).isoformat()
                except ValueError:
                    return say("The date must look like 2026-10-22.", error=True)
            if committee_field.visible:
                body["committee_id"] = int(committee_field.value) if committee_field.value else None
            if number_field.visible:
                body["document_number"] = (number_field.value or "").strip() or None
                if (year_field.value or "").strip():
                    if not year_field.value.strip().isdigit():
                        return say("The series year must be a year like 2026.", error=True)
                    body["series_year"] = int(year_field.value.strip())
            note = (note_field.value or "").strip()
            if correcting:
                if not note:
                    return say("Say why the stage is being corrected.", error=True)
                body["reason"] = note
                path = f"/documents/{document_id}/stage/corrections"
            else:
                body["note"] = note or None
                path = f"/documents/{document_id}/stage"
            try:
                state["data"] = api("POST", path, json=body)
            except Exception as exc:
                return say(str(exc)[:200], error=True)
            state["form"] = None
            say(f"Stage {'corrected to' if correcting else 'changed to'} {state['data']['stage']}.")
            if on_saved:
                on_saved()

        return ft.Container(
            content=ft.Column([
                ui.title("Correct the stage" if correcting else "Change the stage"),
                *([ui.hint("Use this to fix a mistake. The wrong entry stays in the history.")] if correcting else []),
                ft.Row([stage_field, date_field], spacing=12, wrap=True),
                committee_field,
                ft.Row([number_field, year_field], spacing=12, wrap=True),
                note_field,
                ft.Row([
                    ft.FilledButton("Save correction" if correcting else "Save stage", icon=ft.Icons.SAVE_OUTLINED, on_click=save),
                    ft.TextButton("Cancel", on_click=lambda _: switch(None)),
                ], spacing=8),
            ], spacing=10),
            padding=12,
            bgcolor=ui.tone("#F7FAFE", "#1B2430"),
            border_radius=10,
        )

    def say(text, error=False):
        state["message"] = (text, error)
        render()
        page.update()

    def switch(mode):
        # Built once per opening, so a message shown while it is open keeps what was typed.
        state["form"] = form(mode == "correct") if mode else None
        state["message"] = ("", False)
        render()
        page.update()

    def render():
        info = state["data"]
        stage = info.get("stage") or "No stage yet"
        text, error = state["message"]
        buttons = []
        if can_change and state["form"] is None:
            if info["allowed"]:
                buttons.append(ft.OutlinedButton("Change stage", icon=ft.Icons.ARROW_FORWARD, on_click=lambda _: switch("change")))
            buttons.append(ft.TextButton("Correct a mistake", icon=ft.Icons.EDIT_NOTE, on_click=lambda _: switch("correct")))
        history = info.get("history") or []
        section.controls = [
            ft.Row([ui.title("Stage"), ui.chip(stage, stage_color(info.get("stage")))], spacing=10,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            *([ft.Text(text, size=12, color=ft.Colors.RED_700 if error else ft.Colors.GREEN_700)] if text else []),
            *([ft.Row(buttons, spacing=8, wrap=True)] if buttons else []),
            *([state["form"]] if state["form"] else []),
            ft.Column([history_row(entry) for entry in history] or [ui.empty("No stage recorded yet.")], spacing=0),
        ]

    render()
    return section


def _is_enacted(info, stage):
    """Mirrors Backends/backend/stages.is_enacted using the order of `stages` from the backend."""
    order = info["stages"]
    enacted = info.get("enacted_stage")
    endings = {"Withdrawn", "Tabled", "Lost"}
    return stage not in endings and enacted in order and order.index(stage) >= order.index(enacted)
