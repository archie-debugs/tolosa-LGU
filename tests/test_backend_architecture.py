from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_backend_services_live_under_backends_directory():
    backends = ROOT / "Backends"
    assert (backends / "backend" / "main.py").exists()
    assert (backends / "backend_employee" / "main.py").exists()
    assert (backends / "SBmem_backend" / "main.py").exists()
    assert not (ROOT / "backend").exists()
    assert not (ROOT / "backend_employee").exists()
    assert not (ROOT / "SBmem_backend").exists()


def test_backend_launchers_use_backends_paths():
    assert "from Backends.backend.main import app" in (ROOT / "scripts" / "run" / "run_backend.py").read_text(encoding="utf-8")
    assert "from Backends.backend_employee.main import app" in (ROOT / "scripts" / "run" / "run_backend_employee.py").read_text(encoding="utf-8")
    assert "Backends" in (ROOT / "scripts" / "run" / "run_all.py").read_text(encoding="utf-8")
