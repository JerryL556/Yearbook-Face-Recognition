# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata


project_root = Path.cwd()
app_root = project_root / "student_tagger_app"

datas = [
    (str(app_root / "templates"), "student_tagger_app/templates"),
    (str(app_root / "static"), "student_tagger_app/static"),
    (str(project_root / "FACES"), "FACES"),
    (str(project_root / "LICENSE"), "."),
]
local_face_repo = project_root / "face_recognition-master"
if local_face_repo.exists():
    datas.append((str(local_face_repo), "face_recognition-master"))
datas += collect_data_files("face_recognition_models")
datas += copy_metadata("face_recognition_models")
datas += copy_metadata("setuptools")

binaries = []
try:
    binaries += collect_dynamic_libs("dlib")
except Exception:
    pass

hiddenimports = []
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("face_recognition")
hiddenimports += collect_submodules("face_recognition_models")
hiddenimports += [
    "PIL._tkinter_finder",
    "dlib",
    "pkg_resources",
    "_dlib_pybind11",
]


a = Analysis(
    ["student_tagger_app/run.py"],
    pathex=[str(app_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Student Photo Tagger",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Student Photo Tagger",
)
