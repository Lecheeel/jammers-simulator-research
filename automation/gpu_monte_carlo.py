"""GPU-capable Monte Carlo helpers for the B-question stress experiments.

The full protocol simulator remains the reference implementation.  This
module accelerates the embarrassingly-parallel scenario-generation and
coverage pre-screen used to choose promising strategies.  It uses CuPy when
available and otherwise falls back to NumPy, so CI and correctness checks do
not require a CUDA Python package.

The returned statistics are intentionally labelled ``coverage_prescreen``;
they are not official test results and do not replace protocol-faithful runs
through :class:`b_model.ProtocolSimulator`.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np


@dataclass
class GPUStats:
    backend: str
    n_cases: int
    n_jammers: int
    n_waypoints: int
    mean_observable_fraction: float
    p05_observable_fraction: float
    p50_observable_fraction: float
    p95_observable_fraction: float
    elapsed_s: float


def _backend():
    try:
        import cupy as cp  # type: ignore
        cp.cuda.runtime.getDeviceCount()
        return cp, "cupy-cuda"
    except Exception:
        return np, "numpy-fallback"


def _run_xp(n_cases: int, n_jammers: int, waypoints: np.ndarray,
            seed: int, xp: Any) -> np.ndarray:
    """Return per-case fraction of jammers seen by at least one waypoint."""
    rng = xp.random.RandomState(seed)
    # Uniform-in-disk positions and protocol radius range (metres).
    angle = rng.uniform(0.0, 2.0 * np.pi, (n_cases, n_jammers))
    radius = 1800.0 * xp.sqrt(rng.uniform(0.0, 1.0, (n_cases, n_jammers)))
    x = radius * xp.cos(angle)
    y = radius * xp.sin(angle)
    jammer_r = rng.uniform(1000.0, 1500.0, (n_cases, n_jammers))
    # Process waypoints in one broadcasted block.  Shape is
    # [cases, jammers, waypoints], bounded by the caller's batch size.
    wx = xp.asarray(waypoints[:, 0])
    wy = xp.asarray(waypoints[:, 1])
    seen = xp.zeros((n_cases, n_jammers), dtype=bool)
    for start in range(0, len(waypoints), 256):
        sx, sy = wx[start:start + 256], wy[start:start + 256]
        d2 = (x[:, :, None] - sx[None, None, :]) ** 2 + (y[:, :, None] - sy[None, None, :]) ** 2
        seen |= xp.any(d2 <= jammer_r[:, :, None] ** 2, axis=2)
    return xp.mean(seen, axis=1)


def run_gpu_prescreen(n_cases: int = 100_000, n_jammers: int = 16,
                      waypoint_step: float = 1000.0, seed: int = 20260913,
                      batch_cases: int = 4096) -> dict[str, Any]:
    """Run a large pre-screen with bounded memory and return JSON statistics."""
    if n_cases <= 0 or n_jammers <= 0:
        raise ValueError("n_cases and n_jammers must be positive")
    vals = np.arange(-2500.0, 2500.1, waypoint_step)
    waypoints = np.asarray([(x, y) for y in vals for x in vals
                            if x * x + y * y <= 2500.0 ** 2], dtype=np.float32)
    xp, backend = _backend()
    started = time.perf_counter()
    pieces: list[np.ndarray] = []
    for start in range(0, n_cases, batch_cases):
        count = min(batch_cases, n_cases - start)
        vals_xp = _run_xp(count, n_jammers, waypoints, seed + start, xp)
        pieces.append(np.asarray(vals_xp.get() if hasattr(vals_xp, "get") else vals_xp))
    fractions = np.concatenate(pieces)
    elapsed = time.perf_counter() - started
    result = GPUStats(backend, n_cases, n_jammers, len(waypoints),
                      float(fractions.mean()), float(np.quantile(fractions, .05)),
                      float(np.quantile(fractions, .50)), float(np.quantile(fractions, .95)), elapsed)
    out = asdict(result)
    out["experiment"] = "coverage_prescreen"
    out["gpu_accelerated"] = backend == "cupy-cuda"
    out["note"] = "Pre-screen only; validate selected strategies with b_model.ProtocolSimulator."
    return out


def correctness_check(cases: int = 32, jammers: int = 8, seed: int = 7) -> dict[str, Any]:
    """Verify the vectorized backend against a scalar NumPy implementation."""
    vals = np.arange(-1500.0, 1500.1, 1000.0)
    waypoints = np.asarray([(x, y) for y in vals for x in vals
                            if x * x + y * y <= 1800.0 ** 2], dtype=np.float32)
    a = _run_xp(cases, jammers, waypoints, seed, np)
    rng = np.random.RandomState(seed)
    angle = rng.uniform(0.0, 2.0 * np.pi, (cases, jammers))
    radius = 1800.0 * np.sqrt(rng.uniform(0.0, 1.0, (cases, jammers)))
    x, y = radius * np.cos(angle), radius * np.sin(angle)
    jr = rng.uniform(1000.0, 1500.0, (cases, jammers))
    b = []
    for i in range(cases):
        hit = 0
        for j in range(jammers):
            if any((x[i, j] - wx) ** 2 + (y[i, j] - wy) ** 2 <= jr[i, j] ** 2 for wx, wy in waypoints):
                hit += 1
        b.append(hit / jammers)
    max_err = float(np.max(np.abs(a - np.asarray(b))))
    return {"ok": bool(max_err == 0.0), "max_abs_error": max_err,
            "cases": cases, "jammers": jammers, "waypoints": len(waypoints)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=int, default=100_000)
    ap.add_argument("--jammers", type=int, default=16)
    ap.add_argument("--step", type=float, default=1000.0)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()
    result = correctness_check() if args.check else run_gpu_prescreen(args.cases, args.jammers, args.step)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()

