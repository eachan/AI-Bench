# AI-Bench

**AI-Bench** is a local ML/LLM performance profiler for your own machine. It runs
AI/LLM benchmarks on your CPU and GPU(s) and presents the results in a clean,
simple desktop UI so you can understand what your system is capable of for local
models — and share those results with others.

It wraps two industry-standard benchmark engines:

- **[llama.cpp `llama-bench`](https://github.com/eachan/llama.cpp)** — real
  prompt-processing and text-generation throughput against GGUF models.
- **[MLPerf Client](https://github.com/eachan/MLPerf)** — standardized client
  inference benchmarks across execution providers (llama.cpp/CUDA, DirectML,
  OpenVINO, TensorRT-RTX, …).

It also ships a built-in **synthetic** benchmark (GEMM throughput, memory
bandwidth, simulated token generation) that works everywhere with no downloads,
so the app is useful the moment it starts.

> **Status: v1.0.0.** The application, the three benchmark engines, hardware
> detection, model manager, results storage, visualizations, comparison, trends,
> export/import, and the self-contained Windows wizard installer are complete and
> tested. The `llama-bench` and MLPerf adapters are validated against the real
> tools; actually running them needs their binaries (bundled by the Windows
> installer) and, for GPU results, a GPU.

## Features

- **Single-download wizard installer** for Windows (`AI-Bench-Setup.exe`) that
  clicks through Welcome → License → location → Install → Finish, creates Start
  Menu / Desktop shortcuts, and registers a proper uninstaller. No Python/Node
  needed; both benchmark binaries are bundled.
- **Automatic hardware detection** — CPU, memory and GPU(s), shown on a dashboard.
- **Model manager** — one-click downloads of curated GGUF models (or any direct
  URL) with live progress, plus a per-benchmark model picker.
- **Clean, simple UI** for selecting and configuring tests, monitoring progress
  in real time (WebSocket), and reviewing results — all via UI controls, no
  files or commands required.
- **Visualizations, not walls of numbers** — metric bar charts, live throughput
  line charts, grouped comparison charts, and metric-over-time **trends**.
- **Save / export / import** results and test-parameter settings as a shareable
  *test profile* JSON so users can compare across machines.
- **Granular configuration** of every test through sliders, number inputs,
  dropdowns and switches — including an MLPerf stock-config picker.

## Architecture

```
ai-bench/
├── backend/        FastAPI service: hardware detection, benchmark engine,
│   └── aibench/    runner adapters, downloads, SQLite storage, REST + WebSocket
├── frontend/       React + TypeScript + Vite + Tailwind + Recharts UI
├── desktop/        pywebview launcher (native desktop window)
├── installer/      Inno Setup wizard (ai-bench.iss), PyInstaller spec,
│                   build_installer.ps1, and lightweight install.ps1 bootstrap
└── scripts/        dev.sh (macOS/Linux dev launcher)
```

The backend exposes a runner-adapter abstraction (`backend/aibench/runners/`):
each engine (`synthetic`, `llama-bench`, `mlperf`) implements the same
interface, so new benchmarks are easy to add. Runs execute in worker threads and
stream progress to the UI over a WebSocket; results are persisted to SQLite and
snapshot the hardware they ran on.

## Install & run

### Windows (end users) — wizard installer

1. Download the **distribution file** `AI-Bench-<version>-windows-x64.zip` (from
   the project's Releases, or the **Build Windows Installer** GitHub Actions run
   artifacts — it is rebuilt on every change).
2. Extract it and run **`AI-Bench-Setup.exe`** (a `QUICKSTART.txt` is included).
3. Click through the wizard (Welcome → License → install location → optional
   desktop shortcut → Install → Finish). No Python, Node, or command line needed.
4. Launch **AI-Bench** from the Start Menu or Desktop shortcut.

> **The distribution file** is a single, self-contained zip that contains
> everything an end user needs: the wizard installer (which itself bundles the
> app, web UI, and both benchmark engines) plus a quick-start guide. CI builds a
> fresh one on every push, and `installer/build_installer.ps1` produces it
> locally at `installer/Output/AI-Bench-<version>-windows-x64.zip`.

The installer is fully self-contained (the app is packaged with PyInstaller and
the web UI is bundled), registers a proper **uninstaller** in *Apps & features*
/ *Add or remove programs*, and on uninstall offers to also remove your saved
results and downloaded models. It bundles both benchmark engines —
**llama.cpp `llama-bench`** and the **MLPerf Client** (with its stock scenario
configs) — so those benchmarks work out of the box (model/data files download on
first run).

> Prefer a lightweight, source-based bootstrap instead of the packaged app?
> `installer\install.ps1` sets up a venv, builds the UI, and creates shortcuts
> without PyInstaller (it installs Python/Node via winget if missing).

### Building the Windows installer yourself

The installer is built automatically on Windows by GitHub Actions
(`.github/workflows/build-installer.yml`) and uploaded as an artifact. To build
locally on Windows (requires Python, Node, and [Inno Setup 6](https://jrsoftware.org/isdl.php)):

```powershell
.\installer\build_installer.ps1 -Version 1.0.0
# → installer\Output\AI-Bench-Setup.exe

# Skip the (large) MLPerf Client download for a smaller installer:
.\installer\build_installer.ps1 -SkipMlperf
```

This builds the UI, packages the app with PyInstaller (`installer\aibench.spec`),
bundles the `llama-bench` and **MLPerf Client** binaries (the MLPerf CLI is
pulled from the `mlcommons/mlperf_client` release, `-MlperfReleaseTag`), and
compiles the Inno Setup wizard (`installer\ai-bench.iss`). Branding assets
(`installer\aibench.ico`, wizard banners, web favicon/logo) are generated from a
single source image with `python installer\gen_assets.py`.

### Code signing (optional, recommended for distribution)

To produce a **signed** installer (which avoids Windows SmartScreen warnings),
provide an Authenticode code-signing certificate as a base64-encoded PFX. The
build signs both the app executable and the final installer; if no certificate
is configured the build still succeeds and produces an unsigned installer.

- Locally: set `WINDOWS_CERT_PFX_BASE64` (and `WINDOWS_CERT_PASSWORD`) before
  running `build_installer.ps1`.
- In CI: add repository secrets `WINDOWS_CERT_PFX_BASE64` and
  `WINDOWS_CERT_PASSWORD` (base64 of your `.pfx`); the workflow passes them
  through automatically.

### Developers (macOS / Linux)

```bash
./scripts/dev.sh
# then open the printed Vite URL (http://127.0.0.1:5219)
```

Or run the pieces manually:

```bash
# Backend
cd backend && pip install -r requirements.txt
python -m uvicorn aibench.main:app --port 8760

# Frontend (in another terminal)
cd frontend && npm install && npm run dev
```

## Testing

```bash
cd backend && pip install -r requirements.txt pytest && python -m pytest
cd frontend && npm run build   # type-checks and builds
```

## Continuous integration & auto-merge

Every push and pull request runs the **Tests** workflow (`ci.yml`: backend
`pytest` + frontend type-check/build) and the **Build Windows Installer**
workflow. Pull requests are kept fully integrated automatically:

- **Auto-merge** (`auto-merge.yml`): once *all* checks on a PR are green, it is
  squash-merged into `main` and its branch is deleted. Keep a PR in **draft** to
  hold it; mark it **ready for review** to let it merge.
- One-time setup: Settings → Actions → General → Workflow permissions →
  **Read and write permissions** (so the workflow's `GITHUB_TOKEN` may merge).

Tagging a release (`git tag v1.1.0 && git push --tags`) additionally builds and
publishes the installer to GitHub Releases (`release.yml`), which the in-app
updater consumes.

## Configuration

Environment variables (also set by the Windows launcher):

| Variable | Purpose |
| --- | --- |
| `AIBENCH_DATA_DIR` | Where results DB, models, datasets and configs are stored. |
| `AIBENCH_LLAMA_BENCH` | Path to the `llama-bench` binary. |
| `AIBENCH_MLPERF_CLIENT` | Path to the MLPerf Client binary. |
| `AIBENCH_MLPERF_HOME` | Directory of the MLPerf stock configs (defaults next to the binary). |
| `AIBENCH_HOST` / `AIBENCH_PORT` | Bind host/port for the local server. |
| `AIBENCH_SERVER_ONLY` | `1` runs the API/UI server headless (no desktop window). |

## Roadmap

Shipped in v1.0.0: model download/manager UI + per-benchmark model picker,
bundled MLPerf Client with a stock-config picker, and historical trend charts.

Ideas for later:

- Hardware-normalized "capability score" and cross-machine leaderboards.
- macOS/Linux packaged installers (the app already runs cross-platform in dev).
- Scheduled/automated benchmark suites and regression alerts.
