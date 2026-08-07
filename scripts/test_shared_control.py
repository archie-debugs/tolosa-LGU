import sys
from pathlib import Path
proj = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(proj))
import flet as ft

text = ft.Text('Pending Registrations')
row1 = ft.Row([text])
try:
    row2 = ft.Row([text])
    print('second attach ok', row2)
except Exception as exc:
    print('exception on second attach', exc)
