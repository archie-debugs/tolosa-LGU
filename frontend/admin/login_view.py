"""Login screen layout (from the Figma Make design "Create new project").

show_login() in admin/app.py owns the fields and the login logic; this module only lays them out.
"""

import flet as ft

if not hasattr(ft, "Colors") and hasattr(ft, "colors"):
    ft.Colors = ft.colors
if not hasattr(ft, "Icons") and hasattr(ft, "icons"):
    ft.Icons = ft.icons

SEAL_IMAGE = "login_seal.png"
BUILDING_IMAGE = "login_municipal_building.png"

PAGE_BG = "#edf5fc"
NAVY = "#073a78"
LABEL = "#365b88"
MUTED = "#617493"
FIELD_BORDER = "#c8d4e2"
FIELD_FOCUS = "#0869d5"
FIELD_ICON = "#0a498d"
ACCENT = "#ffda31"


def login_field(hint, icon, **text_field_kwargs):
    """A borderless TextField; put it in the page with field_box() so it gets the design's box and icon."""
    return ft.TextField(
        hint_text=hint,
        border=ft.InputBorder.NONE,
        text_size=14,
        color="#163f72",
        hint_style=ft.TextStyle(color="#7890ad"),
        expand=True,
        data=icon,
        **text_field_kwargs,
    )


