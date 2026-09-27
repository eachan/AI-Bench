# PyInstaller spec for AI-Bench.
#
# Produces a self-contained onedir application (dist/AI-Bench/) that bundles the
# FastAPI backend, the built web UI, and (optionally) benchmark binaries, so end
# users need neither Python nor Node installed.
#
# Build from the repo root:
#     pyinstaller installer/aibench.spec
#
# Optional: set AIBENCH_BUNDLE_BIN to a directory whose contents are bundled
# under bin/ (e.g. a downloaded llama-bench.exe and its DLLs).

import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
BACKEND = os.path.join(ROOT, "backend")
LAUNCHER = os.path.join(ROOT, "desktop", "launcher.py")
FRONTEND_DIST = os.path.join(ROOT, "frontend", "dist")

# Make the backend package importable during analysis (it lives in backend/).
sys.path.insert(0, BACKEND)

hiddenimports = []
datas = []
binaries = []

hiddenimports += collect_submodules("aibench")

# Collect packages that use dynamic imports or ship binary extensions.
for pkg in ["uvicorn", "webview", "pydantic", "anyio", "httpx", "httpcore", "websockets"]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:  # pragma: no cover - best effort per environment
        print(f"[aibench.spec] skip collect_all({pkg}): {exc}")

# Bundle the built web UI so the app can serve it offline.
if os.path.isdir(FRONTEND_DIST):
    datas.append((FRONTEND_DIST, os.path.join("frontend", "dist")))
else:
    raise SystemExit(
        "frontend/dist not found — run `npm run build` in frontend/ before packaging."
    )

# Optionally bundle benchmark binaries staged in a directory.
bundle_bin = os.environ.get("AIBENCH_BUNDLE_BIN")
if bundle_bin and os.path.isdir(bundle_bin):
    datas.append((bundle_bin, "bin"))

icon = os.path.join(ROOT, "installer", "aibench.ico")
icon = icon if os.path.exists(icon) else None

a = Analysis(
    [LAUNCHER],
    pathex=[BACKEND, ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # pkg_resources/setuptools are not used at runtime; excluding them avoids the
    # PyInstaller pkg_resources runtime hook pulling in the vendored 'jaraco'
    # namespace (which triggers a startup ImportError).
    excludes=[
        "tkinter",
        "matplotlib",
        "PyQt5",
        "PySide2",
        "pkg_resources",
        "setuptools",
        "pip",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AI-Bench",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="AI-Bench",
)
