import json
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from jammers_simulator import generate_practice, SimulationRules, Scenario, Jammer
from simulator_http import serve


def post(base, path, body):
    req = Request(base + path, data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req) as resp:
        return resp.status, json.loads(resp.read())


def test_http_four_commands_and_idempotency():
    rules = SimulationRules.fast_test()
    rules.program_run_limit_ms = 1_000_000
    rules.movement_speed_mps = 1_000_000.0
    server = serve(generate_practice(3), port=0, rules=rules)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    common = {"arena_id": "default", "robot_id": "local"}
    status, enter = post(base, "/enter", {**common, "request_id": "e1"})
    assert status == 200 and enter["accepted"]
    action = {**common, "request_id": "m1", "position": {"x": 500, "y": 500}, "channel": 1}
    status, first = post(base, "/measure", action)
    assert first["accepted"] and status == 200
    status, again = post(base, "/measure", action)
    assert again == first
    try:
        post(base, "/measure", {**action, "channel": 2})
    except Exception as exc:
        assert "409" in str(exc)
    status, clear = post(base, "/clear", {**common, "request_id": "c1", "position": {"x": 0, "y": 0}, "channel": 2})
    assert status == 200 and clear["accepted"]
    post(base, "/exit", {**common, "request_id": "x1"})
    server.shutdown(); server.server_close()


def test_http_real_clock_gates_and_remaining_duration_are_deterministic():
    now = [0.0]
    rules = SimulationRules.from_dict({
        "countdown_seconds": 5,
        "entry_window_seconds": 10,
        "program_run_limit_seconds": 8,
        "virtual_time_limit_seconds": 100,
        "movement_speed_mps": 1_000_000,
        "measure_duration_ms": 0,
        "clear_duration_ms": 0,
        "clear_failure_duration_ms": 0,
        "channel_switch_duration_ms": 0,
    })
    service = __import__("simulator_http").SimulatorService(
        generate_practice(9, count=10), rules=rules, clock=lambda: now[0]
    )
    common = {"arena_id": "default", "robot_id": "local"}
    status, out = service.handle("/enter", {**common, "request_id": "e"})
    assert status == 200 and not out["accepted"]
    now[0] = 5.0
    status, out = service.handle("/enter", {**common, "request_id": "e"})
    assert status == 200 and out["accepted"]
    assert out["remaining_real_duration_s"] == 8
    now[0] = 12.9
    status, out = service.handle("/measure", {
        **common, "request_id": "m", "position": {"x": 0, "y": 0}, "channel": 1
    })
    assert status == 200 and out["accepted"]
    now[0] = 13.0
    status, out = service.handle("/measure", {
        **common, "request_id": "m2", "position": {"x": 0, "y": 0}, "channel": 1
    })
    assert status == 200 and not out["accepted"]
    assert service.engine.state.end_reason == "program_timeout"


def test_http_request_validation_headers_duplicates_and_method():
    rules = SimulationRules.fast_test()
    server = serve(generate_practice(11), port=0, rules=rules)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    body = b'{"arena_id":"default","arena_id":"default","robot_id":"local","request_id":"x"}'
    req = Request(base + "/enter", data=body,
                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        urlopen(req)
        assert False, "duplicate JSON key should be rejected"
    except HTTPError as exc:
        assert exc.code == 400
    req = Request(base + "/enter", data=b"{}",
                  headers={"Content-Type": "text/plain"}, method="POST")
    try:
        urlopen(req)
        assert False, "unsupported media type should be rejected"
    except HTTPError as exc:
        assert exc.code == 415
    req = Request(base + "/enter", data=b"{}",
                  headers={"Content-Type": "application/json"}, method="GET")
    try:
        urlopen(req)
        assert False, "GET should be rejected"
    except HTTPError as exc:
        assert exc.code == 405
    server.shutdown(); server.server_close()


def test_http_protocol_timing_matches_attachment_example():
    scenario = Scenario(
        "1", 1, 5000, 5000,
        [Jammer("omnidirectional", 4500, 4500, 1, channel=20)],
        target_x=0, target_y=0, target_radius=1,
    )
    rules = SimulationRules(
        countdown_ms=0, entry_window_ms=1_500_000,
        program_run_limit_ms=1_200_000,
        virtual_time_limit_us=360_000_000_000,
    )
    service = __import__("simulator_http").SimulatorService(scenario, rules=rules)
    common = {"arena_id": "default", "robot_id": "local"}
    status, out = service.handle("/enter", {**common, "request_id": "e"})
    assert status == 200 and out["accepted"]
    status, out = service.handle("/measure", {
        **common, "request_id": "m1", "position": {"x": 300, "y": 400}, "channel": 1
    })
    assert status == 200 and out["accepted"] and out["virtual_time_s"] == 105
    status, out = service.handle("/measure", {
        **common, "request_id": "m2", "position": {"x": 300, "y": 400}, "channel": 2
    })
    assert status == 200 and out["virtual_time_s"] == 111
    status, out = service.handle("/clear", {
        **common, "request_id": "c1", "position": {"x": 300, "y": 0}, "channel": 3
    })
    assert status == 200 and out["accepted"] and out["clear_result"] == "no_target_in_range"
    assert out["virtual_time_s"] == 194
    assert service.engine.state.channel == 2
    status, out = service.handle("/measure", {
        **common, "request_id": "m3", "position": {"x": 300, "y": 0}, "channel": 2
    })
    assert status == 200 and out["virtual_time_s"] == 199
