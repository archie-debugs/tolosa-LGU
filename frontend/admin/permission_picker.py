"""Choosing an employee's permissions: one list of switches, each with a plain description.

Used by Create User Account and Edit User. Both keep the chosen permission keys in a set;
the list turns switches on and off in that set and calls `refresh` to redraw.
"""

import flet as ft

DESCRIPTIONS = {
    "view_dashboard": "See the home dashboard with counts and recent activity.",
    "register_documents": "Add new documents and upload their files.",
    "edit_documents": "Change a document's details after it is registered.",
    "delete_documents": "Permanently delete archived documents.",
    "archive_documents": "Move documents to Archived Documents.",
    "restore_documents": "Bring archived documents back.",
    "view_documents": "Open the Documents list.",
    "search_documents": "Search documents by number, title or text.",
    "filter_documents": "Filter the list by type, year, status and office.",
    "view_document_details": "Open a document's full details and history.",
    "import_documents": "Register many documents at once from a spreadsheet.",
    "export_documents": "Download the documents list as a file.",
    "download_documents": "Download a document's attached file.",
    "print_documents": "Print documents and the printable list.",
    "update_document_status": "Change a document's status.",
    "change_measure_stage": "Move an ordinance or resolution to its next stage.",
    "generate_qr_codes": "Make QR codes for documents.",
    "print_qr_codes": "Print QR labels.",
    "view_qr_tracking": "See where a document is by scanning or searching.",
    "set_documents_for_sb_members": "Choose which documents SB Members see each day.",
    "view_users": "See the list of user accounts.",
    "create_users": "Make new user accounts.",
    "edit_users": "Change other people's account details.",
    "reset_passwords": "Set a new password for someone.",
    "activate_users": "Turn accounts back on.",
    "deactivate_users": "Turn accounts off.",
    "delete_users": "Delete accounts.",
    "assign_roles": "Change someone's role.",
    "manage_permissions": "Change what other people can do (only permissions they have themselves).",
    "manage_members_and_committees": "Edit council members, terms and committees.",
    "manage_sessions": "Plan sessions, attendance and the order of business.",
    "view_audit_logs": "See who did what in the system.",
    "export_audit_logs": "Download the audit log.",
    "view_analytics": "See reports and charts.",
    "export_analytics": "Download reports.",
    "view_office_documents": "See documents held by their office.",
    "search_office_documents": "Search their office's documents.",
    "view_office_document_details": "Open their office's documents.",
    "scan_qr": "Scan document QR codes with a phone.",
    "pass_office_documents": "Send a document to another office.",
    "confirm_document_receipt": "Confirm a document arrived at their office.",
    "view_office_history": "See what their office received and passed on.",
}


def permission_key(label):
    return str(label).strip().lower().replace(" ", "_")


def group_keys(groups):
    """{group: [labels]} as {group: [(key, label)]}."""
    return {name: [(permission_key(label), label) for label in labels] for name, labels in groups.items()}


def build_permission_list(widgets, selected, groups, refresh, state, locked=frozenset()):
    """Switches for every permission in `groups` ({group: [labels]}), grouped, with a search box.

    `state` is a dict the dialog keeps between redraws (it holds the search box). Permissions in
    `locked` stay on and their switches are greyed out."""
    groups = group_keys(groups)
    if "search" not in state:
        state["search"] = ft.TextField(
            hint_text="Search permissions, e.g. print, QR, users", prefix_icon=ft.Icons.SEARCH, dense=True,
            on_change=lambda _: refresh(),
        )
    term = (state["search"].value or "").strip().lower()

    def switch(keys, on):
        (selected.update if on else selected.difference_update)(keys)
        selected.update(locked)
        refresh()

    rows = []
    for group, items in groups.items():
        shown = [
            (key, label) for key, label in items
            if not term or term in label.lower() or term in DESCRIPTIONS.get(key, "").lower() or term in group.lower()
        ]
        if not shown:
            continue
        keys = [key for key, _ in items]
        rows.append(ft.Row([
            ft.Text(group.upper(), size=11, weight=ft.FontWeight.BOLD, color=widgets.accent()),
            ft.Text(f"{sum(key in selected for key in keys)}/{len(keys)}", size=11, color=widgets.muted_color()),
            ft.TextButton("All", on_click=lambda _, keys=keys: switch(keys, True)),
            ft.TextButton("None", on_click=lambda _, keys=keys: switch(keys, False)),
        ], spacing=6))
        for key, label in shown:
            rows.append(ft.Row([
                ft.Switch(value=key in selected or key in locked, disabled=key in locked,
                          tooltip="Always on for employees" if key in locked else None,
                          on_change=lambda e, key=key: switch([key], e.control.value)),
                ft.Column([
                    ft.Text(label, size=13, weight=ft.FontWeight.W_600, color=widgets.body_color()),
                    ft.Text(DESCRIPTIONS.get(key, ""), size=11, color=widgets.muted_color()),
                ], spacing=0, expand=True),
            ], spacing=8))
        rows.append(ft.Divider(height=1, color=widgets.line_color()))

    total = sum(len(items) for items in groups.values())
    chosen = sum(key in selected for items in groups.values() for key, _ in items)
    return ft.Column([
        state["search"],
        widgets.hint(f"{chosen} of {total} turned on."),
        *(rows or [widgets.hint("No permission matches that search.")]),
    ], spacing=4)
