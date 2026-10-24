param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $repoRoot "experiments/run_e7_risk_friction_local.py"
$cases = @("210202", "210628", "210129", "210310", "210330", "210323", "210428", "210611")
$gammas = @("G0", "G2", "G4")
$lambdas = @("L0025", "L0500", "L2000")
$total = $cases.Count * $gammas.Count * $lambdas.Count
$completed = 0

Push-Location $repoRoot
try {
    foreach ($case in $cases) {
        foreach ($gamma in $gammas) {
            foreach ($lambda in $lambdas) {
                $runId = "E7-$case-$gamma-$lambda"
                Write-Host "[$runId] checking completion state"
                $statusText = & $Python $runner --status-only --case $case --gamma-token $gamma --lambda-token $lambda
                if ($LASTEXITCODE -ne 0) {
                    throw "[$runId] partial/interrupted condition detected; no files were changed: $statusText"
                }
                $status = $statusText | ConvertFrom-Json
                if ($status.state -eq "COMPLETED") {
                    $completed += 1
                    Write-Host "[$runId] validated complete; skipped"
                }
                elseif ($status.state -eq "ABSENT") {
                    Write-Host "[$runId] absent; execution started"
                    & $Python $runner --case $case --gamma-token $gamma --lambda-token $lambda
                    if ($LASTEXITCODE -ne 0) {
                        throw "[$runId] execution failed"
                    }
                    $completed += 1
                }
                else {
                    throw "[$runId] unknown completion state: $($status.state)"
                }
                Write-Host "completed=$completed remaining=$($total - $completed)"
            }
        }
    }
}
finally {
    Pop-Location
}
