"""Deterministic Python compatibility implementation of the simulator core.

The supplied executable is a Go/Wails application.  This module intentionally
keeps transport/authentication/upload layers out of scope and implements the
test state machine used by automated robot-api tests.  Time is virtual: tests
never need to sleep and a snapshot can be restored exactly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping, Optional


def normalize_degrees(x: float) -> float:
    x = math.fmod(float(x), 360.0)
    return x + 360.0 if x < 0 else x


def angle_error(a: float, b: float) -> float:
    d = abs(normalize_degrees(a) - normalize_degrees(b))
    return min(d, 360.0 - d)


def quantize_bearing_hundredths(x: float) -> float:
    return math.floor(normalize_degrees(x) * 100.0 + 0.5) / 100.0


def inside_jammer_disk(x: float, y: float, cx: float, cy: float, radius: float) -> bool:
    return math.hypot(float(x) - cx, float(y) - cy) <= radius


def directional_coverage(x: float, y: float, jammer: "Jammer") -> bool:
    dx, dy = float(x) - jammer.x, float(y) - jammer.y
    distance = math.hypot(dx, dy)
    if distance > jammer.radius:
        return False
    if distance == 0 or jammer.beam_width >= 360:
        return True
    # +x is east and bearings increase counter-clockwise.
    bearing = normalize_degrees(math.degrees(math.atan2(dy, dx)))
    return angle_error(bearing, jammer.bearing) <= jammer.beam_width / 2.0


def distance_meters(a: Iterable[float], b: Iterable[float]) -> float:
    ax, ay = a
    bx, by = b
    return math.hypot(float(ax) - float(bx), float(ay) - float(by))


@dataclass(eq=True)
class Jammer:
    kind: str
    x: float
    y: float
    radius: float
    bearing: float = 0.0
    beam_width: float = 360.0
    channel: int = 0
    id: str = ""

    def __post_init__(self) -> None:
        self.kind = str(self.kind).lower()
        if not self.id:
            raw = f"{self.kind}|{self.x:.6f}|{self.y:.6f}|{self.radius:.6f}|{self.channel}".encode()
            self.id = "jammer-" + hashlib.sha256(raw).hexdigest()[:8]


@dataclass
class Scenario:
    version: str
    seed: int
    width: float
    height: float
    jammers: list[Jammer]
    target_x: Optional[float] = None
    target_y: Optional[float] = None
    target_radius: float = 20.0

    @property
    def target(self) -> tuple[float, float]:
        return (self.width / 2.0 if self.target_x is None else self.target_x,
                self.height / 2.0 if self.target_y is None else self.target_y)

    def validate(self) -> None:
        if self.version != "1":
            raise ValueError("unsupported scenario version")
        if self.width <= 0 or self.height <= 0 or not self.jammers:
            raise ValueError("invalid scenario dimensions or empty jammer list")
        tx, ty = self.target
        if not (0 <= tx <= self.width and 0 <= ty <= self.height and self.target_radius >= 0):
            raise ValueError("invalid target geometry")
        for j in self.jammers:
            if j.radius <= 0 or not (0 <= j.x <= self.width and 0 <= j.y <= self.height):
                raise ValueError("invalid jammer geometry")
            if j.kind not in ("directional", "omnidirectional"):
                raise ValueError("unsupported jammer kind")
            if j.kind == "directional" and not (0 < j.beam_width <= 360):
                raise ValueError("invalid directional beam width")

    def covered(self, x: float, y: float, channel: int = 0) -> bool:
        return bool(self.covering(x, y, channel))

    def covering(self, x: float, y: float, channel: int = 0) -> list[Jammer]:
        out: list[Jammer] = []
        for j in self.jammers:
            if channel and j.channel not in (0, channel):
                continue
            hit = (directional_coverage(x, y, j) if j.kind == "directional"
                   else inside_jammer_disk(x, y, j.x, j.y, j.radius))
            if hit:
                out.append(j)
        return out

    def optical_targets(self, x: float, y: float, channel: int = 0) -> list[Jammer]:
        """Return sources within optical range, independent of RF direction."""
        out = []
        for j in self.jammers:
            if channel and j.channel not in (0, channel):
                continue
            if inside_jammer_disk(x, y, j.x, j.y, 20.0):
                out.append(j)
        return out


@dataclass
class GenerationRules:
    # The executable's validation strings require 10..16 generated jammers.
    min_jammers: int = 10
    max_jammers: int = 16
    edge_margin: float = 50.0
    min_radius: float = 40.0
    max_radius: float = 180.0
    directional_probability: float = 0.35


@dataclass
class SimulationRules:
    countdown_ms: int = 5000
    entry_window_ms: int = 25 * 60 * 1000
    program_run_limit_ms: int = 20 * 60 * 1000
    virtual_time_limit_us: int = 100 * 60 * 60 * 1_000_000
    movement_speed_mps: float = 5.0
    measure_duration_ms: int = 5000
    clear_duration_ms: int = 5000
    clear_failure_duration_ms: int = 3000
    channel_switch_duration_ms: int = 1000
    target_entry_radius: float = 20.0

    def __post_init__(self) -> None:
        integer_fields = ("countdown_ms", "entry_window_ms", "program_run_limit_ms",
                          "virtual_time_limit_us", "measure_duration_ms",
                          "clear_duration_ms", "clear_failure_duration_ms",
                          "channel_switch_duration_ms")
        for name in integer_fields:
            value = int(getattr(self, name))
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
            setattr(self, name, value)
        if self.movement_speed_mps <= 0:
            raise ValueError("movement_speed_mps must be positive")
        if self.target_entry_radius < 0:
            raise ValueError("target_entry_radius must be non-negative")

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]) -> "SimulationRules":
        """Load test timing overrides without requiring callers to know defaults."""
        data = dict(values)
        # Friendly second-based names are useful in short automation fixtures.
        if "countdown_seconds" in data and "countdown_ms" not in data:
            data["countdown_ms"] = round(float(data.pop("countdown_seconds")) * 1000)
        if "entry_window_seconds" in data and "entry_window_ms" not in data:
            data["entry_window_ms"] = round(float(data.pop("entry_window_seconds")) * 1000)
        if "program_run_limit_seconds" in data and "program_run_limit_ms" not in data:
            data["program_run_limit_ms"] = round(float(data.pop("program_run_limit_seconds")) * 1000)
        if "virtual_time_limit_seconds" in data and "virtual_time_limit_us" not in data:
            data["virtual_time_limit_us"] = round(float(data.pop("virtual_time_limit_seconds")) * 1_000_000)
        allowed = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in allowed})

    @classmethod
    def fast_test(cls) -> "SimulationRules":
        """Convenient deterministic profile for unit/API automation."""
        return cls(countdown_ms=0, entry_window_ms=10_000,
                   program_run_limit_ms=10_000, virtual_time_limit_us=30_000_000,
                   movement_speed_mps=10.0, measure_duration_ms=0,
                   clear_duration_ms=0, channel_switch_duration_ms=0)


def generate_practice(seed: int, width: float = 1000.0, height: float = 1000.0,
                      count: Optional[int] = None,
                      rules: Optional[GenerationRules] = None) -> Scenario:
    rules = rules or GenerationRules()
    rng = random.Random(int(seed) & ((1 << 64) - 1))
    if count is None:
        count = rng.randint(rules.min_jammers, rules.max_jammers)
    if count < 1:
        raise ValueError("count must be positive")
    jammers: list[Jammer] = []
    for i in range(count):
        kind = "directional" if rng.random() < rules.directional_probability else "omnidirectional"
        x = round(rng.uniform(rules.edge_margin, width - rules.edge_margin), 2)
        y = round(rng.uniform(rules.edge_margin, height - rules.edge_margin), 2)
        radius = round(rng.uniform(rules.min_radius, rules.max_radius), 2)
        bearing = round(rng.uniform(0, 360), 2) if kind == "directional" else 0.0
        beam = round(rng.uniform(30, 120), 2) if kind == "directional" else 360.0
        jammers.append(Jammer(kind, x, y, radius, bearing, beam, rng.randint(1, 4), f"jammer-{i+1}"))
    s = Scenario("1", int(seed), width, height, jammers, width / 2, height / 2)
    s.validate()
    return s


@dataclass
class EnterAction:
    x: float
    y: float


@dataclass
class MoveToAction:
    x: float
    y: float


@dataclass
class MeasureAction:
    channel: Optional[int] = None


@dataclass
class ClearAction:
    jammer_id: Optional[str] = None
    channel: Optional[int] = None


@dataclass
class ExitAction:
    pass


@dataclass
class AdvanceAction:
    milliseconds: int


@dataclass
class SimState:
    phase: str = "preparing"
    virtual_time_us: int = 0
    countdown_remaining_ms: int = 5000
    window_remaining_ms: int = 1_500_000
    program_remaining_ms: int = 0
    position: tuple[float, float] = (0.0, 0.0)
    target_position: tuple[float, float] = (0.0, 0.0)
    # The protocol specifies that the measurement receiver starts on channel 1.
    channel: int = 1
    entered: bool = False
    cleared_jammers: list[str] = field(default_factory=list)
    measurements: list[dict[str, Any]] = field(default_factory=list)
    action_log: list[dict[str, Any]] = field(default_factory=list)
    channel_switch_count: int = 0
    clear_failure_count: int = 0
    accepted_measure_count: int = 0
    move_count: int = 0
    end_reason: str = ""
    last_error: str = ""


@dataclass
class Result:
    accepted: bool
    outcome: str
    reason: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    state: Optional[SimState] = None

    @property
    def ok(self) -> bool:
        return self.accepted

    def to_dict(self) -> dict[str, Any]:
        d = {"accepted": self.accepted, "ok": self.accepted, "outcome": self.outcome,
             "reason": self.reason, "data": self.data}
        if self.state is not None:
            d["state"] = asdict(self.state)
        return d


class Engine:
    def __init__(self, scenario: Scenario, rules: Optional[SimulationRules] = None,
                 state: Optional[SimState] = None,
                 enforce_program_limit: bool = True):
        scenario.validate()
        self.scenario = scenario
        if isinstance(rules, Mapping):
            rule_values = dict(rules)
            rule_values.setdefault("target_entry_radius", scenario.target_radius)
            rules = SimulationRules.from_dict(rule_values)
        self.rules = rules or SimulationRules(target_entry_radius=scenario.target_radius)
        # The standalone compatibility engine historically used
        # ``program_remaining_ms`` as a virtual test budget because it is
        # convenient for deterministic unit tests.  The real HTTP protocol,
        # however, defines the 20-minute program limit on a wall clock and the
        # virtual clock limit separately.  The HTTP adapter passes
        # ``enforce_program_limit=False`` and enforces that wall-clock gate
        # itself.  Keeping the switch explicit preserves old in-process test
        # fixtures while making protocol execution faithful.
        self.enforce_program_limit = bool(enforce_program_limit)
        self.state = state or SimState(target_position=scenario.target)
        # Snapshots produced by an older revision used zero as an
        # "uninitialised" channel.  Restore those snapshots to the protocol's
        # actual initial receiver channel rather than charging a spurious
        # switch on the first /measure.
        if self.state.channel == 0:
            self.state.channel = 1
        if state is None:
            self.state.countdown_remaining_ms = self.rules.countdown_ms
            self.state.window_remaining_ms = self.rules.entry_window_ms
        self._sync_phase()

    @classmethod
    def new(cls, scenario: Scenario, rules: Optional[SimulationRules] = None,
            enforce_program_limit: bool = True) -> "Engine":
        return cls(scenario, rules, enforce_program_limit=enforce_program_limit)

    @classmethod
    def from_state(cls, scenario: Scenario, state: SimState | Mapping[str, Any],
                   rules: Optional[SimulationRules] = None,
                   enforce_program_limit: bool = True) -> "Engine":
        if isinstance(state, Mapping):
            d = dict(state)
            for key in ("position", "target_position"):
                if key in d:
                    d[key] = tuple(d[key])
            state = SimState(**d)
        return cls(scenario, rules, state, enforce_program_limit=enforce_program_limit)

    def snapshot(self) -> SimState:
        d = asdict(self.state)
        d["position"] = tuple(d["position"])
        d["target_position"] = tuple(d["target_position"])
        return SimState(**d)

    def _sync_phase(self) -> None:
        if self.state.phase in ("ended", "ending"):
            return
        if self.state.countdown_remaining_ms > 0:
            self.state.phase = "countdown" if self.state.virtual_time_us else "preparing"
        elif not self.state.entered:
            self.state.phase = "waiting_enter"
        else:
            self.state.phase = "running"

    def _finish(self, reason: str) -> None:
        if self.state.phase == "ended":
            return
        self.state.end_reason = reason
        self.state.phase = "ended"

    def _add_virtual_ms(self, ms: int, run_time: bool = False) -> None:
        if ms < 0:
            raise ValueError("time increment must be non-negative")
        remaining = int(ms)
        if self.state.countdown_remaining_ms:
            used = min(remaining, self.state.countdown_remaining_ms)
            self.state.countdown_remaining_ms -= used
            remaining -= used
            self.state.virtual_time_us += used * 1000
            self._sync_phase()
        if remaining and not self.state.entered:
            used = min(remaining, self.state.window_remaining_ms)
            self.state.window_remaining_ms -= used
            self.state.virtual_time_us += used * 1000
            remaining -= used
            if self.state.window_remaining_ms == 0:
                self._finish("window_timeout_before_enter")
        if remaining and self.state.entered and self.state.phase != "ended" and self.enforce_program_limit:
            self.state.program_remaining_ms += remaining
            self.state.virtual_time_us += remaining * 1000
            if self.state.program_remaining_ms >= self.rules.program_run_limit_ms:
                self.state.program_remaining_ms = self.rules.program_run_limit_ms
                self._finish("program_timeout")
        elif remaining and self.state.entered and self.state.phase != "ended":
            # In protocol mode this is purely virtual activity time.  The
            # real program deadline is checked by the transport/service clock.
            self.state.virtual_time_us += remaining * 1000
        if self.state.virtual_time_us >= self.rules.virtual_time_limit_us and self.state.phase != "ended":
            self._finish("virtual_timeout")
        self._sync_phase()

    def advance(self, milliseconds: int) -> Result:
        try:
            self._add_virtual_ms(int(milliseconds))
            self.state.action_log.append({"action": "advance", "milliseconds": int(milliseconds),
                                          "virtual_time_us": self.state.virtual_time_us})
            return self._result(True, "advanced", data={"milliseconds": int(milliseconds)})
        except Exception as exc:
            return self._reject(str(exc))

    def _result(self, accepted: bool, outcome: str, reason: str = "", data: Optional[dict[str, Any]] = None) -> Result:
        return Result(accepted, outcome, reason, data or {}, self.snapshot())

    def _reject(self, reason: str, outcome: str = "rejected") -> Result:
        self.state.last_error = reason
        return self._result(False, outcome, reason)

    def _valid_position(self, x: float, y: float) -> bool:
        # /measure and /clear may use points outside the target arena; the
        # protocol only limits each coordinate to +/-2,000,000 m.  /enter
        # applies the target-region check separately below.
        return (math.isfinite(x) and math.isfinite(y) and
                abs(float(x)) <= 2_000_000.0 and abs(float(y)) <= 2_000_000.0)

    @staticmethod
    def _valid_channel(channel: Any) -> bool:
        return (isinstance(channel, (int, float)) and not isinstance(channel, bool)
                and math.isfinite(float(channel)) and float(channel).is_integer()
                and 1 <= int(channel) <= 20)

    def _request_fits(self, duration_ms: int) -> tuple[bool, str]:
        """Check whether a complete atomic action fits before a deadline."""
        if duration_ms < 0:
            return False, "invalid_duration"
        if self.state.virtual_time_us + int(duration_ms) * 1000 > self.rules.virtual_time_limit_us:
            return False, "virtual_timeout"
        if (self.enforce_program_limit and
                self.state.program_remaining_ms + int(duration_ms) > self.rules.program_run_limit_ms):
            return False, "program_timeout"
        return True, ""

    def _timeout_result(self, action: str, reason: str, **data: Any) -> Result:
        self._finish(reason)
        event = {"action": action, "result": "timeout", "reason": reason,
                 "virtual_time_us": self.state.virtual_time_us, **data}
        self.state.action_log.append(event)
        return self._result(False, "timeout", reason, data)

    def enter(self, x: float, y: float) -> Result:
        if self.state.phase != "waiting_enter":
            return self._reject(f"invalid phase: {self.state.phase}")
        if not self._valid_position(x, y):
            return self._reject("invalid_coordinate")
        if distance_meters((x, y), self.scenario.target) > self.rules.target_entry_radius:
            return self._reject("outside_target_region")
        self.state.position = (float(x), float(y))
        self.state.entered = True
        self.state.phase = "running"
        self.state.action_log.append({"action": "enter", "position": self.state.position,
                                      "virtual_time_us": self.state.virtual_time_us})
        return self._result(True, "entered", data={"position": self.state.position})

    def protocol_enter(self) -> Result:
        """Enter via the four-command HTTP protocol at the fixed origin.

        The in-process compatibility API retains ``enter(x, y)`` for legacy
        fixtures, while the official protocol's /enter has no position fields
        and always starts at (0, 0).
        """
        if self.state.phase != "waiting_enter":
            return self._reject(f"invalid phase: {self.state.phase}")
        self.state.position = (0.0, 0.0)
        self.state.entered = True
        self.state.phase = "running"
        self.state.action_log.append({"action": "enter", "position": self.state.position,
                                      "virtual_time_us": self.state.virtual_time_us})
        return self._result(True, "entered", data={"position": self.state.position})

    def move_to(self, x: float, y: float) -> Result:
        if self.state.phase != "running":
            return self._reject(f"invalid phase: {self.state.phase}")
        if not self._valid_position(x, y):
            return self._reject("invalid_coordinate")
        dist = distance_meters(self.state.position, (x, y))
        ms = int(math.ceil(dist / max(self.rules.movement_speed_mps, 1e-9) * 1000.0))
        fits, reason = self._request_fits(ms)
        if not fits:
            return self._timeout_result("move", reason, position=(float(x), float(y)),
                                        distance_m=dist, duration_ms=ms)
        self.state.position = (float(x), float(y))
        self.state.move_count += 1
        self._add_virtual_ms(ms, run_time=True)
        self.state.action_log.append({"action": "move", "position": self.state.position,
                                      "distance_m": dist, "duration_ms": ms,
                                      "virtual_time_us": self.state.virtual_time_us})
        if self.state.phase == "ended":
            return self._result(False, "timeout", self.state.end_reason, {"distance_m": dist, "duration_ms": ms})
        return self._result(True, "moved", data={"distance_m": dist, "duration_ms": ms})

    def measure_at(self, x: float, y: float, channel: int) -> Result:
        """Execute one complete protocol ``/measure`` atomically.

        Movement, receiver switching, and the five-second measurement are one
        request at the wire level.  The old implementation exposed them as
        separate internal operations, which could mutate position/channel
        even when the request crossed a deadline.  This method computes the
        result at the destination, preflights the full duration, then commits
        all state together.
        """
        if self.state.phase != "running":
            return self._reject(f"invalid phase: {self.state.phase}")
        if not self._valid_position(x, y):
            return self._reject("invalid_coordinate")
        if not self._valid_channel(channel):
            return self._reject("invalid_channel")
        x, y, channel = float(x), float(y), int(channel)
        destination = (x, y)
        dist = distance_meters(self.state.position, destination)
        move_ms = int(math.ceil(dist / max(self.rules.movement_speed_mps, 1e-9) * 1000.0))
        switch_ms = self.rules.channel_switch_duration_ms if channel != self.state.channel else 0
        total_ms = move_ms + switch_ms + self.rules.measure_duration_ms
        hits = [j for j in self.scenario.covering(x, y, channel)
                if j.id not in self.state.cleared_jammers]
        near = bool(hits and any(distance_meters(destination, (j.x, j.y)) <= 5.0 for j in hits))
        fits, reason = self._request_fits(total_ms)
        if not fits:
            return self._timeout_result("measure", reason, position=destination,
                                        channel=channel, distance_m=dist,
                                        duration_ms=total_ms)

        self.state.position = destination
        self.state.move_count += int(dist > 0.0)
        if switch_ms:
            self.state.channel_switch_count += 1
        self.state.channel = channel
        self._add_virtual_ms(total_ms, run_time=True)
        accepted = bool(hits)
        if accepted:
            self.state.accepted_measure_count += 1
        record: dict[str, Any] = {
            "position": self.state.position, "channel": channel,
            "jammer_ids": [j.id for j in hits], "accepted": accepted,
            "measure_result": ("near" if near else "direction") if accepted else "no_signal",
            "distance_m": dist, "move_duration_ms": move_ms,
            "switch_duration_ms": switch_ms,
            "measure_duration_ms": self.rules.measure_duration_ms,
            "duration_ms": total_ms,
            "virtual_time_us": self.state.virtual_time_us,
        }
        if accepted and not near:
            j = hits[0]
            record["svd_deg"] = quantize_bearing_hundredths(
                math.degrees(math.atan2(j.y - y, j.x - x)))
        self.state.measurements.append(record)
        self.state.action_log.append({"action": "measure", **record})
        return self._result(accepted, "measured" if accepted else "no_target_in_range",
                            "" if accepted else "no_target_in_range", record)

    def measure(self, channel: Optional[int] = None) -> Result:
        active_channel = self.state.channel if channel is None else channel
        return self.measure_at(self.state.position[0], self.state.position[1], active_channel)

    def clear_at(self, x: float, y: float, channel: int,
                 jammer_id: Optional[str] = None) -> Result:
        """Execute one complete protocol ``/clear`` atomically."""
        if self.state.phase != "running":
            return self._reject(f"invalid phase: {self.state.phase}")
        if not self._valid_position(x, y):
            return self._reject("invalid_coordinate")
        if not self._valid_channel(channel):
            return self._reject("invalid_channel")
        x, y, channel = float(x), float(y), int(channel)
        destination = (x, y)
        dist = distance_meters(self.state.position, destination)
        move_ms = int(math.ceil(dist / max(self.rules.movement_speed_mps, 1e-9) * 1000.0))
        hits = self.scenario.optical_targets(x, y, channel)
        if jammer_id:
            hits = [j for j in hits if j.id == jammer_id]
        hits = [j for j in hits if j.id not in self.state.cleared_jammers]
        success = bool(hits)
        action_ms = self.rules.clear_duration_ms if success else self.rules.clear_failure_duration_ms
        total_ms = move_ms + action_ms
        fits, reason = self._request_fits(total_ms)
        if not fits:
            return self._timeout_result("clear", reason, position=destination,
                                        channel=channel, distance_m=dist,
                                        duration_ms=total_ms)

        self.state.position = destination
        self.state.move_count += int(dist > 0.0)
        self._add_virtual_ms(total_ms, run_time=True)
        event: dict[str, Any] = {
            "action": "clear", "position": self.state.position,
            "channel": channel, "distance_m": dist,
            "move_duration_ms": move_ms, "clear_duration_ms": action_ms,
            "duration_ms": total_ms,
            "result": "success" if success else "no_target_in_range",
            "virtual_time_us": self.state.virtual_time_us,
        }
        if not success:
            self.state.clear_failure_count += 1
            self.state.action_log.append(event)
            return self._reject("clear_failed", "clear_rejected")
        chosen = hits[0]
        self.state.cleared_jammers.append(chosen.id)
        event["jammer_id"] = chosen.id
        event["cleared_count"] = len(self.state.cleared_jammers)
        self.state.action_log.append(event)
        return self._result(True, "cleared", data={"jammer_id": chosen.id,
                                                    "cleared_count": len(self.state.cleared_jammers),
                                                    "clear_result": "success"})

    def clear(self, jammer_id: Optional[str] = None, channel: Optional[int] = None) -> Result:
        target_channel = self.state.channel if channel is None else channel
        return self.clear_at(self.state.position[0], self.state.position[1],
                             target_channel, jammer_id=jammer_id)

    def exit(self) -> Result:
        if self.state.phase not in ("running", "waiting_enter"):
            return self._reject(f"invalid phase: {self.state.phase}")
        self._finish("user_exit")
        self.state.action_log.append({"action": "exit", "result": "user_exit",
                                      "virtual_time_us": self.state.virtual_time_us})
        return self._result(True, "finished", data={"end_reason": self.state.end_reason})

    def apply(self, action: Any) -> Result:
        if isinstance(action, Mapping):
            name = str(action.get("action", action.get("type", ""))).lower()
            if name in ("enter", "/enter"):
                action = EnterAction(float(action["x"]), float(action["y"]))
            elif name in ("move", "move_to", "/move"):
                action = MoveToAction(float(action["x"]), float(action["y"]))
            elif name in ("measure", "/measure"):
                action = MeasureAction(action.get("channel"))
            elif name in ("clear", "/clear"):
                action = ClearAction(action.get("jammer_id"), action.get("channel"))
            elif name in ("exit", "/exit"):
                action = ExitAction()
            elif name in ("advance", "tick"):
                action = AdvanceAction(int(action.get("milliseconds", action.get("ms", 0))))
            else:
                return self._reject("unknown_action")
        if isinstance(action, EnterAction): return self.enter(action.x, action.y)
        if isinstance(action, MoveToAction): return self.move_to(action.x, action.y)
        if isinstance(action, MeasureAction): return self.measure(action.channel)
        if isinstance(action, ClearAction): return self.clear(action.jammer_id, action.channel)
        if isinstance(action, ExitAction): return self.exit()
        if isinstance(action, AdvanceAction): return self.advance(action.milliseconds)
        return self._reject("unknown_action")

    def summary(self) -> dict[str, Any]:
        total = len(self.scenario.jammers)
        return {"phase": self.state.phase, "end_reason": self.state.end_reason,
                "entered": self.state.entered, "cleared_jammer_count": len(self.state.cleared_jammers),
                "jammer_count": total, "accepted_measure_count": self.state.accepted_measure_count,
                "virtual_time_us": self.state.virtual_time_us,
                "action_count": len(self.state.action_log),
                "program_duration_ms": self.state.program_remaining_ms,
                "channel_switch_count": self.state.channel_switch_count,
                "clear_failure_count": self.state.clear_failure_count,
                "cleared_all": len(self.state.cleared_jammers) == total}

    def done(self) -> bool:
        return self.state.phase == "ended"


class Session:
    """Small in-process equivalent of testsession.Session."""
    def __init__(self, scenario: Scenario, rules: Optional[SimulationRules] = None,
                 engine: Optional[Engine] = None):
        self.engine = engine or Engine(scenario, rules)
        self.active = True

    @classmethod
    def new(cls, scenario: Scenario, rules: Optional[SimulationRules] = None) -> "Session":
        return cls(scenario, rules)

    @classmethod
    def from_state(cls, scenario: Scenario, snapshot: Mapping[str, Any], rules: Optional[SimulationRules] = None) -> "Session":
        eng = Engine.from_state(scenario, snapshot.get("engine", snapshot), rules)
        obj = cls(scenario, rules, eng)
        obj.active = bool(snapshot.get("active", eng.state.phase != "ended"))
        return obj

    def admit(self) -> Result:
        return self.engine._result(True, "admitted")

    def execute(self, action: Any) -> Result:
        result = self.engine.apply(action)
        if self.engine.state.phase == "ended":
            self.active = False
        return result

    def observe(self) -> dict[str, Any]:
        return self.snapshot()

    def manual_abort(self) -> Result:
        reason = "manual_abort_running" if self.engine.state.entered else "manual_abort_before_enter"
        self.engine._finish(reason)
        self.active = False
        return self.engine._result(True, "aborted", data={"end_reason": reason})

    def finish_without_action(self) -> Result:
        self.engine._finish("user_exit" if self.engine.state.entered else "manual_abort_before_enter")
        self.active = False
        return self.engine._result(True, "finished")

    def snapshot(self) -> dict[str, Any]:
        return {"active": self.active and self.engine.state.phase != "ended",
                "done": self.done(), "engine": asdict(self.engine.state),
                "summary": self.engine.summary()}

    def done(self) -> bool:
        return self.engine.state.phase == "ended"

    def export_reports(self, output_dir: str, prefix: str = "practice-p1-1-local") -> dict[str, str]:
        """Write source-compatible *field names* for local automation reports.

        These are intentionally plaintext test artifacts.  Official encrypted
        logs additionally require server-controlled signing/wrapping keys.
        """
        import os
        os.makedirs(output_dir, exist_ok=True)
        summary = self.engine.summary()
        result_path = os.path.join(output_dir, prefix + ".result.json")
        psum_path = os.path.join(output_dir, prefix + ".psum")
        jlog_path = os.path.join(output_dir, prefix + ".jlog")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2); f.write("\n")
        with open(psum_path, "w", encoding="utf-8") as f:
            json.dump({"schema_version": "practice-summary-v1", **summary}, f,
                      ensure_ascii=False, indent=2); f.write("\n")
        with open(jlog_path, "w", encoding="utf-8") as f:
            for i, event in enumerate(self.engine.state.action_log, 1):
                f.write(json.dumps({"seq": i, **event},
                                   ensure_ascii=False) + "\n")
        return {"result": result_path, "summary": psum_path, "journal": jlog_path}

    def export_test_envelope(self, output_dir: str, *, rsa_public_pem: bytes,
                             ed25519_private_raw: bytes,
                             prefix: str = "practice-p1-1-local") -> str:
        """Export a locally verifiable encrypted practice summary.

        This mirrors the recovered package algorithm family, but deliberately
        does not claim official upload compatibility.  See ``jammers_crypto``.
        """
        from jammers_crypto import encrypt_envelope
        import os
        os.makedirs(output_dir, exist_ok=True)
        summary = {"schema_version": "practice-summary-v1", **self.engine.summary()}
        payload = (json.dumps(summary, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        path = os.path.join(output_dir, prefix + ".local-envelope.json")
        with open(path, "wb") as fh:
            fh.write(encrypt_envelope(payload, rsa_public_pem=rsa_public_pem,
                                      ed25519_private_raw=ed25519_private_raw,
                                      package_type="practice-summary-v1"))
        return path


# Naming aliases mirror the recovered Go constructors and make the module
# convenient to call from thin compatibility adapters.
def NewEngine(scenario: Scenario, rules: Optional[SimulationRules] = None) -> Engine:
    return Engine(scenario, rules)


def NewEngineFromState(scenario: Scenario, state: SimState | Mapping[str, Any],
                       rules: Optional[SimulationRules] = None) -> Engine:
    return Engine.from_state(scenario, state, rules)


def NewSession(scenario: Scenario, rules: Optional[SimulationRules] = None) -> Session:
    return Session(scenario, rules)


def scenario_from_dict(obj: Mapping[str, Any]) -> Scenario:
    d = dict(obj)
    d["jammers"] = [Jammer(**j) if not isinstance(j, Jammer) else j for j in d.get("jammers", [])]
    s = Scenario(**d)
    s.validate()
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--count", type=int)
    ap.add_argument("--out")
    args = ap.parse_args()
    obj = asdict(generate_practice(args.seed, count=args.count))
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
