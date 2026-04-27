from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import uvicorn


if __name__ == "__main__":
    helper_process: subprocess.Popen | None = None
    helper_script = Path(__file__).resolve().with_name("capture_helper.py")
    if os.environ.get("STUDENT_TAGGER_DISABLE_HELPER") != "1" and helper_script.exists():
        helper_process = subprocess.Popen([sys.executable, str(helper_script)])
    try:
        uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
    finally:
        if helper_process is not None and helper_process.poll() is None:
            helper_process.terminate()
