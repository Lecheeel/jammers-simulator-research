param([Parameter(Mandatory=$true)][string]$CaseName)
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$safe = $CaseName -replace '[^A-Za-z0-9._-]', '_'
$dir = Join-Path $root (Join-Path 'artifacts' $safe)
New-Item -ItemType Directory -Force -Path $dir | Out-Null
Get-ComputerInfo -Property WindowsProductName,WindowsVersion,OsBuildNumber | Out-File (Join-Path $dir 'environment.txt')
Get-Date -Format o | Out-File (Join-Path $dir 'started-at.txt')
Write-Output "Prepared test record: $dir"
