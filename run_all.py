#!/usr/bin/env python3
r"""Run the backend and frontends together for development.

Usage:
    .venv\Scripts\python.exe run_all.py

Options:
        --no-frontend     Don't start the frontend

The script starts child processes and will terminate them on Ctrl+C.
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).parent
PY = sys.executable

# Load development environment settings before starting child processes
load_dotenv(override=True)

FRONTEND = str(REPO_ROOT / "frontend" / "app.py")

children = []


def start_process(name, script_path, env=None):
    cmd = [PY, script_path]
    print(f"Starting {name}: {' '.join(cmd)}")
    # Start without piping so output flows to the console
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    full_env["PYTHONPATH"] = str(REPO_ROOT)
    p = subprocess.Popen(cmd, cwd=str(REPO_ROOT), env=full_env)
    children.append((name, p))
    print(f"{name} started (pid {p.pid})")


def check_port_available(host: str, port: int):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


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
        backend_port = int(os.getenv("PORT", "8001"))
        backend_host = "0.0.0.0"
        if not check_port_available(backend_host, backend_port):
            print(f"Port {backend_port} is already in use. Backend cannot start.")
            return

        # Start backend first
        start_process("backend", str(REPO_ROOT / "run_backend.py"))
        time.sleep(0.6)

        if children and children[0][1].poll() is None:
            frontend_port = int(os.getenv("FRONTEND_PORT", "8550"))
            frontend_host = "127.0.0.1"
            if not check_port_available(frontend_host, frontend_port):
                print(f"Port {frontend_port} is already in use. Frontend cannot start.")
                print("Backend started, but the frontend was not launched.")
            elif "--no-frontend" not in args:
                frontend_env = os.environ.copy()
                frontend_env["FRONTEND_PORT"] = str(frontend_port)
                start_process("frontend", FRONTEND, env=frontend_env)
                print("All processes started. Press Ctrl+C to stop.")
            else:
                print("Backend started without frontend. Press Ctrl+C to stop.")
        else:
            print("Backend failed to start. Frontend will not be launched.")

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
