### E-TRIAGE
- title: PE triage and imports
- observed_at: 2026-09-12T17:18:18.4498269+08:00
- source_type: command
- source_ref: append-evidence.ps1
- content_hash: sha256:1c7e3a8cd54df64030045a31a429e32a9a7d149fbe128372a9bd0df635556d69
- artifact_path: evidence/objdump-x.txt
- severity: info
- status: observed
- location: n/a
- repro_command: |
    objdump -x tools/jammers-simulator.exe; Get-FileHash -Algorithm SHA256 tools/jammers-simulator.exe
- raw_excerpt: |
    n/a
- linked_workitem: n/a
- supersedes: none
- notes: |
    64-bit Go 1.27.1 Wails/WebView2 PE; import table readable, kernel32-only static imports.