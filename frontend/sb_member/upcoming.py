"""Upcoming documents for SB Members: each later day's documents under its date.

Members can view a document's PDF and download it before its day, but not open its details.
"""

from datetime import date

import flet as ft

from frontend.theme import PRIMARY


def days_until(day, today):
    days = (day - today).days
    return "Today" if days == 0 else "Tomorrow" if days == 1 else f"In {days} days"


def day_rows(day_entry, today, ink, muted, actions, limit=None):
    """The day's date, then its documents numbered.

    `actions(document)` gives the buttons for a document's file; `limit` caps the documents shown.
    """
    day = date.fromisoformat(day_entry["date"])
    rows = [ft.Row([
        ft.Container(ft.Column([
            ft.Text(day.strftime("%b").upper(), size=11, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
            ft.Text(str(day.day), size=22, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
        ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=PRIMARY, border_radius=12, padding=ft.padding.only(12, 6, 12, 6)),
        ft.Column([
            ft.Text(day.strftime("%A, %B %d, %Y"), size=16, weight=ft.FontWeight.BOLD, color=ink),
            ft.Text(days_until(day, today), size=12, color=muted),
        ], spacing=2, expand=True),
    ], spacing=12)]
    items = day_entry["items"]
    for number, document in enumerate(items[:limit], start=1):
        moa = document.get("kind") == "MOA"
        reference = f"MOA · {document['attachments'][0]['filename']}" if moa and document.get("attachments") else \
            f"{document.get('document_type') or 'Document'} · {document.get('tracking_number') or '-'}"
        rows.append(ft.Row([
            ft.Text(f"{number}.", width=24, size=13, color=muted),
            ft.Column([
                ft.Text(document.get("title") or "Untitled", size=13, weight=ft.FontWeight.W_600, color=ink),
                ft.Text(reference, size=11, color=muted),
                *([ft.Text(document["note"], size=12, italic=True, color=muted)] if document.get("note") else []),
            ], spacing=1, expand=True),
            *(actions(document) if document.get("attachments") else [ft.Text("No file", size=12, color=muted)]),
        ], spacing=8))
    if limit is not None and len(items) > limit:
        rows.append(ft.Text(f"and {len(items) - limit} more", size=12, color=muted))
    return rows
