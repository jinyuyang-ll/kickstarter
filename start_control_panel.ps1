$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
Set-Location -LiteralPath $ProjectRoot

$Candidates = @()
if (Test-Path -LiteralPath $VenvPython) { $Candidates += $VenvPython }
$SystemPython = Get-Command python -ErrorAction SilentlyContinue
if ($SystemPython) { $Candidates += $SystemPython.Source }
$Python = $null
foreach ($Candidate in ($Candidates | Select-Object -Unique)) {
    try {
        & $Candidate --version *> $null
        if ($LASTEXITCODE -eq 0) {
            $Python = $Candidate
            break
        }
    } catch {
        continue
    }
}
if (-not $Python) { throw "No working Python was found. Recreate .venv or install Python." }

& $Python "web_app.py" --no-browser
exit $LASTEXITCODE
