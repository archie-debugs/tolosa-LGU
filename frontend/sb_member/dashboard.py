"""The SB Member dashboard: the first screen after login (the "Briefing" layout from the prototype).

A greeting with the member's position, then the next session beside today's documents. One column on a phone; two side by side on a tablet or laptop.
"""

from datetime import date

import flet as ft

from frontend.sb_member.upcoming import day_rows, days_until
from frontend.theme import PRIMARY

SHOWN_DOCUMENTS = 3
# Upcoming days on the dashboard, and documents shown for each; the rest are on Upcoming Documents.
SHOWN_DAYS = 2
SHOWN_UPCOMING_ITEMS = 3


def next_session(sessions, today):
    """The earliest session not yet held, on or after today."""
    coming = [s for s in sessions if s.get("status") != "Held" and s.get("held_on", "") >= today.isoformat()]
    return min(coming, key=lambda s: s["held_on"], default=None)


def my_member(members, username):
    """The member record in the current term linked to this account."""
    username = (username or "").lower()
    return next((m for m in members if m.get("is_active") and (m.get("username") or "").lower() == username), None)


def build(page, card, api, council_api, user, open_screen, open_document, file_actions):
    """`api` calls the SB Member backend, `council_api` the main backend; `open_screen(label)` goes to a sidebar screen.

    `file_actions(document)` gives the View PDF / Download buttons of an upcoming document.
    """
    dark = page.theme_mode == ft.ThemeMode.DARK
    ink = ft.Colors.BLUE_GREY_50 if dark else ft.Colors.BLUE_GREY_900
    muted = ft.Colors.BLUE_GREY_300 if dark else ft.Colors.BLUE_GREY_600
    today = date.today()

    def fetch(call, *args):
        # Each card loads on its own, so one failing backend call leaves the others showing.
        try:
            return call(*args), None
        except Exception as exc:
            return None, str(exc)

    def title(text, size=16):
        return ft.Text(text, size=size, weight=ft.FontWeight.BOLD, color=ink)

    def small(text, color=None, weight=None):
        return ft.Text(text, size=12, color=color or muted, weight=weight)

    def chip(text, color):
        return ft.Container(ft.Text(text, size=11, color=color, weight=ft.FontWeight.W_600),
                            bgcolor=ft.Colors.with_opacity(0.12, color), border_radius=10, padding=ft.padding.only(8, 3, 8, 3))

    def heading(icon, text, *extra):
        return ft.Row([ft.Icon(icon, color=PRIMARY), title(text), *extra], spacing=8)

    def go(label):
        return ft.TextButton(label[0], icon=ft.Icons.ARROW_FORWARD, on_click=lambda _: open_screen(label[1]))

    members, _ = fetch(council_api, "GET", "/council/members")
    member = my_member(members or [], user.get("username"))
    name = (member or {}).get("full_name") or user.get("full_name") or user.get("username") or "Member"
    initials = "".join(part[0] for part in name.replace("Hon.", "").split()[:2]).upper() or "SB"
    position = [chip(member["position"], PRIMARY), small(member.get("term_name") or "")] if member else [small("SB Member")]
    greeting = card(ft.Row([
        ft.CircleAvatar(content=ft.Text(initials, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD), bgcolor=PRIMARY, radius=26),
        ft.Column([
            small(today.strftime("%A, %B %d, %Y")),
            title(f"Good day, {name}", 18),
            ft.Row(position, spacing=8, wrap=True),
        ], spacing=4, expand=True),
    ], spacing=14))

    payload, error = fetch(council_api, "GET", "/council/sessions")
    coming = next_session((payload or {}).get("sessions", []), today)
    session_rows = [heading(ft.Icons.EVENT_AVAILABLE, "Next session")]
    if error:
        session_rows.append(small(f"Unable to load sessions: {error}"))
    elif not coming:
        session_rows.append(small("No session has been planned yet."))
    else:
        day = date.fromisoformat(coming["held_on"])
        session_rows[0].controls.append(chip(coming["status"], ft.Colors.GREEN_700 if coming["status"] == "Scheduled" else ft.Colors.BLUE_GREY_500))
        session_rows.append(ft.Row([
            ft.Container(content=ft.Column([
                ft.Text(day.strftime("%b").upper(), size=12, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                ft.Text(str(day.day), size=26, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                ft.Text(day.strftime("%a"), size=11, color=ft.Colors.WHITE),
            ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=PRIMARY, border_radius=14, padding=ft.padding.only(14, 8, 14, 8)),
            ft.Column([
                title(coming["title"], 15),
                small(day.strftime("%A, %B %d, %Y")),
                small(days_until(day, today), color=PRIMARY, weight=ft.FontWeight.BOLD),
            ], spacing=3, expand=True),
        ], spacing=14))
        business, _ = fetch(council_api, "GET", f"/council/sessions/{coming['id']}/business")
        if business is not None:
            count = sum(len(section["items"]) for section in business.get("sections", []))
            session_rows.append(small(f"Order of business: {count} item{'' if count == 1 else 's'}" if count else "The order of business isn't ready yet."))
        session_rows.append(go(("See the sessions", "Sessions")))
    session_card = card(ft.Column(session_rows, spacing=10))

    payload, error = fetch(api, "GET", "/todays-documents")
    items = (payload or {}).get("items", [])
    document_rows = [heading(ft.Icons.EVENT_NOTE, "Today's documents", chip(str(len(items)), PRIMARY))]
    if error:
        document_rows.append(small(f"Unable to load today's documents: {error}"))
    elif not items:
        document_rows.append(small("No documents have been set for today yet."))
    for document in items[:SHOWN_DOCUMENTS]:
        moa = document.get("kind") == "MOA"
        kind = "MOA" if moa else document.get("document_type") or "Document"
        number = "" if moa else f"No. {document.get('document_number') or '-'} / {document.get('series_year') or '-'}"
        document_rows.append(ft.Container(
            content=ft.Row([
                ft.Container(width=4, height=44, bgcolor=PRIMARY, border_radius=2),
                ft.Column([
                    ft.Row([chip(kind, PRIMARY), small(number)], spacing=8, wrap=True),
                    ft.Text(document.get("title") or "Untitled", size=14, weight=ft.FontWeight.W_600, color=ink),
                    *([small(document["note"])] if document.get("note") else []),
                ], spacing=3, expand=True),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, color=muted),
            ], spacing=10),
            padding=ft.padding.only(0, 6, 0, 6), on_click=lambda _, d=document: open_document(d),
        ))
    if items:
        document_rows.append(go((f"See all {len(items)}", "Today's Documents")))
    document_card = card(ft.Column(document_rows, spacing=6))

    payload, error = fetch(api, "GET", "/upcoming-documents")
    upcoming = (payload or {}).get("days", [])
    upcoming_rows = [heading(ft.Icons.UPCOMING_OUTLINED, "Next Sessions Documents")]
    if error:
        upcoming_rows.append(small(f"Unable to load upcoming documents: {error}"))
    elif not upcoming:
        upcoming_rows.append(small("No documents have been set for a later day yet."))
    for index, day_entry in enumerate(upcoming[:SHOWN_DAYS]):
        if index:
            upcoming_rows.append(ft.Divider(height=1))
        upcoming_rows += day_rows(day_entry, today, ink, muted, file_actions, limit=SHOWN_UPCOMING_ITEMS)
    if upcoming:
        upcoming_rows.append(go(("See all upcoming documents", "Upcoming Documents")))
    upcoming_card = card(ft.Column(upcoming_rows, spacing=8))

    return ft.Column([
        greeting,
        ft.ResponsiveRow([
            ft.Column([session_card], spacing=14, col={"xs": 12, "md": 5}),
            ft.Column([document_card, upcoming_card], spacing=14, col={"xs": 12, "md": 7}),
        ], spacing=14, run_spacing=14),
    ], spacing=14, tight=True)
