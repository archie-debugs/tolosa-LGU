"""Dedicated Employee frontend entrypoint.

The document workspace remains shared with the administrator implementation so
employees see the same records and permission-gated actions. This module owns
employee startup and gives future employee-only screens a clear home.
"""
import os

import flet as ft


def main(page: ft.Page, session=None):
    from frontend.admin.app import main as shared_workspace_main

    return shared_workspace_main(page, session=session)


if __name__ == "__main__":
    ft.app(
        target=main,
        view=ft.AppView.WEB_BROWSER,
        port=int(os.getenv("EMPLOYEE_FRONTEND_PORT", "8552")),
    )
