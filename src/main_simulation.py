"""Explicit entry point for the archived synthetic demonstration."""
import argparse


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy', action='store_true', help='Acknowledge synthetic-only classifier limitations')
    parser.add_argument('--smoke', action='store_true', help='Process one window without opening a server')
    parser.add_argument('--windows', type=int, default=6, help='Finite number of synthetic windows (default 6)')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args(argv)
    if not args.legacy:
        parser.error('Use --legacy for the archived demo. Research verification: python -m src.verify_mechanics')
    if args.windows < 1 or not 1 <= args.port <= 65535:
        parser.error('windows must be positive and port must be in 1..65535')
    from .legacy.runtime import run
    run(seed=args.seed, windows=1 if args.smoke else args.windows, port=args.port, smoke=args.smoke)


if __name__ == '__main__':
    main()

