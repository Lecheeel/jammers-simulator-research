param([string]$SamplePath = (Join-Path $PSScriptRoot '..\sample\jammers-simulator.exe'))
$expected = '2373B9E7AF83735A04309E2983EB433EC46FAF7E0B8494410CE7FDED2A297C27'
if (-not (Test-Path -LiteralPath $SamplePath)) { throw "Sample not found: $SamplePath" }
$actual = (Get-FileHash -LiteralPath $SamplePath -Algorithm SHA256).Hash.ToUpperInvariant()
if ($actual -ne $expected) { throw "Hash mismatch. Expected $expected, got $actual" }
Write-Output "OK: SHA-256 $actual"
