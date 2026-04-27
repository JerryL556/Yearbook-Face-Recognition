from __future__ import annotations

import json
import tempfile
import threading
import tkinter as tk
import uuid
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import get_settings
from .db import (
    connect,
    fetch_detections,
    fetch_latest_photo_id_by_source,
    fetch_photo,
    fetch_recent_photos,
    fetch_recent_photos_by_source,
    fetch_summary,
    fetch_tagged_folders,
    initialize,
    replace_photo_results,
)
from .recognition import RecognitionDependencyError, StudentRecognizer, ensure_directories, normalize_subfolder

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
index_building = False
index_lock = threading.Lock()
index_progress = {
    "phase": "idle",
    "processed": 0,
    "total": 0,
    "current_file": None,
    "known_count": 0,
    "warning_count": 0,
    "started_at": None,
    "updated_at": None,
}
batch_status_lock = threading.Lock()
batch_statuses: dict[str, dict] = {}


def update_index_progress(**values) -> None:
    index_progress.update(values)
    index_progress["updated_at"] = datetime.now(timezone.utc).isoformat()


def build_index_status() -> dict:
    return {
        "building": index_building,
        "dependency_error": recognizer_error,
        "reference_count": recognizer.known_count() if recognizer else 0,
        "phase": index_progress["phase"],
        "processed": index_progress["processed"],
        "total": index_progress["total"],
        "current_file": index_progress["current_file"],
        "known_count": index_progress["known_count"],
        "warning_count": index_progress["warning_count"],
        "started_at": index_progress["started_at"],
        "updated_at": index_progress["updated_at"],
    }


