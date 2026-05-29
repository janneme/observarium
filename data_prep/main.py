"""Data preparation CLI entry point.

Usage examples:
    python main.py
    python main.py --only stars
    python main.py --only dso
    python main.py --object M42
"""

import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare Observarium catalogue data."
    )
    parser.add_argument(
        "--only",
        choices=["stars", "dso", "constellations", "double_stars", "solar_system", "moon_features"],
        help="Process only the named data category.",
    )
    parser.add_argument(
        "--object",
        metavar="ID",
        help="Process a single object for a test run (e.g. M42, NGC224).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raise NotImplementedError(
        f"Data prep pipeline not yet implemented (only={args.only!r}, object={args.object!r})."
    )


if __name__ == "__main__":
    main()
