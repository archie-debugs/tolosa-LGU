"""Temporary documents on Documents for SB Members: ordinances and uploaded MOAs for one day.

After its day an MOA is archived for 30 days; an ordinance is not (Backends/backend/routes/temporary_documents.py);
the archive card lets an employee keep it 30 more days or delete it.
"""

from datetime import date

import flet as ft

from frontend.admin.registration import UNSUPPORTED, error_detail, is_image, upload_finished
from frontend.admin.todays_documents import document_label


def short_day(value):
    return date.fromisoformat(value).strftime("%b %d, %Y")


class TemporaryDocuments:
    """Two cards for the page: this day's temporary documents, and the archive.

    `api(method, path, **kwargs)` calls the main backend. `files` is a PickerFiles for the MOA upload.
    `card_title(icon, title, *extra, subtitle=)` and `empty_state(message)` draw like the rest of the page.
    Call `load(day, today)` whenever the page's day changes.
    """

    def __init__(self, page, api, widgets, files, card_title, empty_state, open_details=None):
        self.page, self.api, self.widgets, self.files = page, api, widgets, files
        self.card_title, self.empty_state, self.open_details = card_title, empty_state, open_details
        self.state = {"day": None, "today": None, "items": [], "archive": [], "results": [], "mode": "ordinance",
                      "file": None, "pages": [], "busy": False, "confirm": None, "notice": ("", False)}
        self.count_text = ft.Text("", size=13, color=widgets.body_color())
        self.notice_text = ft.Text("", size=12)
        self.list_column = ft.Column(spacing=0)
        self.add_column = ft.Column(spacing=12)
        self.archive_column = ft.Column(spacing=0)
        self.due_badge = ft.Row([], spacing=0)
        self.search_field = ft.TextField(
            hint_text="Search ordinances by title or number", prefix_icon=ft.Icons.SEARCH, expand=True, height=46,
            border_radius=10, border_color=widgets.line_color(), focused_border_color=ft.Colors.BLUE_700,
            content_padding=ft.Padding(12, 4, 12, 4), on_submit=lambda _: self.search(),
        )
        self.title_field = ft.TextField(hint_text="Title of the MOA", border_radius=10, border_color=widgets.line_color())
        self.progress = ft.ProgressBar(value=None, visible=False)
        self.day_card = ft.Column([
            card_title(ft.Icons.HOURGLASS_TOP, "Temporary documents", self.count_text,
                       subtitle="Ordinances and MOAs for this day only. After the day, MOAs move to the archive below."),
            self.notice_text, self.list_column, self.add_column,
        ], spacing=12)
        self.archive_card = ft.Column([
            card_title(ft.Icons.INVENTORY_2_OUTLINED, "Archived MOAs", self.due_badge,
                       subtitle="Kept 30 days after their day, then flagged here and in notifications. Keep or delete."),
            self.archive_column,
        ], spacing=12)

    # ---------- data ----------
    def editable(self):
        return self.state["day"] >= self.state["today"]

    def notify(self, message, error=False):
        self.state["notice"] = (message, error)

    def load(self, day, today, update=False):
        if day != self.state["day"]:
            self.notify("")  # a message like "Added ... " belongs to the day it was made on
        self.state.update(day=day, today=today, confirm=None)
        try:
            payload = self.api("GET", "/temporary-documents", params={"date": day.isoformat()})
            self.state["items"] = payload.get("items", [])
            # The server's day, so a screen left open past midnight stops offering to add to yesterday.
            self.state["today"] = date.fromisoformat(payload.get("today") or today.isoformat())
            self.state["archive"] = self.api("GET", "/temporary-documents/archive").get("items", [])
        except Exception as exc:
            self.state.update(items=[], archive=[])
            self.notify(f"Unable to load temporary documents: {error_detail(exc)[0]}", error=True)
        if not self.state["results"] and self.editable():
            self.fetch_ordinances()
        self.render(update)

    def fetch_ordinances(self):
        params = {"archived": "false", "document_type": "Ordinance", "page": 1, "page_size": 10, "sort_by": "created_at", "sort_order": "desc"}
        query = (self.search_field.value or "").strip()
        if query:
            params["search"] = query
        try:
            self.state["results"] = self.api("GET", "/documents", params=params).get("items", [])
        except Exception as exc:
            self.state["results"] = []
            self.notify(f"Unable to load ordinances: {error_detail(exc)[0]}", error=True)

    def reload(self, message=None, error=False):
        if message is not None:
            self.notify(message, error)
        self.load(self.state["day"], self.state["today"], update=True)

    # ---------- actions ----------
    def search(self):
        self.notify("")
        self.fetch_ordinances()
        self.render(True)

    def set_mode(self, mode):
        self.state["mode"] = mode
        self.render(True)

    def add_ordinance(self, document):
        try:
            self.api("POST", "/temporary-documents/ordinance", json={"scheduled_for": self.state["day"].isoformat(), "document_id": document["id"]})
            self.reload(f"Added {document.get('tracking_number') or 'the ordinance'} for {self.state['day'].strftime('%b %d, %Y')}.")
        except Exception as exc:
            self.reload(f"Unable to add: {error_detail(exc)[0]}", error=True)

    def remove(self, entry):
        try:
            self.api("DELETE", f"/temporary-documents/{entry['id']}")
            self.reload("Removed." if not entry.get("archived") else "Deleted for good.")
        except Exception as exc:
            self.reload(f"Unable to remove: {error_detail(exc)[0]}", error=True)

    def ask_delete(self, entry):
        self.state["confirm"] = entry["id"]
        self.render(True)

    def keep(self, entry):
        try:
            kept = self.api("POST", f"/temporary-documents/{entry['id']}/keep")
            self.reload(f"Kept until {short_day(kept['due_on'])}.")
        except Exception as exc:
            self.reload(f"Unable to keep it: {error_detail(exc)[0]}", error=True)

    def view(self, entry):
        if entry["kind"] == "Ordinance":
            if self.open_details:
                self.open_details(entry["document"])
            return
        try:
            self.page.launch_url(self.api("POST", f"/temporary-documents/{entry['id']}/download-token")["download_url"])
        except Exception as exc:
            self.notify(f"Unable to open the file: {error_detail(exc)[0]}", error=True)
            self.render(True)

    def pick_file(self):
        """One file, or several photos or scans of the MOA's pages (joined into one PDF), as in Register Document."""
        def picked(chosen):
            if not chosen:
                return
            names = [item["name"] for item in chosen]
            if len(chosen) > 1 and not all(is_image(name) for name in names):
                self.notify("Choose one file, or several photos or scans (JPG, PNG) of one MOA's pages.", error=True)
            elif len(set(names)) != len(names):
                self.notify("Two of the photos have the same name. Rename one, then choose them again.", error=True)
            else:
                self.state["file"], self.state["pages"] = chosen[0], chosen[1:]
                self.title_field.value = chosen[0]["name"].rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()
                self.notify("")
            self.render(True)

        self.files.pick(True, picked)

    def upload(self):
        chosen, title = self.state["file"], (self.title_field.value or "").strip()
        if not chosen or not title:
            self.notify("Choose a file and give it a title.", error=True)
            self.render(True)
            return
        day = self.state["day"]
        chosen = [chosen, *self.state["pages"]]
        self.set_busy(True)
        try:
            created = self.api("POST", "/documents/uploads/create_tmp_uploads",
                               json={"files": [{"filename": item["name"], "size": item["size"]} for item in chosen]})
        except Exception as exc:
            self.fail(f"The file could not be prepared for upload: {error_detail(exc)[0]}")
            return
        items = created.get("files") or []
        if len(items) != len(chosen) or not all(item.get("ok") for item in items):
            self.fail(UNSUPPORTED.replace("registered", "uploaded"))
            return
        done = {item["name"]: 0.0 for item in chosen}  # name -> progress, 1.0 once uploaded

        def on_progress(name, value, error):
            if name not in done or not self.state["busy"]:
                return
            if error:
                self.fail(f"The upload failed: {error}")
                return
            done[name] = 1.0 if upload_finished(value) else value
            if all(value == 1.0 for value in done.values()):
                self.save_moa([item["tmp_name"] for item in items], title, day)
            else:
                self.progress.value = sum(done.values()) / len(done)
                self.page.update()

        self.progress.value = 0
        self.files.upload([(item["name"], staged["upload_url"]) for item, staged in zip(chosen, items)], on_progress)

    def save_moa(self, tmp_names, title, day):
        try:
            self.api("POST", "/temporary-documents/moa", json={
                "scheduled_for": day.isoformat(), "tmp_name": tmp_names[0], "page_tmp_names": tmp_names[1:], "title": title,
            })
        except Exception as exc:
            self.fail(f"Unable to save the MOA: {error_detail(exc)[0]}")
            return
        self.state.update(busy=False, file=None, pages=[])
        self.title_field.value = ""
        self.reload(f"Uploaded \"{title}\" for {day.strftime('%b %d, %Y')}.")

    def set_busy(self, busy):
        self.state["busy"] = busy
        self.render(True)

    def fail(self, message):
        self.state["busy"] = False
        self.notify(message, error=True)
        self.render(True)

    # ---------- drawing ----------
    def kind_chip(self, entry):
        return self.widgets.chip(entry["kind"], ft.Colors.PURPLE_700 if entry["kind"] == "MOA" else ft.Colors.BLUE_700)

    def reference(self, entry):
        return document_label(entry["document"]) if entry["kind"] == "Ordinance" else entry.get("filename") or "MOA"

    def text_column(self, top, title):
        return ft.Column([
            ft.Text(top, size=12, weight=ft.FontWeight.BOLD, color=self.widgets.link_color()),
            ft.Text(title or "Untitled", size=13, weight=ft.FontWeight.W_600, color=self.widgets.heading_color()),
        ], spacing=2, expand=True)

    def entry_row(self, index, entry):
        actions = [ft.TextButton("Open file" if entry["kind"] == "MOA" else "View", on_click=lambda _, e=entry: self.view(e))]             if entry["kind"] == "MOA" or self.open_details else []
        if self.editable():
            actions.append(ft.TextButton("Remove", style=ft.ButtonStyle(color=ft.Colors.RED_700), on_click=lambda _, e=entry: self.remove(e)))
        return self.widgets.list_row([
            ft.Text(f"{index + 1}.", width=28, size=14, weight=ft.FontWeight.BOLD, color=self.widgets.muted_color()),
            self.kind_chip(entry), self.text_column(self.reference(entry), entry.get("title")),
            *([self.widgets.chip("Archived · hidden from members", ft.Colors.RED_700)] if (entry.get("document") or {}).get("archived") else []),
            *actions,
        ], stack_on_phone=True)

    def due_chip(self, entry):
        days = entry["days_left"]
        if days <= 0:
            return self.widgets.chip("Due for deletion", ft.Colors.RED_700)
        if days <= 7:
            return self.widgets.chip(f"Deleted in {days} day{'s' if days != 1 else ''}", ft.Colors.AMBER_800)
        return self.widgets.chip(f"Kept until {short_day(entry['due_on'])}", ft.Colors.GREEN_700)

    def archive_row(self, entry):
        delete = (
            ft.FilledButton("Confirm delete", style=ft.ButtonStyle(bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE), on_click=lambda _, e=entry: self.remove(e))
            if self.state["confirm"] == entry["id"] else
            ft.TextButton("Delete", style=ft.ButtonStyle(color=ft.Colors.RED_700), on_click=lambda _, e=entry: self.ask_delete(e))
        )
        return self.widgets.list_row([
            self.kind_chip(entry),
            self.text_column(f"For {short_day(entry['scheduled_for'])} · {self.reference(entry)}", entry.get("title")),
            self.due_chip(entry),
            ft.OutlinedButton("Keep 30 more days", on_click=lambda _, e=entry: self.keep(e)),
            delete,
        ], stack_on_phone=True)

    def ordinance_area(self):
        on_day = {entry["document"]["id"] for entry in self.state["items"] if entry["kind"] == "Ordinance"}
        rows = []
        for document in self.state["results"]:
            action = (self.widgets.chip("On this day", ft.Colors.GREEN_700) if document["id"] in on_day
                      else ft.OutlinedButton("Add", icon=ft.Icons.ADD, on_click=lambda _, d=document: self.add_ordinance(d)))
            rows.append(self.widgets.list_row([self.text_column(document_label(document), document.get("title")), action]))
        return [
            ft.Row([self.search_field, ft.TextButton("Search", icon=ft.Icons.SEARCH, on_click=lambda _: self.search())], spacing=8),
            self.widgets.hint("Ordinances only, newest first."),
            *(rows or [self.empty_state("No ordinance matches.")]),
        ]

    def moa_area(self):
        chosen, pages = self.state["file"], self.state["pages"]
        controls = [
            self.widgets.hint("PDF or Word, or photos or scans (JPG, PNG) of its pages, saved as one PDF. "
                              "It stays for this day, then is archived for 30 days."),
            ft.Row([
                ft.OutlinedButton("Choose file…", icon=ft.Icons.ATTACH_FILE, on_click=lambda _: self.pick_file(), disabled=self.state["busy"]),
                ft.Text(f"{1 + len(pages)} pages, joined into one PDF" if chosen and pages else chosen["name"] if chosen else "No file chosen",
                        size=13, color=self.widgets.body_color()),
            ], spacing=12, wrap=True),
            *([self.widgets.hint("In this order: " + ", ".join(item["name"] for item in [chosen, *pages]))] if chosen and pages else []),
            *([self.widgets.hint("Saved as a PDF.")] if chosen and not pages and is_image(chosen["name"]) else []),
        ]
        if chosen:
            controls += [
                self.title_field,
                ft.FilledButton("Uploading…" if self.state["busy"] else "Upload MOA", icon=ft.Icons.UPLOAD_FILE, disabled=self.state["busy"],
                                on_click=lambda _: self.upload()),
            ]
        self.progress.visible = self.state["busy"]
        return controls + [self.progress]

    def mode_button(self, mode, label, icon):
        selected = self.state["mode"] == mode
        return ft.FilledButton(label, icon=icon, on_click=lambda _: self.set_mode(mode)) if selected else ft.OutlinedButton(label, icon=icon, on_click=lambda _: self.set_mode(mode))

    def render(self, update=False):
        items, archive = self.state["items"], self.state["archive"]
        self.count_text.value = f"{len(items)} for this day"
        message, error = self.state["notice"]
        self.notice_text.value = message
        self.notice_text.color = ft.Colors.RED_700 if error else ft.Colors.GREEN_700
        self.notice_text.visible = bool(message)
        self.list_column.controls = [self.entry_row(index, entry) for index, entry in enumerate(items)] or [
            self.empty_state("No temporary documents for this day." if self.editable() else "No temporary documents were set for this day.")
        ]
        self.add_column.visible = self.editable()
        if self.editable():
            self.add_column.controls = [
                ft.Row([
                    self.mode_button("ordinance", "Add an ordinance", ft.Icons.GAVEL),
                    self.mode_button("moa", "Upload a MOA", ft.Icons.UPLOAD_FILE),
                ], spacing=8, wrap=True),
                *(self.ordinance_area() if self.state["mode"] == "ordinance" else self.moa_area()),
            ]
        due = sum(1 for entry in archive if entry["days_left"] <= 0)
        self.due_badge.controls = [self.widgets.chip(f"{due} due", ft.Colors.RED_700)] if due else []
        self.archive_column.controls = [self.archive_row(entry) for entry in archive] or [self.empty_state("Nothing archived.")]
        if update:
            self.page.update()
