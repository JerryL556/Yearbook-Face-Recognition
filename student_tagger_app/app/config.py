from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_root: Path
    project_root: Path
    reference_dir: Path
    uploads_dir: Path
    processed_dir: Path
    cache_dir: Path
    templates_dir: Path
    static_dir: Path
    database_path: Path
    encoding_cache_path: Path
    local_face_repo: Path
    tolerance: float = 0.48
    max_image_width: int = 1600
    upsample_times: int = 1
    detection_model: str = "hog"


def get_settings() -> Settings:
    app_root = Path(__file__).resolve().parents[1]
    project_root = app_root.parent
    data_dir = app_root / "data"
    return Settings(
        app_root=app_root,
        project_root=project_root,
        reference_dir=project_root / "FACES" / "Students",
        uploads_dir=data_dir / "uploads",
        processed_dir=data_dir / "processed",
        cache_dir=data_dir / "cache",
        templates_dir=app_root / "templates",
        static_dir=app_root / "static",
        database_path=data_dir / "student_tagger.sqlite3",
        encoding_cache_path=data_dir / "cache" / "known_faces.json",
        local_face_repo=project_root / "face_recognition-master",
    )
