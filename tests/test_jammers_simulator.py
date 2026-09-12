import math
from jammers_simulator import *

def test_generation_is_deterministic():
    assert generate_practice(1234) == generate_practice(1234)
    assert generate_practice(1234) != generate_practice(1235)

def test_disk_and_sector():
    j=Jammer("omnidirectional",0,0,10)
    assert inside_jammer_disk(6,8,0,0,10)
    d=Jammer("directional",0,0,10,bearing=0,beam_width=40)
    assert directional_coverage(5,0,d)
    assert not directional_coverage(0,5,d)

def test_angle_wrap():
    assert angle_error(359,1)==2
    assert normalize_degrees(-1)==359
    assert quantize_bearing_hundredths(12.345)==12.35

def make_engine(**rule_overrides):
    s = Scenario("1", 1, 100, 100, [
        Jammer("omnidirectional", 50, 50, 12, channel=1, id="j1"),
        Jammer("directional", 80, 80, 15, bearing=0, beam_width=90, channel=2, id="j2"),
    ], target_x=10, target_y=10, target_radius=5)
    r = SimulationRules(**rule_overrides)
    return s, Engine(s, r)

def test_countdown_entry_and_move_time():
    s, e = make_engine(movement_speed_mps=2)
    assert e.state.phase == "preparing"
    e.advance(5000)
    assert e.state.phase == "waiting_enter"
    assert e.enter(10, 10).accepted
    assert e.state.phase == "running"
    old = e.state.virtual_time_us
    result = e.move_to(12, 10)
    assert result.accepted and result.data["duration_ms"] == 1000
    assert e.state.virtual_time_us == old + 1_000_000

def test_measurement_and_clear_failure_then_success():
    s, e = make_engine()
    e.advance(5000); e.enter(10, 10)
    assert e.measure(channel=1).accepted is False
    e.move_to(50, 50)
    measured = e.measure(channel=1)
    assert measured.accepted and measured.data["jammer_ids"] == ["j1"]
    assert e.clear("wrong-id").accepted is False
    assert e.state.clear_failure_count == 1
    assert e.clear("j1").accepted
    assert e.summary()["cleared_jammer_count"] == 1

def test_clear_channel_does_not_switch_measurement_radio():
    s, e = make_engine()
    e.advance(5000); e.enter(10, 10)
    e.measure(channel=1)
    before = (e.state.channel, e.state.channel_switch_count, e.state.virtual_time_us)
    result = e.clear(channel=2)
    assert not result.accepted
    assert e.state.channel == before[0]
    assert e.state.channel_switch_count == before[1]
    assert e.state.virtual_time_us == before[2] + e.rules.clear_failure_duration_ms * 1000

def test_directional_channel_coverage():
    s, e = make_engine()
    e.advance(5000); e.enter(10, 10); e.move_to(85, 80)
    assert e.measure(channel=2).accepted

def test_waiting_entry_timeout_and_manual_abort():
    s, e = make_engine()
    e.advance(5000 + 1_500_000)
    assert e.done() and e.state.end_reason == "window_timeout_before_enter"
    s, e = make_engine(); session = Session(s, e.rules, e)
    session.manual_abort()
    assert session.done() and e.state.end_reason == "manual_abort_before_enter"

def test_program_and_virtual_time_limits():
    s, e = make_engine(program_run_limit_ms=100, virtual_time_limit_us=10_000_000)
    e.advance(5000); e.enter(10, 10)
    e.advance(100)
    assert e.done() and e.state.end_reason == "program_timeout"
    s, e = make_engine(program_run_limit_ms=10_000_000, virtual_time_limit_us=5_100_000)
    e.advance(5000); e.enter(10, 10); e.advance(101)
    assert e.done() and e.state.end_reason == "virtual_timeout"

def test_session_snapshot_restore_and_exit():
    s, e = make_engine(); session = Session(s, e.rules, e)
    session.execute({"action": "advance", "milliseconds": 5000})
    session.execute({"action": "enter", "x": 10, "y": 10})
    snap = session.snapshot()
    restored = Session.from_state(s, snap, e.rules)
    assert restored.observe()["engine"]["entered"] is True
    result = restored.execute({"action": "/exit"})
    assert result.accepted and restored.done()
    assert restored.engine.state.end_reason == "user_exit"

def test_timing_rules_are_overridable_for_automation():
    s, e = make_engine()
    e = Engine(s, SimulationRules.from_dict({
        "countdown_seconds": 0,
        "entry_window_seconds": 2,
        "program_run_limit_seconds": 3,
        "virtual_time_limit_seconds": 4,
        "measure_duration_ms": 0,
        "clear_duration_ms": 0,
    }))
    assert e.state.phase == "waiting_enter"
    e.advance(2000)
    assert e.done() and e.state.end_reason == "window_timeout_before_enter"
    fast = SimulationRules.fast_test()
    assert fast.countdown_ms == 0 and fast.program_run_limit_ms == 10_000

def test_measure_coordinates_may_be_outside_arena_but_with_protocol_bound():
    s, e = make_engine(); e.advance(5000); e.enter(10, 10)
    assert e.move_to(1500, -1500).accepted
    assert not e.move_to(2_000_001, 0).accepted

def test_report_export(tmp_path):
    s, e = make_engine(); session = Session(s, e.rules, e)
    session.execute({"action":"advance", "milliseconds":5000})
    session.execute({"action":"enter", "x":10, "y":10})
    paths = session.export_reports(str(tmp_path), "practice-p1-1-test")
    assert paths["result"].endswith(".result.json")
    assert paths["summary"].endswith(".psum")
    assert paths["journal"].endswith(".jlog")
    text = open(paths["journal"], encoding="utf-8").read()
    assert '"action": "enter"' in text

if __name__ == '__main__':
    test_generation_is_deterministic(); test_disk_and_sector(); test_angle_wrap(); print('ok')
