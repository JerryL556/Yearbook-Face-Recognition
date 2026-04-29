from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

import uvicorn

from capture_helper import main as capture_helper_main


APP_URL = "http://127.0.0.1:8000"


def _runtime_log_path() -> Path:
    base_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    log_dir = base_dir / "student_tagger_app" / "data"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "package_runtime.log"


def _log_runtime(message: str) -> None:
    try:
        log_path = _runtime_log_path()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


def _open_browser_after_delay() -> None:
    time.sleep(1.25)
    try:
        webbrowser.open(APP_URL)
    except Exception:
        pass


def _build_helper_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--capture-helper"]
    return [sys.executable, str(Path(__file__).resolve()), "--capture-helper"]


def run_server() -> None:
    _log_runtime("Server bootstrap starting.")
    try:
        from app.main import app
    except Exception as exc:
        _log_runtime(f"Import failure: {exc!r}")
        raise
    _log_runtime("FastAPI app imported.")

    helper_process: subprocess.Popen | None = None
    if os.environ.get("STUDENT_TAGGER_DISABLE_HELPER") != "1":
        _log_runtime("Launching capture helper process.")
        helper_process = subprocess.Popen(_build_helper_command())

    browser_thread = threading.Thread(target=_open_browser_after_delay, daemon=True)
    browser_thread.start()
    _log_runtime("Starting uvicorn.")
    try:
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=8000,
            reload=False,
            log_config=None if getattr(sys, "frozen", False) else uvicorn.config.LOGGING_CONFIG,
        )
        _log_runtime("Uvicorn exited normally.")
    except Exception as exc:
        _log_runtime(f"Uvicorn failure: {exc!r}")
        raise
    finally:
        if helper_process is not None and helper_process.poll() is None:
            _log_runtime("Terminating capture helper process.")
            helper_process.terminate()


if __name__ == "__main__":
    if "--capture-helper" in sys.argv[1:]:
        capture_helper_main()
    else:
        run_server()
