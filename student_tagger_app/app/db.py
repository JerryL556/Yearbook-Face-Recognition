from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable


def connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            annotated_filename TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            status TEXT NOT NULL,
            face_count INTEGER NOT NULL DEFAULT 0,
            matched_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            photo_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            distance REAL,
            top_px INTEGER NOT NULL,
            right_px INTEGER NOT NULL,
            bottom_px INTEGER NOT NULL,
            left_px INTEGER NOT NULL,
            FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE
        );
        """
    )
    _ensure_column(connection, "photos", "batch_id", "TEXT")
    _ensure_column(connection, "photos", "subfolder", "TEXT NOT NULL DEFAULT ''")
    connection.commit()


def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, column_sql: str) -> None:
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


def replace_photo_results(
    connection: sqlite3.Connection,
    photo_record: dict,
    detections: Iterable[dict],
) -> int:
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO photos (
            original_filename,
            stored_filename,
            annotated_filename,
            uploaded_at,
            status,
            face_count,
            matched_count,
            batch_id,
            subfolder
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            photo_record["original_filename"],
            photo_record["stored_filename"],
            photo_record["annotated_filename"],
            photo_record["uploaded_at"],
            photo_record["status"],
            photo_record["face_count"],
            photo_record["matched_count"],
            photo_record.get("batch_id"),
            photo_record.get("subfolder", ""),
        ),
    )
    photo_id = int(cursor.lastrowid)
    cursor.executemany(
        """
        INSERT INTO detections (
            photo_id,
            name,
            distance,
            top_px,
            right_px,
            bottom_px,
            left_px
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                photo_id,
                detection["name"],
                detection["distance"],
                detection["top"],
                detection["right"],
                detection["bottom"],
                detection["left"],
            )
            for detection in detections
        ],
    )
    connection.commit()
    return photo_id


def fetch_recent_photos(connection: sqlite3.Connection, limit: int = 24) -> list[sqlite3.Row]:
    cursor = connection.execute(
        """
        SELECT *
        FROM photos
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    return list(cursor.fetchall())


def fetch_photo(connection: sqlite3.Connection, photo_id: int) -> sqlite3.Row | None:
    cursor = connection.execute(
        """
        SELECT *
        FROM photos
        WHERE id = ?
        """,
        (photo_id,),
    )
    return cursor.fetchone()


def fetch_detections(connection: sqlite3.Connection, photo_id: int) -> list[sqlite3.Row]:
    cursor = connection.execute(
        """
        SELECT *
        FROM detections
        WHERE photo_id = ?
        ORDER BY top_px, left_px
        """,
        (photo_id,),
    )
    return list(cursor.fetchall())


def fetch_summary(connection: sqlite3.Connection) -> sqlite3.Row:
    cursor = connection.execute(
        """
        SELECT
            COUNT(*) AS total_photos,
            COALESCE(SUM(face_count), 0) AS total_faces,
            COALESCE(SUM(matched_count), 0) AS total_matches
        FROM photos
        """
    )
    return cursor.fetchone()


def fetch_tagged_folders(connection: sqlite3.Connection, limit: int = 12) -> list[sqlite3.Row]:
    cursor = connection.execute(
        """
        SELECT
            CASE
                WHEN TRIM(subfolder) = '' THEN 'Inbox'
                ELSE subfolder
            END AS folder_name,
            COUNT(*) AS photo_count,
            MAX(id) AS latest_photo_id
        FROM photos
        GROUP BY CASE
            WHEN TRIM(subfolder) = '' THEN 'Inbox'
            ELSE subfolder
        END
        ORDER BY latest_photo_id DESC
        LIMIT ?
        """,
        (limit,),
    )
    return list(cursor.fetchall())
