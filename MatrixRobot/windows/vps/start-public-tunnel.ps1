# Cloudflare quick tunnel → local API+Dashboard on port 8080 (ForexVPS).
# Writes public URL to $env:TEMP\matrix-robot-vps-public-url.txt

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$windowsDir = Split-Path -Parent $here
$exe = Join-Path $windowsDir "cloudflared.exe"
$urlFile = Join-Path $env:TEMP "matrix-robot-vps-public-url.txt"
$logFile = Join-Path $env:TEMP "matrix-robot-vps-tunnel.log"
$pidFile = Join-Path $env:TEMP "matrix-robot-vps-tunnel.pid"
$outLog = Join-Path $env:TEMP "matrix-robot-vps-tunnel-out.log"

# Stop previous VPS dashboard tunnel
if (Test-Path $pidFile) {
  $oldPid = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue
  if ($oldPid) { Stop-Process -Id ([int]$oldPid) -Force -ErrorAction SilentlyContinue }
}
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.Name -match 'cloudflared' -and
    $_.CommandLine -match '127\.0\.0\.1:8080|localhost:8080'
  } |
  ForEach-Object {
    try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
  }

foreach ($f in @($urlFile, $logFile, $pidFile, $outLog)) {
  if (Test-Path $f) { Remove-Item -Force $f -ErrorAction SilentlyContinue }
}

if (-not (Test-Path -LiteralPath $exe)) {
  Write-Host "Downloading cloudflared.exe (one-time)..."
  $uri = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
  Invoke-WebRequest -Uri $uri -OutFile $exe -UseBasicParsing
}

$proc = Start-Process -FilePath $exe `
  -ArgumentList @("tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:8080") `
  -WindowStyle Hidden `
  -RedirectStandardError $logFile `
  -RedirectStandardOutput $outLog `
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
  Write-Error "Tunnel started but no public URL. See $logFile"
  exit 1
}

$publicUrl | Set-Content -LiteralPath $urlFile -NoNewline
Write-Output $publicUrl
exit 0
