# Build complete V11 zip for VPS (includes runtime_state.py + ml/)
$src = "c:\Users\SK.6.4\Downloads\MatrixRobot\MatrixRobot\artifacts\python-agents"
$dest = "c:\Users\SK.6.4\Downloads\matrix_v11_full_power_v3.zip"

$items = @(
    "agents", "routes", "tools", "models", "tests", "scripts", "ml",
    "main.py", "config.py", "runtime_state.py", "requirements.txt",
    "requirements-ml.txt", "requirements-backtest.txt",
    "V11_FULL_POWER_DEMO.env.txt", "CHATGPT_V11_COMPLETE_GUIDE.md",
    "V11_FULL_POWER_CURSOR_SPEC.md"
)

$paths = foreach ($item in $items) {
    $p = Join-Path $src $item
    if (Test-Path $p) { $p }
}

if (Test-Path $dest) { Remove-Item $dest -Force }
Compress-Archive -Path $paths -DestinationPath $dest -Force
Get-Item $dest | Format-List Name, Length, LastWriteTime
