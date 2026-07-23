# Upsert VPS co-located URLs into root .env and sync a copy for the Python brain.
# Does NOT invent secrets — only forces localhost service URLs for ForexVPS.

param(
  [Parameter(Mandatory = $true)]
  [string]$Root
)

$ErrorActionPreference = "Stop"
$rootEnv = Join-Path $Root ".env"
$brainEnv = Join-Path $Root "artifacts\python-agents\.env"

if (-not (Test-Path -LiteralPath $rootEnv)) {
  Write-Error "Missing .env at $rootEnv — copy it from the laptop (LocalSend) first."
  exit 1
}

function Set-EnvKey([string]$file, [string]$key, [string]$value) {
  $lines = @(Get-Content -LiteralPath $file -ErrorAction Stop)
  $found = $false
  $out = foreach ($line in $lines) {
    if ($line -match ("^\s*" + [regex]::Escape($key) + "\s*=")) {
      $found = $true
      "$key=$value"
    } else {
      $line
    }
  }
  if (-not $found) {
    $out += "$key=$value"
  }
  $utf8NoBom = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllLines((Resolve-Path -LiteralPath $file), [string[]]$out, $utf8NoBom)
}

Set-EnvKey $rootEnv "PORT" "8080"
Set-EnvKey $rootEnv "NODE_ENV" "production"
Set-EnvKey $rootEnv "PYTHON_AGENT_URL" "http://127.0.0.1:8000"
Set-EnvKey $rootEnv "MT5_BRIDGE_URL" "http://127.0.0.1:5555"

Copy-Item -LiteralPath $rootEnv -Destination $brainEnv -Force
Set-EnvKey $brainEnv "MT5_BRIDGE_URL" "http://127.0.0.1:5555"
Set-EnvKey $brainEnv "PORT" "8000"

Write-Output "VPS env ready: $rootEnv (+ brain copy)"
exit 0
