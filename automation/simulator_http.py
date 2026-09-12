"""Local HTTP+JSON adapter for the reversed four-command simulator protocol.

This is intended for black-box automation tests.  It is deterministic and
offline, and deliberately omits authentication, online time checks and upload
queues.  The adapter enforces the protocol's request shape, idempotency and
the four paths while delegating timing and geometry to ``jammers_simulator``.
"""
from __future__ import annotations

import json
import math
import threading
import time
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from jammers_simulator import Engine, Scenario, SimulationRules


MAX_COORD = 2_000_000.0
MAX_BODY_BYTES = 65_536
MAX_JSON_DEPTH = 16
PATHS = {"/enter", "/measure", "/clear", "/exit"}


class _DuplicateJSONKey(ValueError):
    pass


def _pairs_no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJSONKey(key)
        result[key] = value
    return result


def _json_depth(value: Any, depth: int = 1) -> int:
    if isinstance(value, dict):
        children = list(value.values())
    elif isinstance(value, list):
        children = list(value)
    else:
        return depth
    if not children:
        return depth
    return max(_json_depth(item, depth + 1) for item in children)


class SimulatorService:
    def __init__(self, scenario: Scenario, robot_id: str = "local",
                 rules: SimulationRules | None = None,
                 clock: Callable[[], float] | None = None):
        # Wall-clock program deadlines are handled here; the core engine only
        # advances virtual action time and enforces the independent 100-hour
        # virtual limit.
        self.engine = Engine.new(scenario, rules, enforce_program_limit=False)
        self.robot_id = robot_id
        self.arena_id = "default"
        self.requests: dict[str, tuple[str, bytes, bytes]] = {}
        self._clock = clock or time.monotonic
        self._wall_started = float(self._clock())
        self._ready_at = self._wall_started + self.engine.rules.countdown_ms / 1000.0
        self._entry_deadline = self._ready_at + self.engine.rules.entry_window_ms / 1000.0
        self._program_deadline: float | None = None
        self._session_started_at: float | None = None
        self._lock = threading.RLock()

    def _base(self, accepted: bool = True) -> dict[str, Any]:
        # The official protocol reports zero for rejected business requests;
        # callers must retain the last accepted timestamp themselves.
        return {"accepted": bool(accepted),
                "real_timestamp_ms": int(time.time() * 1000),
                "virtual_time_s": (self.engine.state.virtual_time_us / 1_000_000.0
                                    if accepted else 0)}

    def error_response(self, error: str) -> dict[str, Any]:
        out = self._base(False)
        out["error"] = error
        return out

    def _sync_wall_clock(self) -> None:
        """Synchronize real-time gates without advancing virtual time.

        The executable has two clocks: a preparation/entry wall-clock window
        and a virtual action clock.  The old adapter only modeled the latter,
        which made ``remaining_real_duration_s`` incorrectly constant.  This
        method is deliberately injectable-clock based so tests can advance
        time deterministically without sleeping.
        """
        now = float(self._clock())
        state = self.engine.state
        if state.phase in ("ended", "ending"):
            return
        if not state.entered:
            if now < self._ready_at:
                state.countdown_remaining_ms = max(0, int(math.ceil((self._ready_at - now) * 1000)))
                state.phase = "countdown" if state.countdown_remaining_ms else "preparing"
                return
            state.countdown_remaining_ms = 0
            if now >= self._entry_deadline:
                state.window_remaining_ms = 0
                self.engine._finish("window_timeout_before_enter")
                return
            state.window_remaining_ms = max(0, int(math.ceil((self._entry_deadline - now) * 1000)))
            state.phase = "waiting_enter"
            return
        if self._program_deadline is None:
            return
        if now >= self._program_deadline:
            state.program_remaining_ms = self.engine.rules.program_run_limit_ms
            # The earlier of the entry-window and post-enter program deadline
            # determines the reason; this matters when entering late.
            if self._program_deadline >= self._entry_deadline:
                self.engine._finish("window_timeout")
            else:
                self.engine._finish("program_timeout")
        else:
            elapsed = max(0.0, now - (self._session_started_at or now))
            state.program_remaining_ms = min(
                self.engine.rules.program_run_limit_ms,
                int(elapsed * 1000.0),
            )

    @staticmethod
    def _is_integer_number(value: Any) -> bool:
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(float(value)) and float(value).is_integer())

    @staticmethod
    def _valid_identifier(value: Any, maximum: int) -> bool:
        if not isinstance(value, str) or not value:
            return False
        if len(value.encode("utf-8")) > maximum:
            return False
        # Reject C0 controls and Unicode format controls.  These can make
        # request logs ambiguous and are explicitly disallowed by the guide.
        return all(ord(ch) >= 0x20 and not (0x7f <= ord(ch) <= 0x9f)
                   and unicodedata.category(ch) != "Cf"
                   for ch in value)

    @staticmethod
    def _valid_robot_identifier(value: Any) -> bool:
        return SimulatorService._valid_identifier(value, 64)

    def _validate_common(self, body: dict[str, Any]) -> str | None:
        required = {"arena_id", "robot_id", "request_id"}
        if not required.issubset(body):
            return "missing_field"
        if set(body) - {"arena_id", "robot_id", "request_id", "position", "channel"}:
            return "unknown_field"
        arena_id = body.get("arena_id")
        if not isinstance(arena_id, str) or not arena_id.isascii():
            return "invalid_arena_id"
        if arena_id != self.arena_id:
            return "identity_mismatch"
        robot_id = body.get("robot_id")
        if not self._valid_robot_identifier(robot_id):
            return "invalid_robot_id"
        if robot_id != self.robot_id:
            return "identity_mismatch"
        rid = body.get("request_id")
        if not self._valid_identifier(rid, 128):
            return "invalid_request_id"
        return None

    def _validate_action(self, path: str, body: dict[str, Any]) -> str | None:
        err = self._validate_common(body)
        if err:
            return err
        if path in ("/enter", "/exit") and set(body) != {"arena_id", "robot_id", "request_id"}:
            return "unknown_field"
        if path in ("/measure", "/clear"):
            if "position" not in body or "channel" not in body:
                return "missing_field"
            p = body.get("position")
            c = body.get("channel")
            if not isinstance(p, dict):
                return "invalid_position"
            if set(p) - {"x", "y"}:
                return "unknown_field"
            if not {"x", "y"}.issubset(p):
                return "missing_field"
            if not all(isinstance(p[k], (int, float)) and not isinstance(p[k], bool)
                       and math.isfinite(float(p[k])) and abs(float(p[k])) <= MAX_COORD
                       for k in ("x", "y")):
                return "invalid_coordinate"
            if not self._is_integer_number(c) or not 1 <= int(c) <= 20:
                return "invalid_channel"
        return None

    def handle(self, path: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        with self._lock:
            if path not in PATHS:
                return 404, {"accepted": False, "error": "not_found"}
            err = self._validate_action(path, body)
            if err:
                if err in ("invalid_position", "invalid_coordinate", "invalid_channel",
                           "invalid_request_id", "invalid_robot_id", "invalid_arena_id",
                           "missing_field"):
                    return 400, {"accepted": False, "error": err}
                out = self.error_response(err)
                return 200, out
            rid = body["request_id"]
            canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            prior = self.requests.get(rid)
            if prior:
                if prior[0] != path or prior[1] != canonical:
                    out = self._base(False); out["error"] = "request_id_conflict"
                    return 409, out
                return 200, json.loads(prior[2].decode())

            self._sync_wall_clock()
            if path == "/enter":
                result = self.engine.protocol_enter()
                out = self._base(result.accepted)
                if result.accepted:
                    now = float(self._clock())
                    self._session_started_at = now
                    self._program_deadline = min(self._entry_deadline,
                                                 now + self.engine.rules.program_run_limit_ms / 1000.0)
                    remaining = max(0, int(math.floor(self._program_deadline - now)))
                    out.update({"max_virtual_duration_s": self.engine.rules.virtual_time_limit_us / 1e6,
                                "max_real_duration_s": self.engine.rules.program_run_limit_ms / 1000.0,
                                "remaining_real_duration_s": remaining})
            elif path == "/measure":
                if self.engine.state.phase != "running":
                    result = self.engine._reject(f"invalid phase: {self.engine.state.phase}")
                    out = self._base(False)
                else:
                        result = self.engine.measure_at(
                            float(body["position"]["x"]),
                            float(body["position"]["y"]),
                            int(body["channel"]),
                        )
                        if result.outcome == "timeout":
                            out = self._base(False)
                        else:
                            # A syntactically valid protocol measurement is
                            # accepted even when the radio reports no_signal.
                            out = self._base(True)
                            out["measure_result"] = result.data.get("measure_result", "no_signal")
                            if "svd_deg" in result.data:
                                out["svd_deg"] = result.data["svd_deg"]
            elif path == "/clear":
                if self.engine.state.phase != "running":
                    result = self.engine._reject(f"invalid phase: {self.engine.state.phase}")
                    out = self._base(False)
                else:
                        result = self.engine.clear_at(
                            float(body["position"]["x"]),
                            float(body["position"]["y"]),
                            int(body["channel"]),
                        )
                        if result.outcome == "timeout":
                            out = self._base(False)
                        else:
                            out = self._base(True)
                            out["clear_result"] = "success" if result.accepted else "no_target_in_range"
            else:
                result = self.engine.exit()
                out = self._base(result.accepted)
                if result.accepted:
                    out["exit_reason"] = "user_exit"
            # Only an accepted wire-level action consumes its idempotency key.
            # This lets a client retry the same request after a transient
            # state rejection (countdown, not-entered, or already ended), as
            # specified by the protocol.  A clear miss is accepted at the
            # protocol layer and is therefore cached by the branch above.
            if out.get("accepted") is True:
                self.requests[rid] = (path, canonical, json.dumps(out, sort_keys=True).encode())
            return 200, out


class _Handler(BaseHTTPRequestHandler):
    server: "SimulatorHTTPServer"
    def do_POST(self):  # noqa: N802
        if self.path not in PATHS:
            self._send_json(404, self.server.service.error_response("not_found")); return
        try:
            content_type = self.headers.get("Content-Type")
            if content_type is None:
                self._send_json(415, self.server.service.error_response("unsupported_media_type")); return
            parts = [part.strip() for part in content_type.split(";")]
            if parts[0].lower() != "application/json":
                self._send_json(415, self.server.service.error_response("unsupported_media_type")); return
            params = parts[1:]
            if any(("=" not in item or item.split("=", 1)[0].strip().lower() != "charset"
                    or item.split("=", 1)[1].strip().strip('"').lower() != "utf-8")
                   for item in params):
                self._send_json(415, self.server.service.error_response("unsupported_media_type")); return
            encoding = self.headers.get("Content-Encoding")
            if encoding and encoding.strip().lower() != "identity":
                self._send_json(415, self.server.service.error_response("unsupported_encoding")); return
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if length < 0:
                self._send_json(400, self.server.service.error_response("invalid_content_length")); return
            if length > MAX_BODY_BYTES:
                self._send_json(413, self.server.service.error_response("request_too_large")); return
            raw = self.rfile.read(length)
            if raw.startswith(b"\xef\xbb\xbf"):
                raise ValueError("utf8_bom")
            body = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs_no_duplicates)
            if not isinstance(body, dict):
                raise ValueError
            if _json_depth(body) > MAX_JSON_DEPTH:
                raise OverflowError("json_depth")
            status, out = self.server.service.handle(self.path, body)
        except OverflowError:
            status, out = 400, self.server.service.error_response("json_too_deep")
        except _DuplicateJSONKey:
            status, out = 400, self.server.service.error_response("duplicate_json_key")
        except Exception:
            status, out = 400, self.server.service.error_response("invalid_json")
        self._send_json(status, out)

    def _send_json(self, status: int, out: dict[str, Any]) -> None:
        data = json.dumps(out, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _method_not_allowed(self):
        status = 405 if self.path in PATHS else 404
        error = "method_not_allowed" if status == 405 else "not_found"
        self._send_json(status, self.server.service.error_response(error))

    do_GET = _method_not_allowed
    do_PUT = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_DELETE = _method_not_allowed
    do_HEAD = _method_not_allowed
    def log_message(self, *_args):
        return


class SimulatorHTTPServer(ThreadingHTTPServer):
    def __init__(self, address, service: SimulatorService):
        self.service = service
        super().__init__(address, _Handler)


def serve(scenario: Scenario, host: str = "127.0.0.1", port: int = 2026,
          robot_id: str = "local", rules: SimulationRules | None = None) -> SimulatorHTTPServer:
    server = SimulatorHTTPServer((host, port), SimulatorService(scenario, robot_id, rules))
    return server
