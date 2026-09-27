<#
.SYNOPSIS
    Builds the AI-Bench Windows wizard installer (AI-Bench-Setup.exe).

.DESCRIPTION
    End-to-end build:
      1. Builds the web UI (npm ci + npm run build).
      2. Creates a build venv and installs backend + desktop deps + PyInstaller.
      3. (Optional) Downloads the llama.cpp `llama-bench` binary to bundle.
      4. Packages a self-contained app with PyInstaller (dist\AI-Bench\).
      5. Compiles the Inno Setup wizard into installer\Output\AI-Bench-Setup.exe.

    Requires: Python 3.11+, Node.js LTS, and Inno Setup 6 (ISCC.exe). On GitHub
    Actions windows-latest these are available (Inno Setup via `choco install
    innosetup`). Run from anywhere; paths are resolved relative to the repo.

.PARAMETER Version
    Version stamped into the installer (default 1.0.0).

.PARAMETER SkipLlamaCpp
    Skip downloading/bundling the llama-bench binary.
#>

[CmdletBinding()]
param(
    [string]$Version = "1.0.0",
    [switch]$SkipLlamaCpp,
    [switch]$SkipMlperf,
    [string]$MlperfReleaseTag = "v2.0.1"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Write-Step($m) { Write-Host "==> $m" -ForegroundColor Cyan }

function Get-SignTool {
    $cmd = Get-Command "signtool.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $found = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
    if ($found) { return $found.FullName }
    return $null
}

# Authenticode-sign a file when a code-signing certificate is provided via the
# WINDOWS_CERT_PFX_BASE64 (+ WINDOWS_CERT_PASSWORD) environment variables /
# GitHub secrets. No-op (with a notice) when no certificate is configured, so
# unsigned builds still succeed.
function Invoke-CodeSign([string]$File) {
    $b64 = $env:WINDOWS_CERT_PFX_BASE64
    if (-not $b64) {
        Write-Host "    Code signing skipped for $(Split-Path $File -Leaf) (no WINDOWS_CERT_PFX_BASE64 secret)." -ForegroundColor Yellow
        return
    }
    $st = Get-SignTool
    if (-not $st) { Write-Host "    signtool.exe not found; skipping signing." -ForegroundColor Yellow; return }
    $pfx = Join-Path $env:TEMP "aibench-signing.pfx"
    [IO.File]::WriteAllBytes($pfx, [Convert]::FromBase64String($b64))
    try {
        $args = @("sign", "/fd", "SHA256", "/tr", "http://timestamp.digicert.com", "/td", "SHA256", "/f", $pfx)
        if ($env:WINDOWS_CERT_PASSWORD) { $args += @("/p", $env:WINDOWS_CERT_PASSWORD) }
        $args += $File
        & $st @args
        if ($LASTEXITCODE -ne 0) { throw "signtool failed ($LASTEXITCODE)" }
        Write-Host "    Signed $(Split-Path $File -Leaf)." -ForegroundColor Green
    } finally {
        Remove-Item $pfx -ErrorAction SilentlyContinue
    }
}

# --- 1. Build the web UI --------------------------------------------------- #
Write-Step "Building web UI"
Push-Location "$RepoRoot\frontend"
try {
    if (Test-Path "package-lock.json") { npm ci } else { npm install }
    npm run build
} finally { Pop-Location }

# --- 2. Python build environment ------------------------------------------- #
Write-Step "Setting up build virtual environment"
$Venv = "$RepoRoot\.build-venv"
if (-not (Test-Path "$Venv\Scripts\python.exe")) { python -m venv $Venv }
$Py = "$Venv\Scripts\python.exe"
& $Py -m pip install --upgrade pip | Out-Null
& $Py -m pip install -r "$RepoRoot\backend\requirements.txt"
& $Py -m pip install -r "$RepoRoot\desktop\requirements.txt"
& $Py -m pip install pyinstaller==6.11.1

# --- 3. Optional: stage llama-bench to bundle ------------------------------ #
$StageBin = "$RepoRoot\.build-bin"
if (-not $SkipLlamaCpp) {
    Write-Step "Downloading llama.cpp (llama-bench) to bundle"
    try {
        New-Item -ItemType Directory -Force -Path $StageBin | Out-Null
        $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest" `
            -Headers @{ "User-Agent" = "AI-Bench-Build" }
        $asset = $rel.assets | Where-Object { $_.name -match "win.*x64.*\.zip$" } | Select-Object -First 1
        if ($asset) {
            $zip = Join-Path $env:TEMP $asset.name
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip -UseBasicParsing
            $tmp = Join-Path $env:TEMP "llamacpp_extract"
            Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
            Expand-Archive -Path $zip -DestinationPath $tmp -Force
            $bench = Get-ChildItem -Path $tmp -Recurse -Filter "llama-bench.exe" | Select-Object -First 1
            if ($bench) {
                Copy-Item $bench.FullName $StageBin -Force
                Get-ChildItem -Path $bench.DirectoryName -Filter "*.dll" |
                    ForEach-Object { Copy-Item $_.FullName $StageBin -Force }
                $env:AIBENCH_BUNDLE_BIN = $StageBin
                Write-Host "    Bundling llama-bench from $StageBin"
            } else {
                Write-Host "    llama-bench.exe not found in release; continuing without it." -ForegroundColor Yellow
            }
        }
    } catch {
        Write-Host "    Skipping llama-bench bundle: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# --- 3b. Optional: stage the MLPerf Client binary to bundle ---------------- #
if (-not $SkipMlperf) {
    Write-Step "Downloading MLPerf Client ($MlperfReleaseTag, windows-x64) to bundle"
    try {
        New-Item -ItemType Directory -Force -Path $StageBin | Out-Null
        $mlperfDir = Join-Path $StageBin "mlperf"
        Remove-Item -Recurse -Force $mlperfDir -ErrorAction SilentlyContinue
        New-Item -ItemType Directory -Force -Path $mlperfDir | Out-Null
        $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/mlcommons/mlperf_client/releases/tags/$MlperfReleaseTag" `
            -Headers @{ "User-Agent" = "AI-Bench-Build" }
        # Prefer the non-GUI CLI build for x64 (the app drives it headless).
        $asset = $rel.assets |
            Where-Object { $_.name -match "windows-x64\.zip$" -and $_.name -notmatch "gui" } |
            Select-Object -First 1
        if ($asset) {
            $zip = Join-Path $env:TEMP $asset.name
            Write-Host "    Downloading $($asset.name) ($([math]::Round($asset.size/1MB)) MB)..."
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip -UseBasicParsing
            Expand-Archive -Path $zip -DestinationPath $mlperfDir -Force
            $exe = Get-ChildItem -Path $mlperfDir -Recurse -Filter "mlperf-windows*.exe" | Select-Object -First 1
            if ($exe) {
                $env:AIBENCH_BUNDLE_BIN = $StageBin
                Write-Host "    Bundling MLPerf Client from $mlperfDir (exe: $($exe.Name))"
            } else {
                Write-Host "    MLPerf exe not found after extraction; continuing without it." -ForegroundColor Yellow
            }
        } else {
            Write-Host "    No windows-x64 MLPerf asset found for $MlperfReleaseTag." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "    Skipping MLPerf bundle: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# --- 4. PyInstaller package ------------------------------------------------ #
Write-Step "Packaging app with PyInstaller"
Remove-Item -Recurse -Force "$RepoRoot\dist\AI-Bench" -ErrorAction SilentlyContinue
& $Py -m PyInstaller --noconfirm --clean "$RepoRoot\installer\aibench.spec"
if (-not (Test-Path "$RepoRoot\dist\AI-Bench\AI-Bench.exe")) {
    throw "PyInstaller did not produce dist\AI-Bench\AI-Bench.exe"
}
# Sign the app executable (if a certificate is configured) before packaging.
Invoke-CodeSign "$RepoRoot\dist\AI-Bench\AI-Bench.exe"

# --- 5. Compile the Inno Setup wizard -------------------------------------- #
Write-Step "Compiling Inno Setup wizard"
$Iscc = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
if (-not $Iscc) {
    $guess = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (Test-Path $guess) { $Iscc = $guess } else { throw "ISCC.exe (Inno Setup 6) not found." }
} else { $Iscc = $Iscc.Source }

& $Iscc "/DMyAppVersion=$Version" "$RepoRoot\installer\ai-bench.iss"
$Setup = "$RepoRoot\installer\Output\AI-Bench-Setup.exe"
if (-not (Test-Path $Setup)) { throw "Installer was not produced." }

# Sign the final installer (if a certificate is configured).
Invoke-CodeSign $Setup

Write-Step "Done"
Write-Host "    Installer: $Setup" -ForegroundColor Green
