from __future__ import annotations

import json
import re
import shutil
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .config import Settings


class RecognitionDependencyError(RuntimeError):
    """Raised when face recognition dependencies are not available."""


def _load_face_recognition(settings: Settings):
    try:
        import face_recognition  # type: ignore

        return face_recognition
    except ImportError:
        local_repo = settings.local_face_repo
        if local_repo.exists():
            local_repo_str = str(local_repo)
            if local_repo_str not in sys.path:
                sys.path.insert(0, local_repo_str)
        try:
            import face_recognition  # type: ignore

            return face_recognition
        except Exception as exc:  # pragma: no cover - dependency driven
            raise RecognitionDependencyError(
                "Unable to import face_recognition. Install dlib, face_recognition_models, "
                "and the Python dependencies before running the app."
            ) from exc


def ensure_directories(settings: Settings) -> None:
    for path in (
        settings.uploads_dir,
        settings.processed_dir,
        settings.cache_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)


def parse_student_name(file_path: Path) -> str:
    stem = file_path.stem
    parts = stem.split("_")
    if parts and parts[0].isdigit():
        parts = parts[1:]
    cleaned = " ".join(parts).replace(",", "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or stem


@dataclass
class DetectionResult:
    name: str
    distance: float | None
    top: int
    right: int
    bottom: int
    left: int


class StudentRecognizer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.face_recognition = _load_face_recognition(settings)
        self.known_names: list[str] = []
        self.known_files: list[str] = []
        self.known_encodings = np.empty((0, 128))
        self.cache_warnings: list[str] = []

    def load_or_build_index(self, force_rebuild: bool = False) -> list[str]:
        if not self.settings.reference_dir.exists():
            raise RecognitionDependencyError(
                f"Reference folder not found: {self.settings.reference_dir}"
            )
        if not force_rebuild and self.settings.encoding_cache_path.exists():
            cache = json.loads(self.settings.encoding_cache_path.read_text(encoding="utf-8"))
            self.known_names = [entry["name"] for entry in cache["entries"]]
            self.known_files = [entry["source_file"] for entry in cache["entries"]]
            self.known_encodings = np.array([entry["encoding"] for entry in cache["entries"]], dtype=float)
            self.cache_warnings = cache.get("warnings", [])
            return self.cache_warnings

        entries: list[dict] = []
        warnings: list[str] = []
        for file_path in sorted(self.settings.reference_dir.glob("*")):
            if not file_path.is_file():
                continue
            try:
                image = self.face_recognition.load_image_file(file_path)
                encodings = self.face_recognition.face_encodings(image)
            except Exception as exc:
                warnings.append(f"{file_path.name}: failed to load ({exc})")
                continue
            if len(encodings) != 1:
                warnings.append(
                    f"{file_path.name}: expected 1 face in reference photo, found {len(encodings)}"
                )
                continue
            entries.append(
                {
                    "name": parse_student_name(file_path),
                    "source_file": file_path.name,
                    "encoding": encodings[0].tolist(),
                }
            )

        payload = {
            "built_at": datetime.now(timezone.utc).isoformat(),
            "entries": entries,
            "warnings": warnings,
        }
        self.settings.encoding_cache_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        self.known_names = [entry["name"] for entry in entries]
        self.known_files = [entry["source_file"] for entry in entries]
        self.known_encodings = np.array([entry["encoding"] for entry in entries], dtype=float)
        self.cache_warnings = warnings
        return warnings

    def known_count(self) -> int:
        return len(self.known_names)

    def process_upload(self, source_path: Path, original_filename: str) -> dict:
        saved_name = self._store_upload(source_path, original_filename)
        upload_path = self.settings.uploads_dir / saved_name
        analyzed_path = upload_path
        try:
            detections, analyzed_path = self._recognize_faces(upload_path)
            annotated_name = self._write_annotated_image(analyzed_path, detections)
            matched_count = sum(1 for detection in detections if detection.name != "Unknown")
            return {
                "photo": {
                    "original_filename": original_filename,
                    "stored_filename": saved_name,
                    "annotated_filename": annotated_name,
                    "uploaded_at": datetime.now(timezone.utc).isoformat(),
                    "status": "processed",
                    "face_count": len(detections),
                    "matched_count": matched_count,
                },
                "detections": [
                    {
                        "name": detection.name,
                        "distance": detection.distance,
                        "top": detection.top,
                        "right": detection.right,
                        "bottom": detection.bottom,
                        "left": detection.left,
                    }
                    for detection in detections
                ],
            }
        finally:
            if analyzed_path != upload_path:
                analyzed_path.unlink(missing_ok=True)

    def _store_upload(self, source_path: Path, original_filename: str) -> str:
        extension = Path(original_filename).suffix.lower() or ".jpg"
        saved_name = f"{uuid.uuid4().hex}{extension}"
        target_path = self.settings.uploads_dir / saved_name
        shutil.copy2(source_path, target_path)
        return saved_name

    def _recognize_faces(self, image_path: Path) -> tuple[list[DetectionResult], Path]:
        resized_path = self._resize_large_image(image_path)
        image = self.face_recognition.load_image_file(resized_path)
        locations = self.face_recognition.face_locations(
            image,
            number_of_times_to_upsample=self.settings.upsample_times,
            model=self.settings.detection_model,
        )
        encodings = self.face_recognition.face_encodings(image, locations)
        results: list[DetectionResult] = []
        for location, encoding in zip(locations, encodings):
            name = "Unknown"
            distance: float | None = None
            if len(self.known_encodings) > 0:
                face_distances = self.face_recognition.face_distance(self.known_encodings, encoding)
                best_index = int(np.argmin(face_distances))
                best_distance = float(face_distances[best_index])
                if best_distance <= self.settings.tolerance:
                    name = self.known_names[best_index]
                distance = best_distance
            top, right, bottom, left = [int(value) for value in location]
            results.append(
                DetectionResult(
                    name=name,
                    distance=distance,
                    top=top,
                    right=right,
                    bottom=bottom,
                    left=left,
                )
            )
        return results, resized_path

    def _resize_large_image(self, image_path: Path) -> Path:
        with Image.open(image_path) as image:
            if image.width <= self.settings.max_image_width:
                return image_path
            scale = self.settings.max_image_width / float(image.width)
            resized = image.resize(
                (self.settings.max_image_width, int(image.height * scale)),
                Image.Resampling.LANCZOS,
            )
            resized_path = image_path.with_name(f"{image_path.stem}_resized{image_path.suffix}")
            resized.save(resized_path)
            return resized_path

    def _write_annotated_image(self, image_path: Path, detections: list[DetectionResult]) -> str:
        output_name = f"{image_path.stem}_tagged.jpg"
        output_path = self.settings.processed_dir / output_name
        with Image.open(image_path) as image:
            draw = ImageDraw.Draw(image)
            for detection in detections:
                color = "#3f8efc" if detection.name != "Unknown" else "#d97706"
                draw.rectangle(
                    [(detection.left, detection.top), (detection.right, detection.bottom)],
                    outline=color,
                    width=4,
                )
                label = detection.name
                if detection.distance is not None:
                    label = f"{label} ({detection.distance:.2f})"
                text_box_top = max(0, detection.top - 28)
                draw.rectangle(
                    [(detection.left, text_box_top), (detection.right, detection.top)],
                    fill=color,
                )
                draw.text((detection.left + 6, text_box_top + 6), label, fill="white")
            image.convert("RGB").save(output_path, quality=92)
        return output_name
