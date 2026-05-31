"""Command-line helper to export double-star systems and optionally
embed them into an existing stars JSON output.

This module parses the WDS TSV (via the `DoubleStarMatcher`) and writes
`double_stars.json`. It can also merge double-star metadata into a
`stars.m{mag}.json` file when requested.
"""

import csv
import json
import sys
from pathlib import Path

from config import VARIABLE_THRESHOLD, WDS_FILENAME, WDS_VIZIER_URL
from double_stars import DoubleStarMatcher

# pylint: disable=too-many-locals,protected-access,too-many-branches,too-many-statements


def main(
    max_mag: float | None = None,
    min_sep: float = 2.0,
    embed_into_stars: bool = True,
    only_mode: bool = False,
    debug: bool = False,
) -> None:
    """Export double-star systems and optionally embed dbl metadata into an
    existing `stars.m{mag}.json` file when *max_mag* is provided.

    If *embed_into_stars* is True and *max_mag* is specified, the function
    will load `output/stars.m{max_mag}.json`, attach `dbl` entries and
    overwrite that file. A standalone `double_stars.json` is always written.
    """
    sources_dir = Path(__file__).parent / "sources"
    cache_dir = Path(__file__).parent / "cache"
    output_dir = Path(__file__).parent / "output"
    matcher = DoubleStarMatcher(sources_dir, cache_dir=cache_dir)

    # If running in `only_mode` the user likely expects the double-star
    # information to be embedded into an existing stars file. If the
    # requested stars file doesn't exist, fail early and instruct the user
    # to initialize/run the stars pipeline first so they can re-run with
    # embedding enabled.
    if only_mode and embed_into_stars and max_mag is not None:
        stars_file = output_dir / f"stars.m{max_mag:g}.json"
        if not stars_file.exists():
            print(
                f"Stars file {stars_file} not found.\n"
                "Run 'python main.py --only stars --max-mag {max_mag:g}' or\n"
                "'python main.py --group stars --max-mag {max_mag:g}' to create it,\n"
                "then re-run this command to embed double-star metadata.")
            sys.exit(2)

    # Always produce the standalone double_stars.json for inspection/debugging
    # Ensure WDS TSV is present in the cache (download if necessary) and
    # parse it to build systems.
    tsv_path = matcher._downloader.fetch(WDS_VIZIER_URL, WDS_FILENAME)
    systems = matcher._load_systems(tsv_path, max_mag=(max_mag or 8.0), min_sep=min_sep)
    out = output_dir / "double_stars.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    grouped = {s["wds"]: s for s in systems}
    with out.open("w", encoding="utf-8") as fh:
        json.dump(grouped, fh, ensure_ascii=False, indent=2)
    if only_mode:
        # In only_mode we prefer compact output regardless of debug so the
        # command remains useful as a standalone tool.
        if max_mag is None:
            print(f"Wrote {len(grouped)} double-star systems to {out} (max_mag=8.0)")
        else:
            print(
                f"Wrote {len(grouped)} double-star systems to {out} "
                f"(filtered by max_mag={max_mag:g})"
            )
    else:
        if debug:
            if max_mag is None:
                print(f"Wrote {len(grouped)} double-star systems to {out} (max_mag=8.0)")
            else:
                print(
                    f"Wrote {len(grouped)} double-star systems to {out} "
                    f"(filtered by max_mag={max_mag:g})"
                )

    # Optionally embed into existing stars file
    if embed_into_stars and max_mag is not None:
        stars_file = output_dir / f"stars.m{max_mag:g}.json"
        if not stars_file.exists():
            print(f"Stars file {stars_file} not found; skipping embedding.")
            return
        # Load grouped stars, flatten, attach, regroup and overwrite
        with stars_file.open("r", encoding="utf-8") as fh:
            grouped_stars = json.load(fh)
        flat: list[dict] = []
        for _const, lst in grouped_stars.items():
            flat.extend(lst)
        n_dbl_stars, n_pairs = matcher.attach(flat, max_mag=max_mag, min_sep=min_sep)
        # Rebuild grouped structure preserving original constellation keys
        # The `stars.m{mag}.json` file is already grouped by constellation
        # keys; we flattened it earlier in the same order. Re-slice `flat`
        # back into the original group sizes so we don't rely on a
        # per-star `const` field (which the writer may remove).
        new_grouped: dict[str, list[dict]] = {}
        idx = 0
        for key, lst in grouped_stars.items():
            size = len(lst)
            new_grouped[key] = flat[idx : idx + size]
            idx += size
        with stars_file.open("w", encoding="utf-8") as fh:
            json.dump(new_grouped, fh, ensure_ascii=False)
        if only_mode:
            print(f"Embedded dbl into {stars_file}: {n_dbl_stars} stars, {n_pairs} pairs")
        else:
            if debug:
                print(f"Embedded dbl into {stars_file}: {n_dbl_stars} stars, {n_pairs} pairs")

        # Emit a stars-like summary so this command's output matches the
        # `--only stars` run. Recompute basic stats from the updated file.
        # Use the original grouping loaded from file for constellation counts
        total_stars = sum(len(lst) for lst in grouped_stars.values())
        n_const = len(grouped_stars)
        n_variable = sum(
            1 for lst in grouped_stars.values() for s in lst if isinstance(s.get("mag"), list)
        )

        # Load curated notes sidecar to distinguish curated vs auto notes.
        notes_path = sources_dir / "notes_stars.csv"
        curated_hips = set()
        if notes_path.exists():
            with notes_path.open("r", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    hip = row.get("hip", "")
                    try:
                        hip_i = int(hip)
                    except ValueError:
                        continue
                    curated_hips.add(hip_i)

        n_curated = 0
        n_auto = 0
        # Count notes across the stars file we just loaded (grouped_stars),
        # not the double-star systems mapping (`grouped`). Using the wrong
        # variable caused iteration over dict keys (strings) and a crash.
        for lst in grouped_stars.values():
            for s in lst:
                note = s.get("note")
                if not note:
                    continue
                hip = s.get("hip")
                if isinstance(hip, int) and hip in curated_hips:
                    n_curated += 1
                else:
                    n_auto += 1

        # If invoked as `--only double_stars` prefer compact output showing
        # only the double-star summary and output path so it matches the
        # user's expectation for that mode.
        if only_mode:
            size_mb = stars_file.stat().st_size / 1_048_576
            print(
                f"Double stars   : {n_dbl_stars} stars with {n_pairs} pairs "
                f"(sep >= {min_sep} arcsec)"
            )
            print(f"Output         : {stars_file} ({size_mb:.2f} MB)")
            return

        if debug:
            size_mb = stars_file.stat().st_size / 1_048_576
            print(
                f"Stars included : {total_stars:,} across {n_const:,} "
                "constellations"
            )
            print(
                f"Variable stars : {n_variable} encoded with amplitude >= "
                f"{VARIABLE_THRESHOLD}"
            )
            print(
                f"Double stars   : {n_dbl_stars} stars with {n_pairs} pairs "
                f"(sep >= {min_sep} arcsec)"
            )
            note_parts = (
                ([f"{n_curated} curated"] if n_curated else [])
                + ([f"{n_auto} auto-generated"] if n_auto else [])
            )
            notes_summary = " + ".join(note_parts) if note_parts else "none"
            print(f"Star notes     : {notes_summary}")
            print(f"Output         : {stars_file} ({size_mb:.2f} MB)")
        else:
            # Concise summary for non-debug/grouped runs so the user still
            # sees the key results without verbose diagnostics.
            size_mb = stars_file.stat().st_size / 1_048_576
            note_parts = (
                ([f"{n_curated} curated"] if n_curated else [])
                + ([f"{n_auto} auto-generated"] if n_auto else [])
            )
            notes_summary = " + ".join(note_parts) if note_parts else "none"
            print(f"Stars included : {total_stars:,} across {n_const:,} constellations")
            print(f"Variable stars : {n_variable} encoded with amplitude >= {VARIABLE_THRESHOLD}")
            print(
                f"Double stars   : {n_dbl_stars} stars with {n_pairs} pairs "
                f"(sep >= {min_sep} arcsec)"
            )
            print(f"Star notes     : {notes_summary}")
            print(f"Output         : {stars_file} ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
