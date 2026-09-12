### E-SYMBOLS
- title: Go symbols and embedded frontend
- observed_at: 2026-09-12T17:18:18.4839685+08:00
- source_type: command
- source_ref: append-evidence.ps1
- content_hash: sha256:6a55550610b016b51ce399f696a12dcda5b958bd1aef36ddcf28716783495d90
- artifact_path: evidence/go-buildid.txt
- severity: info
- status: observed
- location: n/a
- repro_command: |
    go version -m tools/jammers-simulator.exe; extract_embedded_assets.py
- raw_excerpt: |
    n/a
- linked_workitem: n/a
- supersedes: none
- notes: |
    Recovered internal package/function names and extracted embedded HTML/JS.