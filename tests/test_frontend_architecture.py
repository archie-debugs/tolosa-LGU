import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_archived_documents_delete_selected_button_and_handler_exist():
    admin_app = (ROOT / "frontend" / "admin" / "app.py").read_text(encoding="utf-8")
    documents_screen = (ROOT / "frontend" / "admin" / "documents.py").read_text(encoding="utf-8")
    assert 'ft.OutlinedButton("Delete permanently"' in documents_screen
    assert 'delete_selected=open_archived_delete_selected_dialog' in admin_app
    assert 'def open_archived_delete_selected_dialog():' in admin_app
    assert 'def run_delete_selected_archived_documents_action():' in admin_app


def test_archived_delete_selected_flow_uses_real_permanent_delete_requests():
    text = (ROOT / "frontend" / "admin" / "app.py").read_text(encoding="utf-8")
    assert 'backend_api(method, f"/documents/{doc_id}{path_suffix}")' in text
    assert 'run_archived_bulk_action("DELETE", "/permanent", "Permanently deleted")' in text
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


def test_document_details_dialog_lives_in_its_own_module():
    admin_app = (ROOT / "frontend" / "admin" / "app.py").read_text(encoding="utf-8")
    assert "from frontend.admin.document_details import open_document_details" in admin_app
    # What an office may do with a document comes from the backend's overview, not from client-side receipt checks.
    assert "office_receipt_status" not in admin_app
    assert "/receipts" not in admin_app
