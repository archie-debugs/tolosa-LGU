import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_archived_documents_delete_selected_button_and_handler_exist():
    admin_app = ROOT / "frontend" / "admin" / "app.py"
    text = admin_app.read_text(encoding="utf-8")
    assert 'archived_documents_delete_selected_button = ft.Button(' in text
    assert 'def open_archived_delete_selected_dialog():' in text
    assert 'def run_delete_selected_archived_documents_action():' in text


def test_archived_delete_selected_flow_uses_real_permanent_delete_requests():
    admin_app = ROOT / "frontend" / "admin" / "app.py"
    text = admin_app.read_text(encoding="utf-8")
    assert 'requests.delete(' in text
    assert 'f"{BACKEND_URL}/documents/{doc_id}/permanent"' in text
    assert 'Delete Selected action prepared' not in text


def test_employee_frontend_has_dedicated_entrypoint():
    employee_app = ROOT / "frontend" / "employee" / "app.py"
    assert employee_app.exists()
    tree = ast.parse(employee_app.read_text(encoding="utf-8"))
    functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert "main" in functions


def test_employee_launcher_targets_employee_package():
    launcher = (ROOT / "scripts" / "run" / "run_flet_employee.py").read_text(encoding="utf-8")
    assert "frontend.employee" in launcher
    assert "frontend.frontend_admin" not in launcher


def test_employee_login_routes_to_employee_entrypoint():
    admin_app = (ROOT / "frontend" / "admin" / "app.py").read_text(encoding="utf-8")
    assert "from frontend.employee.app import main as employee_main" in admin_app
    assert "employee_main(page, session=payload)" in admin_app
