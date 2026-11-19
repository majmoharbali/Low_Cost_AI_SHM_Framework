"""Optional reproduction of the legacy synthetic learner, not research training."""
import argparse
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy', action='store_true')
    parser.add_argument('--smoke', action='store_true', help='Use 30 samples and five trees for an execution check only')
    parser.add_argument('--samples', type=int, default=4500)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--output', type=Path, default=Path('outputs/legacy/retrained.pkl'))
    args = parser.parse_args(argv)
    if not args.legacy:
        parser.error('Only --legacy synthetic reproduction is available; no measured-data detector exists yet')
    if args.samples < 30 or args.samples % 3:
        parser.error('samples must be at least 30 and divisible by three')
    from .legacy.training import main as train
    train(samples=30 if args.smoke else args.samples, seed=args.seed, output=args.output, trees=5 if args.smoke else 100)


if __name__ == '__main__':
    main()