def field_box(text_field, height):
    box = ft.Container(
        content=ft.Row(
            [ft.Icon(text_field.data, color=FIELD_ICON, size=25), text_field],
            spacing=15,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        height=height,
        padding=ft.padding.only(left=18, right=6),
        border=ft.border.all(1, FIELD_BORDER),
        border_radius=13,
        bgcolor=ft.Colors.WHITE,
        visible=text_field.visible,
    )

    def set_focus(focused):
        box.border = ft.border.all(1, FIELD_FOCUS if focused else FIELD_BORDER)
        box.shadow = ft.BoxShadow(spread_radius=3, color=ft.Colors.with_opacity(0.12, FIELD_FOCUS)) if focused else None
        box.update()

    text_field.on_focus = lambda _: set_focus(True)
    text_field.on_blur = lambda _: set_focus(False)
    return box


def _label(text):
    return ft.Container(
        content=ft.Text(text, size=15, weight=ft.FontWeight.W_500, color=LABEL),
        padding=ft.padding.only(bottom=9),
    )


def _seal(size):
    """The seal image has a white square background, so clip it to a circle around the round seal."""
    return ft.Container(
        content=ft.Image(src=SEAL_IMAGE, width=size, height=size, fit=ft.ImageFit.COVER, scale=1.1),
        width=size,
        height=size,
        border_radius=size / 2,
        bgcolor=ft.Colors.WHITE,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
    )


def _brand_panel():
    copy_box = ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    ft.Text("WELCOME TO", size=20, weight=ft.FontWeight.W_500, color=ft.Colors.WHITE,
                            style=ft.TextStyle(letter_spacing=5), text_align=ft.TextAlign.CENTER),
                    padding=ft.padding.only(bottom=8),
                ),
                ft.Text("SANGGUNIANG BAYAN OF\nTOLOSA, LEYTE", size=25, weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE, style=ft.TextStyle(letter_spacing=1.75, height=1.08),
                        text_align=ft.TextAlign.CENTER),
                ft.Container(width=78, height=5, bgcolor=ACCENT, margin=ft.margin.only(top=24, bottom=20)),
                ft.Container(
                    ft.Text("Document Tracking Management System", size=18, weight=ft.FontWeight.W_600,
                            color=ft.Colors.WHITE, text_align=ft.TextAlign.CENTER),
                    padding=ft.padding.only(bottom=12),
                ),
                ft.Text(
                    "Efficiently manage, track, and monitor official documents for a more transparent "
                    "and accountable local government.",
                    size=14, color=ft.Colors.WHITE, style=ft.TextStyle(height=1.65), text_align=ft.TextAlign.CENTER,
                ),
            ],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        width=430,
        padding=ft.padding.symmetric(vertical=18, horizontal=30),
        bgcolor=ft.Colors.with_opacity(0.86, "#05396f"),
    )

    return ft.Stack(
        [
            ft.Image(src=BUILDING_IMAGE, fit=ft.ImageFit.COVER, expand=True),
            ft.Container(
                expand=True,
                gradient=ft.LinearGradient(
                    begin=ft.alignment.top_center,
                    end=ft.alignment.bottom_center,
                    colors=[ft.Colors.with_opacity(0.7, "#044184"), ft.Colors.with_opacity(0.78, "#03346f")],
                ),
            ),
            ft.Container(
                content=ft.Column(
                    [_seal(180), ft.Container(height=60), copy_box],
                    spacing=0,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                alignment=ft.alignment.top_center,
                padding=ft.padding.only(top=40),
                expand=True,
            ),
        ],
        expand=True,
    )


def _ribbon_background(content, compact):
    if compact:
        ribbons = ft.LinearGradient(
            begin=ft.alignment.top_left,
            end=ft.alignment.bottom_right,
            colors=[PAGE_BG, PAGE_BG, "#82bced", "#82bced", "#0867c9", "#0867c9"],
            stops=[0, 0.74, 0.74, 0.83, 0.83, 1],
        )
        return ft.Container(content=content, gradient=ribbons, padding=ft.padding.symmetric(vertical=24, horizontal=16))

    ribbons = ft.LinearGradient(
        begin=ft.alignment.top_left,
        end=ft.alignment.bottom_right,
        colors=["#edf4fb", "#edf4fb", "#a8d3f7", "#a8d3f7", "#1c77d1", "#1c77d1", "#0757aa", "#0757aa"],
        stops=[0, 0.79, 0.79, 0.86, 0.86, 0.93, 0.93, 1],
    )
    white_band = ft.LinearGradient(
        begin=ft.alignment.top_left,
        end=ft.alignment.bottom_right,
        colors=[ft.Colors.TRANSPARENT, ft.Colors.TRANSPARENT,
                ft.Colors.with_opacity(0.8, ft.Colors.WHITE), ft.Colors.with_opacity(0.8, ft.Colors.WHITE),
                ft.Colors.TRANSPARENT, ft.Colors.TRANSPARENT],
        stops=[0, 0.64, 0.64, 0.76, 0.76, 1],
    )
    return ft.Container(
        content=ft.Container(content=content, gradient=white_band, alignment=ft.alignment.center, padding=28, expand=True),
        gradient=ribbons,
        expand=True,
    )


def field_height(page):
    return 57 if (page.width or 1024) <= 720 else 62


def build_login_view(page, *, username_field, password_field, code_box, error_text, on_login, on_back):
    """code_box is field_box(code_field, field_height(page)); the caller shows it when the second step is needed."""
    width = page.width or 1024
    compact = width <= 720
    brand_share, form_share = (544, 456) if width > 1000 else (44, 56)
    height = field_height(page)

    login_button = ft.Container(
        content=ft.Row(
            [
                ft.Text("Log In", size=16, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                ft.Icon(ft.Icons.ARROW_FORWARD, color=ft.Colors.WHITE, size=24),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=28,
        ),
        height=height,
        border_radius=13,
        gradient=ft.LinearGradient(colors=["#086bdc", "#0561c9"]),
        shadow=ft.BoxShadow(blur_radius=18, offset=ft.Offset(0, 8), color=ft.Colors.with_opacity(0.18, "#0564cf")),
        on_click=on_login,
        ink=True,
    )

    divider = lambda: ft.Container(width=80 if compact else 100, height=1, bgcolor="#b5c1d0")
    go_back = ft.Row(
        [
            divider(),
            ft.TextButton(
                content=ft.Text("Go Back", size=14, weight=ft.FontWeight.W_600, color=FIELD_FOCUS),
                on_click=on_back,
            ),
            divider(),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=18,
    )

    seal_size = 105 if compact else 126
    card = ft.Container(
        content=ft.Column(
            [
                ft.Row([_seal(seal_size)], alignment=ft.MainAxisAlignment.CENTER),
                ft.Container(height=8),
                ft.Text("Welcome Back", size=29 if compact else 34, weight=ft.FontWeight.BOLD, color=NAVY,
                        text_align=ft.TextAlign.CENTER),
                ft.Container(
                    ft.Text("Sign in to continue to the document tracking system.", size=13 if compact else 15,
                            color=MUTED, text_align=ft.TextAlign.CENTER),
                    padding=ft.padding.only(top=12, bottom=26 if compact else 31),
                ),
                _label("Username"),
                field_box(username_field, height),
                ft.Container(height=24),
                _label("Password"),
                field_box(password_field, height),
                ft.Container(height=12),
                code_box,
                error_text,
                ft.Container(height=12),
                login_button,
                ft.Container(height=28),
                go_back,
            ],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
        width=None if compact else min(612, width * form_share / (brand_share + form_share) - 56),
        padding=ft.padding.symmetric(vertical=30, horizontal=22) if compact else ft.padding.only(left=44, top=40, right=44, bottom=42),
        border_radius=20 if compact else 24,
        bgcolor=ft.Colors.with_opacity(0.96, ft.Colors.WHITE),
        shadow=ft.BoxShadow(blur_radius=40, offset=ft.Offset(0, 16), color=ft.Colors.with_opacity(0.12, "#0c4279")),
    )

    if compact:
        return _ribbon_background(card, compact=True)

    return ft.Row(
        [
            ft.Container(content=_brand_panel(), expand=brand_share),
            ft.Container(content=_ribbon_background(card, compact=False), expand=form_share),
        ],
        spacing=0,
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
    )
