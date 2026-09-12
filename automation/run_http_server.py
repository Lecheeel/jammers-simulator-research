"""Start the loopback four-command compatibility service."""
from __future__ import annotations

import argparse

from jammers_simulator import SimulationRules, generate_practice
from simulator_http import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Jammers Simulator HTTP harness.")
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2026)
    parser.add_argument("--robot-id", default="local")
    parser.add_argument("--realistic-timing", action="store_true",
                        help="Use recovered production-like timing instead of fast_test().")
    args = parser.parse_args()
    rules = SimulationRules() if args.realistic_timing else SimulationRules.fast_test()
    server = serve(generate_practice(args.seed, count=args.count), host=args.host,
                   port=args.port, robot_id=args.robot_id, rules=rules)
    print(f"Listening on http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
