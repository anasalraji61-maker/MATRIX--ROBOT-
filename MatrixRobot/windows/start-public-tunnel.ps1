# Starts a Cloudflare quick tunnel to the local Dashboard (port 5173).
# Works from cellular / any network — not limited to home Wi-Fi.
# Writes the public HTTPS URL to $env:TEMP\matrix-robot-public-url.txt

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$exe = Join-Path $here "cloudflared.exe"
$urlFile = Join-Path $env:TEMP "matrix-robot-public-url.txt"
$logFile = Join-Path $env:TEMP "matrix-robot-tunnel.log"
$pidFile = Join-Path $env:TEMP "matrix-robot-tunnel.pid"

# Stop any previous dashboard tunnel we started
if (Test-Path $pidFile) {
  $oldPid = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue
  if ($oldPid) {
    Stop-Process -Id ([int]$oldPid) -Force -ErrorAction SilentlyContinue
  }
}
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.Name -match 'cloudflared' -and
    $_.CommandLine -match '127\.0\.0\.1:5173|localhost:5173'
  } |
  ForEach-Object {
    try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
  }

if (Test-Path $urlFile) { Remove-Item -Force $urlFile -ErrorAction SilentlyContinue }
if (Test-Path $logFile) { Remove-Item -Force $logFile -ErrorAction SilentlyContinue }
if (Test-Path $pidFile) { Remove-Item -Force $pidFile -ErrorAction SilentlyContinue }
if (Test-Path (Join-Path $env:TEMP "matrix-robot-tunnel-out.log")) {
  Remove-Item -Force (Join-Path $env:TEMP "matrix-robot-tunnel-out.log") -ErrorAction SilentlyContinue
}

if (-not (Test-Path -LiteralPath $exe)) {
  Write-Host "Downloading cloudflared.exe (one-time)..."
  $uri = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
  Invoke-WebRequest -Uri $uri -OutFile $exe -UseBasicParsing
}

# cloudflared prints the public URL on stderr
$proc = Start-Process -FilePath $exe `
  -ArgumentList @("tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:5173") `
  -WindowStyle Hidden `
  -RedirectStandardError $logFile `
  -RedirectStandardOutput (Join-Path $env:TEMP "matrix-robot-tunnel-out.log") `
  -PassThru

$proc.Id | Set-Content -LiteralPath $pidFile -NoNewline

$publicUrl = $null
for ($i = 0; $i -lt 45; $i++) {
  Start-Sleep -Seconds 1
  if (-not (Test-Path -LiteralPath $logFile)) { continue }
  $text = Get-Content -LiteralPath $logFile -Raw -ErrorAction SilentlyContinue
  if (-not $text) { continue }
  $m = [regex]::Match($text, "https://[a-zA-Z0-9-]+\.trycloudflare\.com")
  if ($m.Success) {
    $publicUrl = $m.Value
    break
  }
}

if (-not $publicUrl) {
  Write-Error "Cloudflare tunnel started but no public URL appeared. See $logFile"
  exit 1
}

$publicUrl | Set-Content -LiteralPath $urlFile -NoNewline
Write-Output $publicUrl
exit 0
