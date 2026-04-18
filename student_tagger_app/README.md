# Student Photo Tagger

Local web app for Windows and macOS that tags uploaded photos by matching faces against the student portraits in `FACES/Students`.

## Features

- Bulk upload from a browser
- Local face recognition with no cloud dependency
- Cached student face index
- Annotated output images with names and match distances
- SQLite-backed results history

## Project layout

- `app/`: FastAPI backend and recognition pipeline
- `templates/`: browser pages
- `static/`: styles
- `data/uploads/`: original uploaded photos
- `data/processed/`: annotated tagged images
- `data/cache/known_faces.json`: cached student encodings
- `data/student_tagger.sqlite3`: results database

## Setup

1. Create and activate a Python virtual environment.

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

macOS Terminal:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install the app requirements:

```bash
pip install -r student_tagger_app/requirements.txt
```

3. If `face_recognition` is already installed in your environment, the app will use it.
4. If it is not installed, the app will fall back to the local `face_recognition-master` source tree, but you still need its runtime dependencies:
   - `dlib`
   - `face_recognition_models`
   - `numpy`
   - `Pillow`

## Run

From the repository root:

Windows:

```powershell
python student_tagger_app/run.py
```

macOS:

```bash
python3 student_tagger_app/run.py
```

Then open `http://127.0.0.1:8000`.

## Notes

- The app assumes each file in `FACES/Students` is a single-student reference portrait.
- Accuracy improves if students have multiple good reference photos.
- Large group shots, blur, side profiles, and poor lighting will reduce match quality.
- The matching threshold is configured in `app/config.py`.
- The first startup can take a while because the app builds the student face index from `FACES/Students`.
- If `dlib` is difficult to install on a machine, resolve that first; the web app depends on it for recognition.
