# Jammers Simulator reverse-engineering report

## Scope and identity

- Sample: local offline `sample/jammers-simulator.exe`
- SHA-256: `2373b9e7af83735a04309e2983eb433ec46faf7e0b8494410ce7fded2a297c27`
- Format: PE32+ x86-64 Windows GUI
- Runtime: Go 1.27.1, Wails v3 beta, WebView2 frontend
- UI: embedded Vue/Vite JavaScript and CSS

## Evidence → Finding → Path

### F-001 — Go/Wails simulator architecture

- severity: info
- status: validated
- confidence: high
- evidence_ids: [E-TRIAGE, E-SYMBOLS]
- location: PE metadata and recovered Go package symbols
- evidence: [`E-TRIAGE.md`](evidence/E-TRIAGE.md), [`E-SYMBOLS.md`](evidence/E-SYMBOLS.md)

The executable is a Wails desktop shell around a Vue frontend and Go simulation engine. Recovered package anchors include `scenario`, `bearingnoise`, `simcore`, `testsession`, `robotapi`, `behaviorlog` and `practicesummary`.

### F-002 — Deterministic scenario and geometry contract

- severity: info
- status: validated
- confidence: high
- evidence_ids: [E-SYMBOLS, E-PYTEST]
- location: scenario generation, geometry and lifecycle implementation
- evidence: [`E-SYMBOLS.md`](evidence/E-SYMBOLS.md), [`E-PYTEST.md`](evidence/E-PYTEST.md)

`scenario.GeneratePractice`, `DefaultGenerationRules`, `counterSource`, `insideJammerDisk` and `directionalCoverage` establish a seed-driven scenario model with omnidirectional disks, directional sectors, normalized bearings and lifecycle timing. The published Python layer reproduces the confirmed contract and keeps unresolved official-server details explicit.

### P-001 — Recovered call/data path

- path_type: callflow
- start: Wails/WebView2 UI
- goal: simulator engine and behavior summary
- evidence_ids: [E-TRIAGE, E-SYMBOLS]

```text
Wails/WebView2 UI
  → auth/session and practice controls
  → scenario.GeneratePractice(seed, rules)
  → bearingnoise / jammer geometry
  → simcore.Engine (move, measure, clear, timing)
  → behaviorlog + practice summary + local protocol adapter
```

## Published automation

The release in [`../automation/`](../automation/) contains the deterministic simulator, loopback HTTP adapter, local crypto envelope test module, GPU/NumPy pre-screen and a server launcher. [`../tests/`](../tests/) contains 18 regression tests covering timing, geometry, lifecycle, HTTP idempotency and protocol entry.

## Reproduction

```powershell
powershell -ExecutionPolicy Bypass -File ..\scripts\verify-sample.ps1
python -m pytest -q ..\tests
python ..\automation\jammers_simulator.py --seed 1234 --count 4 --out .\scenario-1234.json
```

## Limits

This is a high-fidelity compatibility implementation, not byte-for-byte equivalence or official server acceptance. Authentication, signed practice tickets, upload queues, official behavior-log encryption, external robot transport and any exact parameters not visible in the stripped executable remain out of scope.
