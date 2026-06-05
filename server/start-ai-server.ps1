param(
  [int]$Port = 8000,
  [string]$ListenHost = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot ".python312\python.exe"
$pidFile = Join-Path $PSScriptRoot ".ai_server.pid"
$outLog = Join-Path $PSScriptRoot ".ai_server.out.log"
$errLog = Join-Path $PSScriptRoot ".ai_server.err.log"

if (!(Test-Path $pythonExe)) {
  throw "Python runtime not found: $pythonExe"
}

if (Test-Path $pidFile) {
  $oldPid = Get-Content $pidFile -ErrorAction SilentlyContinue
  if ($oldPid) {
    try {
      $oldProcess = Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue
      if ($oldProcess) {
        Stop-Process -Id $oldProcess.Id -Force -ErrorAction SilentlyContinue
        Wait-Process -Id $oldProcess.Id -Timeout 5 -ErrorAction SilentlyContinue
      }
    } catch {}
  }
  Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

if (Test-Path $outLog) { Remove-Item -LiteralPath $outLog -Force }
if (Test-Path $errLog) { Remove-Item -LiteralPath $errLog -Force }

$proc = Start-Process `
  -FilePath $pythonExe `
  -ArgumentList "-m","uvicorn","app.main:app","--host",$ListenHost,"--port",$Port `
  -WorkingDirectory $PSScriptRoot `
  -RedirectStandardOutput $outLog `
  -RedirectStandardError $errLog `
  -PassThru

$proc.Id | Set-Content -Path $pidFile

Start-Sleep -Seconds 2

Write-Output "AI backend started. PID=$($proc.Id), HOST=$ListenHost, PORT=$Port"
Write-Output "PID file: $pidFile"
Write-Output "Logs:"
Write-Output "  OUT: $outLog"
Write-Output "  ERR: $errLog"
