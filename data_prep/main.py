"""Data preparation CLI entry point.

Usage examples:
    python main.py
    python main.py --only stars
    python main.py --only dso
    python main.py --object M42
"""

# pylint: disable=duplicate-code

import argparse
import math
import sys
from collections.abc import Callable
from pathlib import Path

from config import MAX_STAR_MAGNITUDE, NON_MESSIER_NUM
from constellations import ConstellationPipeline
from dso import DsoPipeline
from moon_features import MoonFeaturePipeline
from stars import StarPipeline
from variable_stars import VariableStarPipeline

_SOURCES_DIR = Path(__file__).parent / "sources"
_CACHE_DIR = Path(__file__).parent / "cache"
_OUTPUT_DIR = Path(__file__).parent / "output"

_ALL_CATEGORIES = [
    "variable_stars",
    "stars",
    "dso",
    "constellations",
    "solar_system",
    "moon_features",
    "double_stars",
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
        default=None,
        metavar="FLOAT",
        dest="var_max_mag",
        help=(
            "Peak brightness limit for the SIMBAD variable-star query "
            "(default: 0.75 * --max-mag, rounded up)."
        ),
    )
    parser.add_argument(
        "--group",
        choices=["stars"],
        help='Fetch a named group of related data (e.g. "stars").',
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
    parser.add_argument(
        "--min-double-star-sep",
        type=float,
        default=2.0,
        metavar="FLOAT",
        dest="min_double_star_sep",
        help="Minimum double-star separation in arcsec for inclusion (default: %(default)s).",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point: run all requested data pipelines."""
    args = parse_args()
    # Compute default for var_max_mag based on max_mag if not provided.
    if args.var_max_mag is None:
        effective_max = args.max_mag if args.max_mag is not None else MAX_STAR_MAGNITUDE
        args.var_max_mag = float(math.ceil(0.75 * effective_max))

    # Determine targets and star kwargs
    if args.group == "stars":
        targets = ["variable_stars", "stars", "double_stars"]
    else:
        targets = [args.only] if args.only else _ALL_CATEGORIES
    star_kwargs: dict[str, float] = {}
    if args.max_mag is not None:
        star_kwargs["max_mag"] = args.max_mag
    if args.var_threshold is not None:
        star_kwargs["var_threshold"] = args.var_threshold

    runners = _build_runners(args, star_kwargs)
    for target in targets:
        runner = runners.get(target)
        if runner is None:
            print(f"[data-prep] '{target}' not yet implemented, skipping.")
            continue
        runner()


def _prepare_var_index(args: argparse.Namespace) -> dict[int, tuple[float, float]]:
    """Prepare and return the variable-star index for star enrichment."""
    if args.only == "stars":
        return {}
    var_pipeline = VariableStarPipeline(_SOURCES_DIR, args.var_max_mag, debug=args.debug)
    if args.group == "stars":
        if not var_pipeline.csv_path().exists():
            var_pipeline.run()
    else:
        # Strict mode: require existing variable-star CSV
        if not var_pipeline.csv_path().exists():
            csv_name = var_pipeline.csv_path().name
            print(
                f"Variable-star data {csv_name} not found.\n"
                "Run 'python main.py --only variable_stars --var-max-mag "
                f"{args.var_max_mag}'\n"
                "or 'python main.py --group stars' to create it, then re-run."
            )
            sys.exit(2)
    return var_pipeline.load_index()


def _run_stars(args: argparse.Namespace, star_kwargs: dict[str, float]) -> None:
    var_index = _prepare_var_index(args)
    show_summary = False if args.group == "stars" else (args.debug or args.group != "stars")
    StarPipeline(
        _SOURCES_DIR,
        _OUTPUT_DIR,
        cache_dir=_CACHE_DIR,
        debug=args.debug,
        min_double_star_sep=args.min_double_star_sep,
        **star_kwargs,
    ).run(var_index=var_index, attach_double=False, show_summary=show_summary)


def _build_runners(
    args: argparse.Namespace,
    star_kwargs: dict[str, float],
) -> dict[str, Callable[[], None]]:
    return {
        "variable_stars": lambda: VariableStarPipeline(
            _SOURCES_DIR, args.var_max_mag, debug=args.debug
        ).run(),
        "stars": lambda: _run_stars(args, star_kwargs),
        "dso": lambda: DsoPipeline(
            _SOURCES_DIR,
            _OUTPUT_DIR,
            cache_dir=_CACHE_DIR,
            non_messier_num=args.non_messier_num,
            debug=args.debug,
        ).run(object_id=args.object),
        "constellations": lambda: ConstellationPipeline(
            _SOURCES_DIR, _OUTPUT_DIR, cache_dir=_CACHE_DIR, debug=args.debug
        ).run(),
        "moon_features": lambda: MoonFeaturePipeline(_SOURCES_DIR, _OUTPUT_DIR).run(),
        "double_stars": lambda: __import__("double_stars_cli").main(
            max_mag=args.max_mag,
            min_sep=args.min_double_star_sep,
            embed_into_stars=True,
            only_mode=(args.only == "double_stars"),
            debug=args.debug,
        ),
    }

if __name__ == "__main__":
    main()
