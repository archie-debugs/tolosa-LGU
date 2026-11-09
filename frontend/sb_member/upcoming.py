"""Upcoming sessions' order of business for SB Members (layout A of the prototype on branch
prototype/upcoming-session-documents): each session with its documents grouped by section.

Members can view a document's PDF and download it ahead of the session, but not open its details.
"""

from datetime import date

import flet as ft

from frontend.theme import PRIMARY


def days_until(day, today):
    days = (day - today).days
    return "Today" if days == 0 else "Tomorrow" if days == 1 else f"In {days} days"


def session_rows(session, today, ink, muted, actions, limit=None):
    """The session's date and title, then its items numbered under their section headings.

    `actions(document)` gives the buttons for an item's file; `limit` caps the items shown.
    """
    day = date.fromisoformat(session["held_on"])
    rows = [ft.Row([
        ft.Container(ft.Column([
            ft.Text(day.strftime("%b").upper(), size=11, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
            ft.Text(str(day.day), size=22, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
        ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=PRIMARY, border_radius=12, padding=ft.padding.only(12, 6, 12, 6)),
        ft.Column([
            ft.Text(session["title"], size=16, weight=ft.FontWeight.BOLD, color=ink),
            ft.Text(f"{day.strftime('%A, %B %d, %Y')} · {days_until(day, today)}", size=12, color=muted),
        ], spacing=2, expand=True),
    ], spacing=12)]
    total = sum(len(section["items"]) for section in session["sections"])
    if not total:
        return rows + [ft.Text("The order of business isn't ready yet.", size=12, color=muted)]
    number = 0
    for section in session["sections"]:
        if limit is not None and number >= limit:
            break
        rows.append(ft.Text(section["label"].upper(), size=11, weight=ft.FontWeight.BOLD, color=PRIMARY))
        for item in section["items"]:
            if limit is not None and number >= limit:
                break
            number += 1
            document = item.get("document")
            reference = f"{document.get('document_type') or 'Document'} · {document.get('tracking_number') or '-'}" if document else "No file"
            rows.append(ft.Row([
                ft.Text(f"{number}.", width=24, size=13, color=muted),
                ft.Column([
                    ft.Text((document or {}).get("title") or item.get("title") or "Untitled", size=13, weight=ft.FontWeight.W_600, color=ink),
                    ft.Text(reference, size=11, color=muted),
                ], spacing=1, expand=True),
                *(actions(document) if document and document.get("attachments") else []),
            ], spacing=8))
    if number < total:
        rows.append(ft.Text(f"and {total - number} more", size=12, color=muted))
    return rows
