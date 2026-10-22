"""The look shared by every screen: the login page's blues, the admin sidebar's gradient and the round seal.

The admin shell keeps its own sidebar colours (admin_shell.shell_colors); these match them.
"""

import flet as ft

if not hasattr(ft, "Colors") and hasattr(ft, "colors"):
    ft.Colors = ft.colors

SEAL_IMAGE = "login_seal.png"
BUILDING_IMAGE = "login_municipal_building.png"

NAVY = "#073a78"
BLUE = "#1A56B5"
BLUE_DARK = "#0E3A86"
PRIMARY = "#0869d5"
ACCENT = "#ffda31"
CANVAS = "#F2F6FC"
INK = "#163f72"
MUTED = "#617493"
BORDER = "#d6e1ee"
# Text on the blue bands and footers.
ON_BLUE = "#ffffff"
ON_BLUE_MUTED = "#c9dcf5"

# Night mode, matching admin_shell.shell_colors(True).
NIGHT_CANVAS = "#0f171d"
NIGHT_SURFACE = "#16212b"
NIGHT_BLUE = "#13263d"
NIGHT_INK = "#e8f0fa"
NIGHT_MUTED = "#9fb4cc"
NIGHT_BORDER = "#26384a"


def seal(size):
    """The seal image has a white square background, so clip it to a circle around the round seal."""
    return ft.Container(
        content=ft.Image(src=SEAL_IMAGE, width=size, height=size, fit=ft.ImageFit.COVER, scale=1.1),
        width=size,
        height=size,
        border_radius=size / 2,
        bgcolor=ft.Colors.WHITE,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
    )


def blue_band_gradient():
    """The sidebar's top-to-bottom blue, for headers, banners and footers."""
    return ft.LinearGradient(begin=ft.Alignment(0, -1), end=ft.Alignment(0, 1), colors=[BLUE, BLUE_DARK])


def primary_button(label, on_click=None, icon=None, height=46):
    """The login page's Log In button: a blue gradient pill with white text."""
    row = [ft.Text(label, size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE)]
    if icon is not None:
        row.append(ft.Icon(icon, color=ft.Colors.WHITE, size=20))
    return ft.Container(
        content=ft.Row(row, alignment=ft.MainAxisAlignment.CENTER, spacing=10, tight=True),
        height=height,
        padding=ft.Padding(22, 0, 22, 0),
        border_radius=13,
        gradient=ft.LinearGradient(colors=["#086bdc", "#0561c9"]),
        shadow=ft.BoxShadow(blur_radius=14, offset=ft.Offset(0, 6), color=ft.Colors.with_opacity(0.18, "#0564cf")),
        on_click=on_click,
        ink=True,
    )


def accent_bar(width=64):
    """The short yellow rule under headings on the login page."""
    return ft.Container(width=width, height=4, bgcolor=ACCENT, border_radius=2)


def brand(subtitle="Municipality of Tolosa", on_blue=False, seal_size=46):
    """The seal beside the Sangguniang Bayan name, as in the admin sidebar header."""
    return ft.Row(
        [
            seal(seal_size),
            ft.Column(
                [
                    ft.Text("SANGGUNIANG BAYAN", size=15, weight=ft.FontWeight.BOLD, color=ON_BLUE if on_blue else NAVY),
                    ft.Text(subtitle.upper(), size=10, color=ON_BLUE_MUTED if on_blue else MUTED, style=ft.TextStyle(letter_spacing=1)),
                ],
                spacing=1,
                tight=True,
            ),
        ],
        spacing=12,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