def bootstrap_recognizer(force_rebuild: bool = False) -> None:
    global recognizer
    global recognizer_error
    global index_warnings
    global index_building

    with index_lock:
        if index_building:
            return
        index_building = True
        update_index_progress(
            phase="starting",
            processed=0,
            total=0,
            current_file=None,
            known_count=0,
            warning_count=0,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

    try:
        try:
            next_recognizer = StudentRecognizer(settings)
            warnings = next_recognizer.load_or_build_index(
                force_rebuild=force_rebuild,
                progress_callback=lambda progress: update_index_progress(**progress),
            )
            recognizer = next_recognizer
            index_warnings = warnings
            recognizer_error = None
            update_index_progress(
                phase="ready",
                processed=index_progress["total"],
                current_file=None,
                known_count=next_recognizer.known_count(),
                warning_count=len(warnings),
            )
        except RecognitionDependencyError as exc:
            recognizer = None
            recognizer_error = str(exc)
            index_warnings = []
            update_index_progress(
                phase="error",
                current_file=None,
                known_count=0,
                warning_count=0,
            )
    finally:
        with index_lock:
            index_building = False


def bootstrap_recognizer_async(force_rebuild: bool = False) -> None:
    thread = threading.Thread(
        target=bootstrap_recognizer,
        kwargs={"force_rebuild": force_rebuild},
        daemon=True,
    )
    thread.start()


def build_home_context(request: Request) -> dict:
    summary = fetch_summary(db_connection)
    recent_photos = fetch_recent_photos(db_connection)
    desktop_results = fetch_recent_photos_by_source(db_connection, "desktop_screenshot", limit=2)
    tagged_folders = fetch_tagged_folders(db_connection)
    return {
        "request": request,
        "summary": summary,
        "recent_photos": recent_photos,
        "desktop_results": desktop_results,
        "tagged_folders": tagged_folders,
        "latest_desktop_photo_id": fetch_latest_photo_id_by_source(db_connection, "desktop_screenshot"),
        "reference_count": recognizer.known_count() if recognizer else 0,
        "reference_dir": settings.reference_dir,
        "tagged_root_name": settings.processed_dir.name,
        "tagged_root_path": settings.processed_dir,
        "dependency_error": recognizer_error,
        "index_building": index_building,
        "index_status": build_index_status(),
        "index_warnings": index_warnings[:10],
        "warning_count": len(index_warnings),
    }


@app.on_event("startup")
def start_background_index() -> None:
    bootstrap_recognizer_async()


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(request, "index.html", build_home_context(request))


@app.get("/index-status")
def index_status() -> dict:
    return build_index_status()


def _update_batch_status(batch_id: str, **values) -> None:
    with batch_status_lock:
        if batch_id not in batch_statuses:
            return
        batch_statuses[batch_id].update(values)
        batch_statuses[batch_id]["updated_at"] = datetime.now(timezone.utc).isoformat()


def _process_batch(batch_id: str, items: list[dict]) -> None:
    _update_batch_status(batch_id, status="processing", started_at=datetime.now(timezone.utc).isoformat())
    completed = 0
    discarded = 0
    failures: list[str] = []
    for item in items:
        if item["discard"]:
            discarded += 1
            completed += 1
            _update_batch_status(batch_id, processed=completed, discarded=discarded)
            item["temp_path"].unlink(missing_ok=True)
            continue
        _update_batch_status(
            batch_id,
            current_file=item["original_filename"],
            current_folder=item["subfolder"] or "Inbox",
            current_step="tagging",
        )
        try:
            if recognizer is None:
                raise RuntimeError("Recognizer unavailable.")
            result = recognizer.process_upload(
                item["temp_path"],
                item["original_filename"],
                subfolder=item["subfolder"],
                batch_id=batch_id,
                output_root=settings.processed_dir,
                source_kind="upload",
            )
            replace_photo_results(db_connection, result["photo"], result["detections"])
        except Exception as exc:
            failures.append(f"{item['original_filename']}: {exc}")
        finally:
            completed += 1
            _update_batch_status(batch_id, processed=completed, discarded=discarded)
            item["temp_path"].unlink(missing_ok=True)
            resized_temp = item["temp_path"].with_name(f"{item['temp_path'].stem}_resized{item['temp_path'].suffix}")
            resized_temp.unlink(missing_ok=True)
    status = "completed" if not failures else "completed_with_errors"
    _update_batch_status(
        batch_id,
        status=status,
        current_file=None,
        current_folder=None,
        current_step=None,
        completed_at=datetime.now(timezone.utc).isoformat(),
        failures=failures,
    )


def _build_batch_payload(batch_id: str) -> dict:
    with batch_status_lock:
        payload = dict(batch_statuses[batch_id])
    payload["recent_photos"] = [
        {
            "id": photo["id"],
            "original_filename": photo["original_filename"],
            "annotated_filename": photo["annotated_filename"],
            "subfolder": photo["subfolder"],
        }
        for photo in fetch_recent_photos(db_connection, limit=12)
        if photo["batch_id"] == batch_id
    ]
    return payload


def _serialize_photo_row(photo) -> dict:
    return {
        "id": int(photo["id"]),
        "original_filename": photo["original_filename"],
        "annotated_filename": photo["annotated_filename"],
        "subfolder": photo["subfolder"],
        "matched_count": int(photo["matched_count"]),
        "face_count": int(photo["face_count"]),
        "uploaded_at": photo["uploaded_at"],
        "source_kind": photo["source_kind"],
    }


@app.post("/rebuild-index")
def rebuild_index():
    bootstrap_recognizer_async(force_rebuild=True)
    return RedirectResponse(url="/", status_code=303)


@app.post("/upload")
async def upload_photos(
    files: list[UploadFile] = File(...),
    upload_plan: str = Form(...),
):
    if recognizer is None and not recognizer_error and not index_building:
        bootstrap_recognizer_async()
    if index_building:
        raise HTTPException(status_code=503, detail="Reference index is still building. Try again in a moment.")
    if recognizer_error or recognizer is None:
        raise HTTPException(status_code=503, detail=recognizer_error or "Recognizer unavailable.")
    try:
        plan = json.loads(upload_plan)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid upload plan.") from exc
    if not isinstance(plan, list) or len(plan) != len(files):
        raise HTTPException(status_code=400, detail="Upload plan does not match selected files.")

    batch_id = uuid.uuid4().hex[:12]
    batch_items: list[dict] = []
    total_items = len(plan)
    for upload, item in zip(files, plan):
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
        await upload.close()
        batch_items.append(
            {
                "temp_path": temp_path,
                "original_filename": upload.filename,
                "subfolder": normalize_subfolder(str(item.get("subfolder", ""))),
                "discard": bool(item.get("discard", False)),
            }
        )

    with batch_status_lock:
        batch_statuses[batch_id] = {
            "batch_id": batch_id,
            "status": "queued",
            "processed": 0,
            "total": total_items,
            "discarded": 0,
            "current_file": None,
            "current_folder": None,
            "current_step": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "completed_at": None,
            "failures": [],
        }

    worker = threading.Thread(target=_process_batch, args=(batch_id, batch_items), daemon=True)
    worker.start()
    return JSONResponse({"batch_id": batch_id})


@app.post("/desktop-capture")
async def desktop_capture(
    file: UploadFile = File(...),
):
    if recognizer is None and not recognizer_error and not index_building:
        bootstrap_recognizer_async()
    if index_building:
        raise HTTPException(status_code=503, detail="Reference index is still building. Try again in a moment.")
    if recognizer_error or recognizer is None:
        raise HTTPException(status_code=503, detail=recognizer_error or "Recognizer unavailable.")

    suffix = Path(file.filename or "desktop_capture.png").suffix or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_path = Path(temp_file.name)
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            temp_file.write(chunk)
    await file.close()

    original_filename = datetime.now().strftime("desktop_capture_%Y%m%d_%H%M%S.png")
    try:
        result = recognizer.process_upload(
            temp_path,
            original_filename,
            output_root=settings.processed_dir,
            source_kind="desktop_screenshot",
        )
        photo_id = replace_photo_results(db_connection, result["photo"], result["detections"])
    finally:
        temp_path.unlink(missing_ok=True)
        resized_temp = temp_path.with_name(f"{temp_path.stem}_resized{temp_path.suffix}")
        resized_temp.unlink(missing_ok=True)

    return JSONResponse(
        {
            "photo_id": photo_id,
            "detail_url": f"/photos/{photo_id}",
            "photo": {
                **result["photo"],
                "id": photo_id,
            },
            "detections": result["detections"],
        }
    )


@app.get("/pick-output-folder")
def pick_output_folder() -> dict:
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(
            initialdir=str(settings.processed_dir),
            title="Choose a folder inside Tagged Photos",
            mustexist=False,
        )
    finally:
        root.destroy()
    if not selected:
        return {"selected": False}
    selected_path = Path(selected).resolve()
    tagged_root = settings.processed_dir.resolve()
    try:
        relative = selected_path.relative_to(tagged_root)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Please choose a folder inside {tagged_root}.",
        ) from exc
    return {
        "selected": True,
        "folder": relative.as_posix() if str(relative) != "." else "",
        "display_name": relative.as_posix() if str(relative) != "." else "Inbox",
    }


@app.get("/batches/{batch_id}")
def batch_status(batch_id: str) -> dict:
    with batch_status_lock:
        if batch_id not in batch_statuses:
            raise HTTPException(status_code=404, detail="Batch not found.")
    return _build_batch_payload(batch_id)


@app.get("/desktop-results")
def desktop_results() -> dict:
    photos = fetch_recent_photos_by_source(db_connection, "desktop_screenshot", limit=2)
    return {
        "latest_photo_id": fetch_latest_photo_id_by_source(db_connection, "desktop_screenshot"),
        "results": [_serialize_photo_row(photo) for photo in photos],
    }


@app.get("/photos/{photo_id}")
def photo_detail(request: Request, photo_id: int):
    photo = fetch_photo(db_connection, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found.")
    detections = fetch_detections(db_connection, photo_id)
    return templates.TemplateResponse(
        request,
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
