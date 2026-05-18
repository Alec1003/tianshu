$ErrorActionPreference = "Stop"

$pidFile = Join-Path $PSScriptRoot ".ai_server.pid"

if (!(Test-Path $pidFile)) {
  Write-Output "No PID file found: $pidFile"
  exit 0
}

$pidValue = Get-Content $pidFile -ErrorAction SilentlyContinue
if (!$pidValue) {
  Write-Output "PID file is empty: $pidFile"
  Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
  exit 0
}

try {
  Stop-Process -Id ([int]$pidValue) -Force -ErrorAction SilentlyContinue
  Write-Output "Stopped AI backend process: $pidValue"
} catch {
  Write-Output "Failed to stop process ${pidValue}: $($_.Exception.Message)"
}

Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
