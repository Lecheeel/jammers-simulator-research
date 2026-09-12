# Automation API

The modules in this directory are intentionally local and deterministic. Add the
directory to `PYTHONPATH` (the repository tests do this automatically) or run the
CLI files directly.

## Scenario generation

```powershell
python .\automation\jammers_simulator.py --seed 1234 --count 16 --out .\artifacts\scenario.json
```

## Loopback protocol harness

```powershell
python .\automation\run_http_server.py --seed 1234 --port 2026
# or
powershell -ExecutionPolicy Bypass -File .\scripts\start-local-http.ps1
```

The harness binds to loopback by default. It implements `/enter`, `/measure`,
`/clear` and `/exit`, and is intended for a client under test to point at a local
fake service.

## Python API

```python
from jammers_simulator import SimulationRules, Session, generate_practice

scenario = generate_practice(1234)
session = Session(scenario, SimulationRules.fast_test())
session.enter()
result = session.measure(0, 0, channel=1)
print(result.accepted, session.summary())
```

`jammers_crypto.py` is a local test envelope only. It must not be used to claim
official server authentication or to handle real secrets. `gpu_monte_carlo.py`
uses NumPy and optionally CuPy; it is a coverage pre-screen, not the protocol
oracle.
