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

> **Status:** This is the initial MVP. The full application architecture,
> synthetic benchmark, hardware detection, results storage, visualizations, and
> export/import are complete and tested end-to-end. The `llama-bench` and MLPerf
> adapters implement the documented CLI/output contracts and are unit-tested
> against real output samples; running them end-to-end requires their binaries
> (installed automatically on Windows by `installer/install.ps1`).

## Features

- **One-script install** on Windows (`installer/install.ps1`) that installs and
  updates all dependencies (Python, Node, the web UI, and the llama.cpp binary)
  and creates Start Menu / Desktop shortcuts. No manual steps.
- **Automatic hardware detection** — CPU, memory and GPU(s), shown on a dashboard.
- **Automatic model/dataset downloads** for tests and synthetic loads, with
  progress (llama.cpp pulls GGUF models via `-hf`; MLPerf downloads scenario
  files from its config).
- **Clean, simple UI** for selecting and configuring tests, monitoring progress
  in real time (WebSocket), and reviewing results — all via UI controls, no
  files or commands required.
- **Visualizations, not walls of numbers** — bar charts for metric overviews,
  line charts for live/again-viewable throughput series, and grouped bar charts
  for comparisons.
- **Save / export / import** results and test-parameter settings as a shareable
  *test profile* JSON so users can compare across machines.
- **Granular configuration** of every test through sliders, number inputs,
  dropdowns and switches.

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

1. Download `AI-Bench-Setup-<version>.zip` (from the project's Releases, or the
   **Build Windows Installer** GitHub Actions run artifacts).
2. Unzip it and run **`AI-Bench-Setup.exe`**.
3. Click through the wizard (Welcome → License → install location → optional
   desktop shortcut → Install → Finish). No Python, Node, or command line needed.
4. Launch **AI-Bench** from the Start Menu or Desktop shortcut.

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
.\installer\build_installer.ps1 -Version 0.1.0
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

## Configuration

Environment variables (also set by the Windows launcher):

| Variable | Purpose |
| --- | --- |
| `AIBENCH_DATA_DIR` | Where results DB, models, datasets and configs are stored. |
| `AIBENCH_LLAMA_BENCH` | Path to the `llama-bench` binary. |
| `AIBENCH_MLPERF_CLIENT` | Path to the MLPerf Client binary. |
| `AIBENCH_HOST` / `AIBENCH_PORT` | Bind host/port for the local server. |

## Roadmap

- Wire model/dataset download UI into per-benchmark model pickers.
- Bundle prebuilt MLPerf Client binary in the installer.
- Historical trend charts across runs over time and hardware-normalized scores.
