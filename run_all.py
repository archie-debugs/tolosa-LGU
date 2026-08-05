#!/usr/bin/env python3
"""Run the backend and frontends together for development.

Usage:
  .venv\Scripts\python.exe run_all.py

Options:
    --no-admin        Don't start the admin frontend

The script starts child processes and will terminate them on Ctrl+C.
"""
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent
PY = sys.executable

FRONTENDS = {
    "admin": str(REPO_ROOT / "frontend" / "frontend_admin" / "app.py"),
}

children = []


def start_process(name, script_path):
    cmd = [PY, script_path]
    print(f"Starting {name}: {' '.join(cmd)}")
    # Start without piping so output flows to the console
    p = subprocess.Popen(cmd, cwd=str(REPO_ROOT))
    children.append((name, p))
    print(f"{name} started (pid {p.pid})")


def stop_all():
    print("Stopping child processes...")
    for name, p in children:
        if p.poll() is None:
            print(f"Terminating {name} (pid {p.pid})")
            try:
                p.terminate()
            except Exception:
                pass
    # Give them a moment to exit gracefully
    time.sleep(1.5)
    for name, p in children:
        if p.poll() is None:
            print(f"Killing {name} (pid {p.pid})")
            try:
                p.kill()
            except Exception:
                pass
    print("All children stopped.")


def main():
    args = set(sys.argv[1:])
    try:
        # Start backend first
        start_process("backend", str(REPO_ROOT / "run_backend.py"))
        time.sleep(0.6)

        if "--no-admin" not in args:
            start_process("admin", FRONTENDS["admin"])
        print("All processes started. Press Ctrl+C to stop.")

        # Wait until children exit or user interrupts
        while True:
            still_running = [p for _, p in children if p.poll() is None]
            if not still_running:
                print("All child processes have exited.")
                break
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("Keyboard interrupt received.")
    finally:
        stop_all()


if __name__ == "__main__":
    main()
