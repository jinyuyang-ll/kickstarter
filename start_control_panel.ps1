$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { (Get-Command python).Source }
Set-Location -LiteralPath $ProjectRoot
& $Python "web_app.py" --no-browser
exit $LASTEXITCODE

\n