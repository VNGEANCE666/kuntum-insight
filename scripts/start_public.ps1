param(
    [int]$Port = 8000
)
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$cf = Join-Path $env:LOCALAPPDATA "cloudflared\cloudflared.exe"
if (-not (Test-Path $cf)) {
    Write-Host "cloudflared belum ada - mengunduh..."
    New-Item -ItemType Directory -Force -Path (Split-Path $cf) | Out-Null
    Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $cf -UseBasicParsing
}

$alreadyRunning = $false
try {
    Invoke-WebRequest "http://127.0.0.1:$Port/api/pipeline/status" -UseBasicParsing -TimeoutSec 2 | Out-Null
    $alreadyRunning = $true
} catch {}

if (-not $alreadyRunning) {
    $env:PYTHONPATH = "backend_seed"
    Start-Process python -ArgumentList "-m", "uvicorn", "backend_seed.main:app", "--host", "127.0.0.1", "--port", "$Port" -WindowStyle Minimized | Out-Null
    Write-Host "Menyiapkan uvicorn di port $Port (jendela minimasi)..."
    $ready = $false
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Seconds 1
        try {
            Invoke-WebRequest "http://127.0.0.1:$Port/api/pipeline/status" -UseBasicParsing -TimeoutSec 3 | Out-Null
            $ready = $true
            break
        } catch {}
    }
    if (-not $ready) {
        Write-Host "uvicorn tidak merespons dalam 40 detik - cek window uvicorn."
        exit 1
    }
    Write-Host "uvicorn siap."
} else {
    Write-Host "uvicorn sudah berjalan di port $Port."
}

$cfOut = Join-Path $env:TEMP "ki_cf_out.txt"
$cfErr = Join-Path $env:TEMP "ki_cf_err.txt"
Start-Process $cf -ArgumentList "tunnel", "--url", "http://127.0.0.1:$Port", "--no-autoupdate" -WindowStyle Minimized -RedirectStandardOutput $cfOut -RedirectStandardError $cfErr | Out-Null

$url = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    $all = (Get-Content $cfOut, $cfErr -ErrorAction SilentlyContinue) -join "`n"
    if ($all -match "https://[a-z0-9-]+\.trycloudflare\.com") { $url = $matches[0]; break }
}

if (-not $url) {
    Write-Host "Tidak menemukan URL tunnel. Isi log terakhir:"
    Get-Content $cfOut, $cfErr -ErrorAction SilentlyContinue | Select-Object -Last 15
    exit 1
}

Write-Host ""
Write-Host "==============================================================="
Write-Host "  URL PUBLIK: $url"
Write-Host "  Jangan tutup jendela PowerShell ini & cloudflared."
Write-Host "  (URL baru akan berbeda setiap kali script ini dijalankan ulang)"
Write-Host "==============================================================="