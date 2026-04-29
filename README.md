# Yearbook Face Recognition

Browser-based local app for reviewing batches of school/event photos, matching faces against reference portraits in `FACES/Students`, and saving tagged output into organized local folders.

## Current State

- Main app lives in `student_tagger_app`
- UI runs locally at `http://127.0.0.1:8000`
- Tagged output is saved under `student_tagger_app/data/Tagged Photos`
- Reference portraits are loaded from `FACES/Students`
- The app caches student face encodings in `student_tagger_app/data/cache/known_faces.json`

## What The App Does

- Builds a student face index from the portraits in `FACES/Students`
- Shows real-time index progress in the web UI
- Lets the user pick one destination folder for a batch using a native folder picker
- Lets the user review a file-list of uploaded photos before tagging
- Lets the user discard individual photos from the batch
- Shows hover preview near the cursor when hovering over the filename area
- Processes tagging in the background and reports live batch status
- Stores tagged images and tracks results in SQLite

## Important Folders

- `FACES/Students`
  Reference portraits used for recognition

- `student_tagger_app/data/Tagged Photos`
  Tagged output images

- `student_tagger_app/data/uploads`
  Uploaded originals copied by the app

- `student_tagger_app/data/cache/known_faces.json`
  Cached student face index

- `student_tagger_app/data/student_tagger.sqlite3`
  Photo and detection metadata

## Notes On Recognition

- Reference indexing now keeps the largest detected face in a reference portrait instead of rejecting every image with multiple detected faces.
- Warnings still appear for portraits where no usable face encoding is found.
- First-time index building can still take a while depending on the number and size of reference portraits.

## Windows Setup

From the repo root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r student_tagger_app\requirements.txt
python student_tagger_app\run.py
```

Then open:

```text
http://127.0.0.1:8000
```

## Windows Package

The repo now includes a Windows packaging path that keeps the same local web UI workflow and desktop capture helper, but bundles the Python runtime and app dependencies so the packaged app can run without Python being installed separately.

Build from the repo root:

```text
Build Windows Package.cmd
```

Output:

```text
dist\Student Photo Tagger\
```

Main packaged launcher:

```text
dist\Student Photo Tagger\Student Photo Tagger.exe
```

What the packaged folder includes:

- the web UI server
- the desktop capture helper window
- bundled Python runtime and dependencies
- web templates and static assets
- `FACES\Students` reference portraits

Practical constraint:

- Windows packaging can be built on Windows
- macOS `.app` packaging usually needs a Mac build machine

## Repo Notes

- `face_recognition-master` is intentionally kept out of git via `.gitignore`
- Runtime output under `student_tagger_app/data/` is also ignored

## Useful Files

- `SESSION_SUMMARY.txt`
  Session context for future Codex work

- `student_tagger_app/app/main.py`
  Routes, batch processing, native folder picker, progress endpoints

- `student_tagger_app/app/recognition.py`
  Recognition logic, indexing, and tagged output writing

- `student_tagger_app/templates/index.html`
  Main review/tagging UI
