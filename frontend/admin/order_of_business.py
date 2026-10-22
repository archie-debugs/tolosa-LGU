"""The Order of business card on a session's page: items by section, their outcomes and votes.

Before the session is Held, items are added (suggested by stage or by hand), reordered and removed,
and outcomes and votes are set freely. Marking the session held enters each measure's stages from
its outcome. After that, outcomes and votes are corrected with a reason (docs/adr/0003).
"""

import flet as ft

from frontend.admin.documents import DROPDOWN_EVENT

NONE = "none"  # dropdown key for "no outcome" / "no vote"
VOTE_CHOICES = ["Yes", "No", "Abstain"]


def vote_text(vote):
    """"Nominal vote 8-1-0, Carried" for an item's line."""
    return f"{vote['method']} vote {vote['yes']}-{vote['no']}-{vote['abstain']}, {vote['result']}"


def build_business_card(page, ui, surface_card, ctx, *, can_manage):
    """`ctx` is the session page's helpers: state, call, dialog_call, open_dialog, show and update.

    state["business"] holds the GET /business payload and state["session"] the session detail.
    """
    state = ctx["state"]
    business = state["business"]
    session = state["session"]
    base = f"/council/sessions/{session['id']}/business"
    editable = business["editable"] and can_manage

    def refresh(result, text):
        if result is not None:
            state["business"] = result
            ctx["show"](text)
        ctx["update"]()

    # ----- items -----

    def move(section, item, step):
        ids = [entry["id"] for entry in section["items"]]
        index = ids.index(item["id"])
        ids[index], ids[index + step] = ids[index + step], ids[index]
        refresh(ctx["call"]("PUT", f"{base}/order", json={"section": section["key"], "item_ids": ids}), "Order saved.")

    def remove(item):
        refresh(ctx["call"]("DELETE", f"{base}/items/{item['id']}"), f"Removed {item['title']}.")

    def item_row(number, section, index, item):
        doc = item.get("document")
        detail = [doc["tracking_number"], doc.get("document_type") or ""] if doc else ["No document"]
        if doc and doc.get("stage"):
            detail.append(f"at {doc['stage']}")
        lines = [
            ft.Text(f"{number}  {item['title']}", size=14, weight=ft.FontWeight.W_600, color=ui.heading_color()),
            ft.Text(" · ".join(part for part in detail if part), size=12, color=ui.muted_color()),
        ]
        status = []
        outcome, vote = item.get("outcome"), item.get("vote")
        if outcome:
            status.append(ui.chip(outcome["outcome"], ft.Colors.GREEN_700 if not business["editable"] else ft.Colors.BLUE_700))
        if vote:
            status.append(ft.Text(vote_text(vote), size=12, color=ui.body_color()))
        if status:
            lines.append(ft.Row(status, spacing=8, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER))
        if outcome and outcome.get("stages") and not business["editable"]:
            lines.append(ft.Text("Stage: " + " → ".join(outcome["stages"]), size=12, color=ui.muted_color()))
        elif outcome and outcome.get("note"):
            lines.append(ft.Text(outcome["note"], size=12, color=ui.body_color()))
        for entry in item.get("outcome_history") or []:
            if entry.get("is_correction"):
                lines.append(ft.Text(f"Outcome corrected to {entry['outcome']} by {entry.get('recorded_by') or '-'}: {entry.get('note') or ''}",
                                     size=11, color=ft.Colors.AMBER_800))
        for entry in item.get("vote_history") or []:
            if entry.get("is_correction"):
                lines.append(ft.Text(f"Vote corrected to {vote_text(entry)} by {entry.get('recorded_by') or '-'}: {entry.get('note') or ''}",
                                     size=11, color=ft.Colors.AMBER_800))
        actions = []
        if editable:
            count = len(section["items"])
            actions = [
                ft.IconButton(ft.Icons.ARROW_UPWARD, tooltip="Move up", disabled=index == 0,
                              on_click=lambda _: move(section, item, -1)),
                ft.IconButton(ft.Icons.ARROW_DOWNWARD, tooltip="Move down", disabled=index == count - 1,
                              on_click=lambda _: move(section, item, 1)),
                ft.TextButton("Outcome", on_click=lambda _: open_outcome(item)),
                ft.TextButton("Vote", on_click=lambda _: open_vote(item)),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Remove", on_click=lambda _: remove(item)),
            ]
        elif can_manage:
            actions = [
                ft.TextButton("Correct outcome", on_click=lambda _: open_outcome(item)),
                ft.TextButton("Correct vote", on_click=lambda _: open_vote(item)),
            ]
        return ft.Container(
            content=ft.ResponsiveRow([
                ft.Column(lines, spacing=3, col={"xs": 12, "md": 7}),
                ft.Row(actions, spacing=2, wrap=True, alignment=ft.MainAxisAlignment.END, col={"xs": 12, "md": 5},
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding(14, 10, 8, 10),
            bgcolor=ui.tone("#F7FAFE", "#1B2430"),
            border_radius=12,
        )

    def section_block(position, section):
        rows = [item_row(f"{position}.{index + 1}", section, index, item) for index, item in enumerate(section["items"])]
        return ft.Column([
            ft.Text(f"{position}. {section['label']}", size=14, weight=ft.FontWeight.BOLD, color=ui.heading_color()),
            *(rows or [ft.Text("Nothing listed.", size=12, color=ui.muted_color())]),
        ], spacing=6)

    # ----- adding items -----

    section_options = [ft.dropdown.Option(key=section["key"], text=section["label"]) for section in business["sections"]]

    def open_add_item():
        section = ft.Dropdown(label="Section", value="other", width=360, options=section_options)
        search = ft.TextField(label="Find a document", hint_text="Tracking number or title", width=260)
        found = ft.Dropdown(label="Document", width=360, options=[], visible=False)
        title = ft.TextField(label="Or a title, for an item without a document", width=360)

        def find(_):
            results = ctx["call"]("GET", f"{base}/documents", params={"search": (search.value or "").strip()}) or []
            found.options = [ft.dropdown.Option(key=str(doc["id"]), text=f"{doc['tracking_number']} · {doc['title'][:60]}") for doc in results]
            found.value = found.options[0].key if found.options else None
            found.visible = True
            found.label = "Document" if results else "No matching documents"
            page.update()

        def on_save():
            if found.value:
                body = {"section": section.value, "document_id": int(found.value)}
            elif (title.value or "").strip():
                body = {"section": section.value, "title": title.value.strip()}
            else:
                raise ValueError("Find a document, or give the item a title.")
            state["business"] = ctx["dialog_call"]("POST", f"{base}/items", json=body)
            ctx["show"]("Item added.")

        ctx["open_dialog"]("Add item", [section, ft.Row([search, ft.OutlinedButton("Find", icon=ft.Icons.SEARCH, on_click=find)],
                                                        spacing=8, wrap=True), found, title], "Add", on_save)

    def open_suggestions():
        suggested = ctx["call"]("GET", f"{base}/suggestions")
        if suggested is None:
            ctx["update"]()
            return
        if not suggested:
            ctx["show"]("No measures are waiting for this session.")
            ctx["update"]()
            return
        boxes = [(ft.Checkbox(value=True, label=f"{row['document']['tracking_number']} · {row['document']['title'][:50]}"), row)
                 for row in suggested]
        lines = []
        for box, row in boxes:
            lines.append(ft.Column([box, ft.Text(f"{row['section_label']} · {row['reason']}", size=11, color=ui.muted_color())], spacing=0))

        def on_save():
            chosen = [row for box, row in boxes if box.value]
            if not chosen:
                raise ValueError("Tick at least one measure.")
            for row in chosen:
                state["business"] = ctx["dialog_call"]("POST", f"{base}/items",
                                                       json={"section": row["section"], "document_id": row["document"]["id"]})
            ctx["show"](f"Added {len(chosen)} item(s).")

        ctx["open_dialog"]("Suggested items", [ui.hint("Measures ready for this session by their stage, and unfinished business."),
                                               ft.Column(lines, spacing=6, scroll=ft.ScrollMode.AUTO, height=min(360, 64 * len(lines)))],
                           "Add selected", on_save)

    # ----- outcomes -----

    committees = {"list": None}

    def committee_options():
        if committees["list"] is None:
            committees["list"] = ctx["call"]("GET", "/council/committees?active_only=true") or []
        return [ft.dropdown.Option(key=str(item["id"]), text=item["name"]) for item in committees["list"]]

    def open_outcome(item):
        held = not business["editable"]
        rules = {choice["outcome"]: choice for choice in item["outcome_choices"]}
        current = (item.get("outcome") or {}).get("outcome")
        options = ([] if held else [ft.dropdown.Option(key=NONE, text="No outcome yet")]) + [ft.dropdown.Option(name) for name in rules]
        outcome = ft.Dropdown(label="Outcome", width=320, options=options, value=current or (None if held else NONE),
                              **{DROPDOWN_EVENT: lambda _: show_fields()})
        committee = ft.Dropdown(label="Committee", width=320, options=committee_options(), visible=False)
        has_number = bool((item.get("document") or {}).get("has_number"))
        number = ft.TextField(label="Enacted number", width=150, visible=False)
        year = ft.TextField(label="Series year", width=150, value=session["held_on"][:4], visible=False)
        note = ft.TextField(label="Reason (required)" if held else "Note (optional)", multiline=True, min_lines=1, max_lines=3,
                            value="" if held else ((item.get("outcome") or {}).get("note") or ""))

        def show_fields():
            rule = rules.get(outcome.value) or {}
            committee.visible = bool(rule.get("committee"))
            number.visible = year.visible = bool(rule.get("number")) and not has_number
            page.update()

        def on_save():
            if not outcome.value:
                raise ValueError("Choose the outcome.")
            if outcome.value == NONE:
                state["business"] = ctx["dialog_call"]("PUT", f"{base}/items/{item['id']}/outcome", json={"outcome": None})
                ctx["show"]("Outcome cleared.")
                return
            body = {"outcome": outcome.value}
            if committee.visible:
                body["committee_id"] = int(committee.value) if committee.value else None
            if number.visible:
                if not (year.value or "").strip().isdigit():
                    raise ValueError("The series year must be a year like 2026.")
                body["document_number"], body["series_year"] = (number.value or "").strip(), int(year.value)
            if held:
                if not (note.value or "").strip():
                    raise ValueError("Say why the outcome is being corrected.")
                body["reason"] = note.value.strip()
                state["business"] = ctx["dialog_call"]("POST", f"{base}/items/{item['id']}/outcome/corrections", json=body)
                ctx["show"]("Outcome corrected; the measure's stage was corrected to match.")
            else:
                body["note"] = (note.value or "").strip() or None
                state["business"] = ctx["dialog_call"]("PUT", f"{base}/items/{item['id']}/outcome", json=body)
                ctx["show"]("Outcome recorded.")

        hint = ("The earlier outcome stays in the record, and the measure's stage is corrected to match." if held
                else "A measure's stage moves when the session is marked held.")
        ctx["open_dialog"](("Correct the outcome of " if held else "Outcome of ") + item["title"][:60],
                           [outcome, committee, ft.Row([number, year], spacing=12, wrap=True), note, ui.hint(hint)], "Save", on_save)
        show_fields()

    # ----- votes -----

    def open_vote(item):
        held = not business["editable"]
        current = item.get("vote") or {}
        options = ([] if held else [ft.dropdown.Option(key=NONE, text="No vote")]) + [ft.dropdown.Option("Voice"), ft.dropdown.Option("Nominal")]
        method = ft.Dropdown(label="Vote", width=200, options=options, value=current.get("method") or "Voice",
                             **{DROPDOWN_EVENT: lambda _: show_fields()})
        tally = [ft.TextField(label=label, width=96, value=str(current.get(key, 0) or "")) for label, key in
                 (("Yes", "yes"), ("No", "no"), ("Abstain", "abstain"))]
        cast = {row["member_id"]: row["vote"] for row in current.get("members") or []}
        member_fields = []
        for row in session["attendance"]:
            field = ft.Dropdown(label=row["full_name"], width=300, dense=True, value=cast.get(row["member_id"], NONE),
                                options=[ft.dropdown.Option(key=NONE, text="Did not vote")] + [ft.dropdown.Option(value) for value in VOTE_CHOICES])
            member_fields.append((row["member_id"], field))
        members_box = ft.Column([field for _, field in member_fields], spacing=6, scroll=ft.ScrollMode.AUTO,
                                height=min(300, 56 * max(len(member_fields), 1)))
        result = ft.Dropdown(label="Result", width=200, value=current.get("result") or "Carried",
                             options=[ft.dropdown.Option("Carried"), ft.dropdown.Option("Lost")])
        reason = ft.TextField(label="Reason (required)", multiline=True, min_lines=1, max_lines=3, visible=held)

        def show_fields():
            for field in tally:
                field.visible = method.value == "Voice"
            members_box.visible = method.value == "Nominal"
            result.visible = method.value != NONE
            page.update()

        def on_save():
            if method.value == NONE:
                state["business"] = ctx["dialog_call"]("PUT", f"{base}/items/{item['id']}/vote", json={"method": None})
                ctx["show"]("Vote cleared.")
                return
            body = {"method": method.value, "result": result.value}
            if method.value == "Voice":
                values = [(field.value or "0").strip() for field in tally]
                if not all(value.isdigit() for value in values):
                    raise ValueError("The tally must be whole numbers.")
                body.update(yes=int(values[0]), no=int(values[1]), abstain=int(values[2]))
            else:
                body["members"] = [{"member_id": member_id, "vote": field.value} for member_id, field in member_fields
                                   if field.value and field.value != NONE]
            if held:
                if not (reason.value or "").strip():
                    raise ValueError("Say why the vote is being corrected.")
                body["reason"] = reason.value.strip()
                state["business"] = ctx["dialog_call"]("POST", f"{base}/items/{item['id']}/vote/corrections", json=body)
                ctx["show"]("Vote corrected.")
            else:
                state["business"] = ctx["dialog_call"]("PUT", f"{base}/items/{item['id']}/vote", json=body)
                ctx["show"]("Vote recorded.")

        ctx["open_dialog"](("Correct the vote on " if held else "Vote on ") + item["title"][:60],
                           [method, ft.Row(tally, spacing=8, wrap=True), members_box, result, reason,
                            ui.hint("A nominal vote records each member's vote; its tally is counted from them.")], "Save", on_save)
        show_fields()

    # ----- the card -----

    if business["editable"]:
        subtitle = "Items in their fixed sections. A measure's stage moves from its outcome when the session is marked held."
    else:
        subtitle = "Held: outcomes and votes are corrected with a reason."
    header_actions = []
    if editable:
        header_actions = [ft.Row([
            ft.ElevatedButton("Suggested items", icon=ft.Icons.AUTO_AWESOME_OUTLINED, on_click=lambda _: open_suggestions()),
            ft.OutlinedButton("Add item", icon=ft.Icons.ADD, on_click=lambda _: open_add_item()),
        ], spacing=8, wrap=True)]
    return surface_card(ft.Column([
        ui.card_title("Order of business", ft.Icons.LIST_ALT_OUTLINED, subtitle=subtitle),
        *header_actions,
        *[section_block(position, section) for position, section in enumerate(business["sections"], start=1)],
    ], spacing=14), padding=20)
