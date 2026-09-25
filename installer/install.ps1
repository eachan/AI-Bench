<#
.SYNOPSIS
    One-script installer for AI-Bench on Windows.

.DESCRIPTION
    Installs and updates everything AI-Bench needs, with no manual steps:
      * Ensures Python 3.11+ and Node.js LTS are present (installs via winget if
        missing).
      * Creates an isolated Python virtual environment and installs the backend
        and desktop dependencies.
      * Builds the web UI.
      * Downloads the llama.cpp `llama-bench` Windows binary so the llama.cpp
        benchmark works out of the box (best-effort; the app still runs its
        synthetic benchmarks without it).
      * Creates a Start Menu + Desktop shortcut that launches the app.

    Re-running this script updates dependencies and the UI in place.

.EXAMPLE
    # From a PowerShell prompt (no admin required for winget user installs):
    #   Set-ExecutionPolicy -Scope Process Bypass -Force
    #   .\install.ps1
#>

[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "AI-Bench"),
    [switch]$SkipLlamaCpp
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn2($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

function Ensure-Tool {
    param([string]$Command, [string]$WingetId, [string]$FriendlyName)
    if (Get-Command $Command -ErrorAction SilentlyContinue) {
        Write-Ok "$FriendlyName found."
        return
    }
    Write-Step "Installing $FriendlyName via winget ($WingetId)..."
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "winget is not available. Please install $FriendlyName manually, then re-run."
    }
    winget install --id $WingetId --silent --accept-package-agreements --accept-source-agreements
    # Refresh PATH for the current session.
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User")
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        throw "$FriendlyName still not on PATH. Open a new terminal and re-run install.ps1."
    }
}

Write-Step "AI-Bench installer"
Write-Ok "Repo:      $RepoRoot"
Write-Ok "Install:   $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

# --- 1. Prerequisites ------------------------------------------------------ #
Ensure-Tool -Command "python" -WingetId "Python.Python.3.12" -FriendlyName "Python 3.12"
Ensure-Tool -Command "node"   -WingetId "OpenJS.NodeJS.LTS"  -FriendlyName "Node.js LTS"

# --- 2. Python virtual environment ----------------------------------------- #
$VenvDir = Join-Path $InstallDir "venv"
if (-not (Test-Path (Join-Path $VenvDir "Scripts\python.exe"))) {
    Write-Step "Creating Python virtual environment..."
    python -m venv $VenvDir
}
$VenvPy = Join-Path $VenvDir "Scripts\python.exe"

Write-Step "Installing/updating backend dependencies..."
& $VenvPy -m pip install --upgrade pip | Out-Null
& $VenvPy -m pip install -r (Join-Path $RepoRoot "backend\requirements.txt")
& $VenvPy -m pip install -r (Join-Path $RepoRoot "desktop\requirements.txt")
Write-Ok "Python dependencies ready."

# --- 3. Build the web UI --------------------------------------------------- #
Write-Step "Building the web UI..."
Push-Location (Join-Path $RepoRoot "frontend")
try {
    if (Test-Path "package-lock.json") { npm ci } else { npm install }
    npm run build
    Write-Ok "UI built to frontend\dist."
} finally {
    Pop-Location
}

# --- 4. llama.cpp llama-bench binary (best effort) ------------------------- #
$BinDir = Join-Path $InstallDir "bin"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$LlamaBench = Join-Path $BinDir "llama-bench.exe"
if (-not $SkipLlamaCpp -and -not (Test-Path $LlamaBench)) {
    Write-Step "Downloading llama.cpp (llama-bench) Windows binary..."
    try {
        $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest" `
            -Headers @{ "User-Agent" = "AI-Bench-Installer" }
        $asset = $rel.assets | Where-Object { $_.name -match "win.*x64.*\.zip$" } | Select-Object -First 1
        if ($asset) {
            $zip = Join-Path $env:TEMP $asset.name
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip -UseBasicParsing
            $tmp = Join-Path $env:TEMP "llamacpp_extract"
            Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
            Expand-Archive -Path $zip -DestinationPath $tmp -Force
            $found = Get-ChildItem -Path $tmp -Recurse -Filter "llama-bench.exe" | Select-Object -First 1
            if ($found) {
                Copy-Item $found.FullName $LlamaBench -Force
                # Copy any sibling DLLs the binary depends on.
                Get-ChildItem -Path $found.DirectoryName -Filter "*.dll" |
                    ForEach-Object { Copy-Item $_.FullName $BinDir -Force }
                Write-Ok "llama-bench installed."
            } else {
                Write-Warn2 "llama-bench.exe not found in release archive; skipping."
            }
        } else {
            Write-Warn2 "No suitable Windows asset found; skipping llama.cpp."
        }
    } catch {
        Write-Warn2 "Could not download llama.cpp automatically ($($_.Exception.Message))."
        Write-Warn2 "AI-Bench will still run with its built-in synthetic benchmarks."
    }
}

# --- 5. Launcher + shortcuts ----------------------------------------------- #
Write-Step "Creating launcher and shortcuts..."
$RunScript = Join-Path $InstallDir "run.ps1"
@"
`$ErrorActionPreference = 'Stop'
`$env:AIBENCH_DATA_DIR = '$InstallDir\data'
if (Test-Path '$LlamaBench') { `$env:AIBENCH_LLAMA_BENCH = '$LlamaBench' }
& '$VenvPy' '$RepoRoot\desktop\launcher.py'
"@ | Set-Content -Path $RunScript -Encoding UTF8

$WshShell = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath("Desktop"),
                   (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"))) {
    $lnk = Join-Path $dir "AI-Bench.lnk"
    $sc = $WshShell.CreateShortcut($lnk)
    $sc.TargetPath = "powershell.exe"
    $sc.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$RunScript`""
    $sc.WorkingDirectory = $InstallDir
    $sc.Description = "AI-Bench — Local ML/LLM Profiler"
    $sc.Save()
}
Write-Ok "Shortcuts created (Desktop + Start Menu)."

Write-Host ""
Write-Step "Installation complete!"
Write-Host "    Launch AI-Bench from the Start Menu or Desktop shortcut," -ForegroundColor Green
Write-Host "    or run:  powershell -ExecutionPolicy Bypass -File `"$RunScript`"" -ForegroundColor Green
