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
├── installer/      install.ps1 (Windows one-script install) + run script
└── scripts/        dev.sh (macOS/Linux dev launcher)
```

The backend exposes a runner-adapter abstraction (`backend/aibench/runners/`):
each engine (`synthetic`, `llama-bench`, `mlperf`) implements the same
interface, so new benchmarks are easy to add. Runs execute in worker threads and
stream progress to the UI over a WebSocket; results are persisted to SQLite and
snapshot the hardware they ran on.

## Install & run

### Windows (end users)

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\installer\install.ps1
```

Then launch **AI-Bench** from the Start Menu or Desktop shortcut.

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
