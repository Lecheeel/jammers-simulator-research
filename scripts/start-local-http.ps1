[CmdletBinding()]
param(
    [int]$Seed = 1234,
    [int]$Port = 2026,
    [string]$Host = '127.0.0.1',
    [string]$RobotId = 'local',
    [switch]$RealisticTiming
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$args = @('--seed', $Seed, '--host', $Host, '--port', $Port, '--robot-id', $RobotId)
if ($RealisticTiming) { $args += '--realistic-timing' }
python (Join-Path $root 'automation\run_http_server.py') @args
