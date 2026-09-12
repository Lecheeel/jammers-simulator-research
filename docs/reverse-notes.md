# Reverse-engineering notes

This document records the reproducible, offline findings for the supplied
`sample/jammers-simulator.exe`. The raw sample is a local PE and is not executed
by the extraction scripts.

## Sample identity

- Format: PE32+ x86-64 Windows GUI executable
- Runtime: Go 1.27.1
- UI shell: Wails v3 beta with WebView2; embedded Vue/Vite assets
- SHA-256: `2373B9E7AF83735A04309E2983EB433EC46FAF7E0B8494410CE7FDED2A297C27`

Reproduce the identity check with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-sample.ps1
```

## How we reversed it

1. Hash and identify the PE before any execution.
2. Inspect PE headers, sections, imports and strings with `objdump`, `strings`
   and Go metadata tooling.
3. Recover Go package/function names and inspect the embedded Wails frontend.
4. Extract embedded HTML/JavaScript into `analysis/embedded/` and search UI and
   protocol terms.
5. Reconstruct the deterministic scenario/geometry/state-machine contract in
   Python, then validate it with local regression and HTTP protocol tests.

The authoritative evidence summaries are in [`analysis/evidence/`](../analysis/evidence/),
and the extracted frontend is in [`analysis/embedded/`](../analysis/embedded/).

## Recovered components and conclusions

Recovered Go/package anchors include `scenario.GeneratePractice`,
`DefaultGenerationRules`, `bearingnoise`, `simcore.directionalCoverage`,
`insideJammerDisk`, and the deterministic `counterSource`. The lifecycle includes
preparing/countdown, enter, move, measure, clear, exit, timeout and summary paths.

The Python compatibility layer therefore implements:

- seed-stable scenario generation;
- omnidirectional disks and directional sectors;
- degree normalization and bearing quantization;
- virtual-time simulation with countdown, entry/program/virtual limits;
- movement, measurement, clear, channel switching and snapshots;
- an HTTP loopback service exposing `/enter`, `/measure`, `/clear`, `/exit` with
  validation and request-id idempotency;
- a local-only crypto envelope test module using the recovered algorithm family.

These are high-fidelity compatibility results, not a claim of byte-for-byte or
server acceptance. Official authentication, signed tickets, upload queues,
encrypted server packages and external robot transport remain out of scope.
