### E-PYTEST
- title: Python compatibility core regression
- observed_at: 2026-09-12T17:18:18.4931366+08:00
- source_type: command
- source_ref: append-evidence.ps1
- content_hash: sha256:d1cf72448cca30c2d51c567a7ebbf746687cd0c77553326a263b24659a6d3cea
- artifact_path: evidence/scenario-1234.json
- severity: info
- status: validated
- location: n/a
- repro_command: |
    python -m pytest -q
    python test_jammers_simulator.py
- raw_excerpt: |
    n/a
- linked_workitem: n/a
- supersedes: none
- notes: |
    24 pytest cases pass, covering countdown, entry and program timeouts,
    movement accumulation, measurement/coverage, clearing, abort/exit, and
    snapshot restoration, timing overrides, Q1/Q2 geometry, and strict protocol
    timing. B题 Monte Carlo and sensitivity artifacts are under
    `../../work/b_experiments2/`; the direct smoke test also reports ok.
