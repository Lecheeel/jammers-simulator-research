[CmdletBinding()]
param(
    [int]$Seed = 1234,
    [string]$CaseName = "smoke"
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$out = Join-Path $root (Join-Path 'artifacts' $CaseName)
New-Item -ItemType Directory -Force -Path $out | Out-Null

& (Join-Path $PSScriptRoot 'verify-sample.ps1')
& (Join-Path $PSScriptRoot 'prepare-test.ps1') -CaseName $CaseName
python (Join-Path $root 'automation\jammers_simulator.py') --seed $Seed --count 4 --out (Join-Path $out 'scenario.json')
if ($LASTEXITCODE -ne 0) { throw "Scenario generation failed with exit code $LASTEXITCODE" }
Write-Output "Automation smoke complete: $out"
