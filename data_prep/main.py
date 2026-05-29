"""Data preparation CLI entry point.

Usage examples:
    python main.py
    python main.py --only stars
    python main.py --only dso
    python main.py --object M42
"""

import argparse
from collections.abc import Callable
from pathlib import Path

from config import NON_MESSIER_NUM, VAR_MAX_MAG
from constellations import ConstellationPipeline
from dso import DsoPipeline
from stars import StarPipeline
from variable_stars import VariableStarPipeline

_SOURCES_DIR = Path(__file__).parent / "sources"
_OUTPUT_DIR = Path(__file__).parent / "output"

_ALL_CATEGORIES = [
    "variable_stars",
    "stars",
    "dso",
    "constellations",
    "double_stars",
    "solar_system",
    "moon_features",
]


def parse_args() -> argparse.Namespace:
    """Parse and return CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Prepare Observarium catalogue data."
    )
    parser.add_argument(
        "--only",
        choices=_ALL_CATEGORIES,
        help="Process only the named data category.",
    )
    parser.add_argument(
        "--object",
        metavar="ID",
        help="Process a single object for a test run (e.g. M42, NGC224).",
    )
    parser.add_argument(
        "--max-mag",
        type=float,
        default=None,
        metavar="FLOAT",
        dest="max_mag",
        help="Maximum apparent magnitude to include (default: config 8.0).",
    )
    parser.add_argument(
        "--var-threshold",
        type=float,
        default=None,
        metavar="FLOAT",
        dest="var_threshold",
        help="Min magnitude range to encode as variable [min,max] (default: config 1.0).",
    )
    parser.add_argument(
        "--var-max-mag",
        type=float,
        default=VAR_MAX_MAG,
        metavar="FLOAT",
        dest="var_max_mag",
        help="Peak brightness limit for the SIMBAD variable-star query (default: %(default)s).",
    )
    parser.add_argument(
        "--skip-variables",
        action="store_true",
        default=False,
        dest="skip_variables",
        help="Skip variable-star enrichment when processing stars.",
    )
    parser.add_argument(
        "--non-messier-num",
        type=int,
        default=NON_MESSIER_NUM,
        metavar="INT",
        dest="non_messier_num",
        help="Number of brightest non-Messier DSOs to include (default: %(default)s).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Print verbose diagnostic output (cache hits, counts loaded, …).",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point: run all requested data pipelines."""
    args = parse_args()
    targets = [args.only] if args.only else _ALL_CATEGORIES
    star_kwargs: dict[str, float] = {}
    if args.max_mag is not None:
        star_kwargs["max_mag"] = args.max_mag
    if args.var_threshold is not None:
        star_kwargs["var_threshold"] = args.var_threshold

    def _run_stars() -> None:
        var_index: dict[int, tuple[float, float]] = {}
        if not args.skip_variables:
            var_pipeline = VariableStarPipeline(
                _SOURCES_DIR, args.var_max_mag, debug=args.debug
            )
            if not var_pipeline.csv_path().exists():
                var_pipeline.run()
            var_index = var_pipeline.load_index()
        StarPipeline(
            _SOURCES_DIR, _OUTPUT_DIR, debug=args.debug, **star_kwargs
        ).run(var_index=var_index)

    runners: dict[str, Callable[[], None]] = {
        "variable_stars": lambda: VariableStarPipeline(
            _SOURCES_DIR, args.var_max_mag
        ).run(),
        "stars": _run_stars,
        "dso": lambda: DsoPipeline(
            _SOURCES_DIR,
            _OUTPUT_DIR,
            non_messier_num=args.non_messier_num,
            debug=args.debug,
        ).run(
            object_id=args.object
        ),
        "constellations": lambda: ConstellationPipeline(
            _SOURCES_DIR, _OUTPUT_DIR, debug=args.debug
        ).run(),
    }
    for target in targets:
        runner = runners.get(target)
        if runner is None:
            print(f"[data-prep] '{target}' not yet implemented, skipping.")
        else:
            runner()


if __name__ == "__main__":
    main()
