import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_employee_frontend_has_dedicated_entrypoint():
    employee_app = ROOT / "frontend" / "employee" / "app.py"
    assert employee_app.exists()
    tree = ast.parse(employee_app.read_text(encoding="utf-8"))
    functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert "main" in functions


def test_employee_launcher_targets_employee_package():
    launcher = (ROOT / "run_flet_employee.py").read_text(encoding="utf-8")
    assert "frontend.employee" in launcher
    assert "frontend.frontend_admin" not in launcher


def test_employee_login_routes_to_employee_entrypoint():
    admin_app = (ROOT / "frontend" / "admin" / "app.py").read_text(encoding="utf-8")
    assert "from frontend.employee.app import main as employee_main" in admin_app
    assert "employee_main(page, session=payload)" in admin_app
