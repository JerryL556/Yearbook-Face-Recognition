from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import get_settings
from .db import (
    connect,
    fetch_detections,
    fetch_photo,
    fetch_recent_photos,
    fetch_summary,
    initialize,
    replace_photo_results,
)
from .recognition import RecognitionDependencyError, StudentRecognizer, ensure_directories

settings = get_settings()
ensure_directories(settings)
templates = Jinja2Templates(directory=str(settings.templates_dir))

app = FastAPI(title="Student Photo Tagger")
app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")
app.mount("/uploads", StaticFiles(directory=str(settings.uploads_dir)), name="uploads")
app.mount("/processed", StaticFiles(directory=str(settings.processed_dir)), name="processed")

db_connection = connect(settings.database_path)
initialize(db_connection)

recognizer_error: str | None = None
recognizer: StudentRecognizer | None = None
index_warnings: list[str] = []


def bootstrap_recognizer(force_rebuild: bool = False) -> None:
    global recognizer
    global recognizer_error
    global index_warnings

    try:
        recognizer = StudentRecognizer(settings)
        index_warnings = recognizer.load_or_build_index(force_rebuild=force_rebuild)
        recognizer_error = None
    except RecognitionDependencyError as exc:
        recognizer = None
        recognizer_error = str(exc)
        index_warnings = []


bootstrap_recognizer()


def build_home_context(request: Request) -> dict:
    summary = fetch_summary(db_connection)
    recent_photos = fetch_recent_photos(db_connection)
    return {
        "request": request,
        "summary": summary,
        "recent_photos": recent_photos,
        "reference_count": recognizer.known_count() if recognizer else 0,
        "reference_dir": settings.reference_dir,
        "dependency_error": recognizer_error,
        "index_warnings": index_warnings[:10],
        "warning_count": len(index_warnings),
    }


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", build_home_context(request))


@app.post("/rebuild-index")
def rebuild_index():
    bootstrap_recognizer(force_rebuild=True)
    return RedirectResponse(url="/", status_code=303)


@app.post("/upload")
async def upload_photos(files: list[UploadFile] = File(...)):
    if recognizer_error or recognizer is None:
        raise HTTPException(status_code=503, detail=recognizer_error or "Recognizer unavailable.")
    for upload in files:
        if not upload.filename:
            continue
        suffix = Path(upload.filename).suffix or ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = Path(temp_file.name)
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                temp_file.write(chunk)
        try:
            result = recognizer.process_upload(temp_path, upload.filename)
            replace_photo_results(db_connection, result["photo"], result["detections"])
        finally:
            await upload.close()
            temp_path.unlink(missing_ok=True)
            resized_temp = temp_path.with_name(f"{temp_path.stem}_resized{temp_path.suffix}")
            resized_temp.unlink(missing_ok=True)
    return RedirectResponse(url="/", status_code=303)


@app.get("/photos/{photo_id}")
def photo_detail(request: Request, photo_id: int):
    photo = fetch_photo(db_connection, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found.")
    detections = fetch_detections(db_connection, photo_id)
    return templates.TemplateResponse(
        "photo_detail.html",
        {
            "request": request,
            "photo": photo,
            "detections": detections,
        },
    )


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok" if recognizer_error is None else "degraded",
        "known_students": recognizer.known_count() if recognizer else 0,
        "dependency_error": recognizer_error,
    }
