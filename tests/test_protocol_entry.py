from jammers_simulator import Scenario, Jammer, SimulationRules
from simulator_http import SimulatorService


def test_protocol_enter_always_starts_at_origin():
    s = Scenario("1", 1, 100, 100,
                 [Jammer("omnidirectional", 50, 50, 10, channel=1)],
                 target_x=90, target_y=90, target_radius=1)
    svc = SimulatorService(s, rules=SimulationRules.fast_test())
    status, out = svc.handle("/enter", {"arena_id": "default", "robot_id": "local", "request_id": "e"})
    assert status == 200 and out["accepted"]
    assert tuple(svc.engine.state.position) == (0.0, 0.0)

