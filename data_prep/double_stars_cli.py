"""Command-line helper to export double-star systems and optionally
embed them into an existing stars JSON output.

This module parses the WDS TSV (via the `DoubleStarMatcher`) and writes
`double_stars.json`. It can also merge double-star metadata into a
`stars.m{mag}.json` file when requested.
"""

import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

from config import BRIGHT_VARIABLE_THRESHOLD, WDS_FILENAME, WDS_VIZIER_URL
from double_stars import DoubleStarMatcher

# pylint: disable=too-many-locals,protected-access,too-many-branches,too-many-statements


def main(
    max_mag: float | None = None,
    stars_max_mag: float | None = None,
    min_sep: float = 2.0,
    embed_into_stars: bool = True,
    only_mode: bool = False,
    debug: bool = False,
) -> None:
    """Export double-star systems and optionally embed dbl metadata into an
    existing `stars.m{mag}.json` file when *max_mag* is provided.

    *max_mag* controls which WDS pairs are included (double-star magnitude limit).
    *stars_max_mag* controls which stars file is read/written; defaults to *max_mag*.
    If *embed_into_stars* is True, the function will load
    `output/stars.m{stars_max_mag}.json`, attach `dbl` entries and overwrite it.
    A standalone `double_stars.json` is always written.
    """
    file_mag = stars_max_mag if stars_max_mag is not None else max_mag
    sources_dir = Path(__file__).parent / "sources"
    cache_dir = Path(__file__).parent / "cache"
    output_dir = Path(__file__).parent / "output"
    matcher = DoubleStarMatcher(sources_dir, cache_dir=cache_dir)

    # If running in `only_mode` the user likely expects the double-star
    # information to be embedded into an existing stars file. If the
    # requested stars file doesn't exist, fail early and instruct the user
    # to initialize/run the stars pipeline first so they can re-run with
    # embedding enabled.
    if only_mode and embed_into_stars and file_mag is not None:
        stars_file = output_dir / f"stars.m{file_mag:g}.json"
        if not stars_file.exists():
            print(
                f"Stars file {stars_file} not found.\n"
                "Run 'python main.py --only stars --max-mag {max_mag:g}' or\n"
                "'python main.py --group stars --max-mag {max_mag:g}' to create it,\n"
                "then re-run this command to embed double-star metadata.")
            sys.exit(2)

    # Always produce the standalone double_stars.json for inspection/debugging.
    # Ensure WDS TSV is present in the cache (download if necessary) and
    # parse it to build systems.
    tsv_path = matcher._downloader.fetch(WDS_VIZIER_URL, WDS_FILENAME)
    systems = matcher._load_systems(tsv_path, max_mag=(max_mag or 8.0), min_sep=min_sep)

    # If stars output exists for this magnitude, enrich systems with inferred
    # component spectra before writing standalone double-star JSON.
    if file_mag is not None:
        stars_file = output_dir / f"stars.m{file_mag:g}.json"
        if stars_file.exists():
            with stars_file.open("r", encoding="utf-8") as fh:
                grouped_stars = json.load(fh)
            stars_flat: list[dict[str, Any]] = []
            for lst in grouped_stars.values():
                stars_flat.extend(lst)
            matcher.attach(stars_flat, max_mag=max_mag or 8.0, min_sep=min_sep)
            _merge_enriched_spectra_from_stars(systems, stars_flat)
    out = output_dir / "double_stars.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    grouped = {s["wds"]: s for s in systems}
    with out.open("w", encoding="utf-8") as fh:
        json.dump(grouped, fh, ensure_ascii=False, indent=2)
    # Also write a mag-tagged copy when max_mag is specified so data_upload.py
    # can pick the right file for the current MAG setting.
    if max_mag is not None:
        out_mag = output_dir / f"double_stars.m{max_mag:g}.json"
        with out_mag.open("w", encoding="utf-8") as fh:
            json.dump(grouped, fh, ensure_ascii=False, indent=2)
    # Only emit the explicit 'Wrote ...' message when debug is enabled.
    if debug:
        if max_mag is None:
            print(f"Wrote {len(grouped)} double-star systems to {out} (max_mag=8.0)")
        else:
            print(
                f"Wrote {len(grouped)} double-star systems to {out} "
                f"(filtered by max_mag={max_mag:g})"
            )

    # Optionally embed into existing stars file
    if embed_into_stars and file_mag is not None:
        stars_file = output_dir / f"stars.m{file_mag:g}.json"
        if not stars_file.exists():
            print(f"Stars file {stars_file} not found; skipping embedding.")
            return
        # Load grouped stars, flatten, attach, regroup and overwrite
        with stars_file.open("r", encoding="utf-8") as fh:
            grouped_stars = json.load(fh)
        flat: list[dict] = []
        for lst in grouped_stars.values():
            flat.extend(lst)
        n_dbl_stars, n_pairs, n_phys_pairs = matcher.attach(
            flat, max_mag=max_mag or 8.0, min_sep=min_sep
        )
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
                print(
                    f"Embedded dbl into {stars_file}: {n_dbl_stars} stars, "
                    f"{n_pairs} pairs, {n_phys_pairs} physical"
                )

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
        # Count notes across the stars file we just loaded (grouped_stars).
        # Prefer the persistent top-N summary note when present (e.g.
        # "Among the 10 stars with highest luminosity"). If those
        # summary notes exist, report that as the auto-generated count
        # to avoid recounting many minor non-curated notes.
        # Recognise summary phrases for luminosity and brightness and count
        # the unique stars they mark; otherwise count non-summary auto notes.
        lum_re = re.compile(r"Among the (\d+) stars with highest luminosity")
        bright_re = re.compile(r"Among the (\d+) brightest stars")
        summary_ids: set[int] = set()
        for lst in grouped_stars.values():
            for s in lst:
                note = s.get("note")
                if not note:
                    continue
                hip = s.get("hip")
                if isinstance(hip, int) and hip in curated_hips:
                    n_curated += 1
                else:
                    if lum_re.search(note) or bright_re.search(note):
                        summary_ids.add(id(s))
                    else:
                        n_auto += 1
        if summary_ids:
            n_auto = len(summary_ids)

        # If invoked as `--only double_stars` prefer compact output showing
        # only the double-star summary and output path so it matches the
        # user's expectation for that mode.
        if only_mode:
            size_mb = stars_file.stat().st_size / 1_048_576
            print(
                f"Double stars   : {n_dbl_stars} stars with {n_pairs} pairs "
                f"({n_phys_pairs} physical, sep >= {min_sep} arcsec)"
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
                f"{BRIGHT_VARIABLE_THRESHOLD}"
            )
            print(
                f"Double stars   : {n_dbl_stars} stars with {n_pairs} pairs "
                f"({n_phys_pairs} physical, sep >= {min_sep} arcsec)"
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
            print(
                f"Variable stars : {n_variable} encoded with amplitude"
                f" >= {BRIGHT_VARIABLE_THRESHOLD}"
            )
            print(
                f"Double stars   : {n_dbl_stars} stars with {n_pairs} pairs "
                f"({n_phys_pairs} physical, sep >= {min_sep} arcsec)"
            )
            print(f"Star notes     : {notes_summary}")
            print(f"Output         : {stars_file} ({size_mb:.2f} MB)")


def _merge_enriched_spectra_from_stars(
    systems: list[dict[str, Any]],
    stars: list[dict[str, Any]],
) -> None:
    """Copy richer dbl.spect strings from enriched stars back into systems."""
    by_wds = {s.get("wds"): s for s in systems if s.get("wds")}
    for star in stars:
        dbl_entries = star.get("dbl")
        if not isinstance(dbl_entries, list):
            continue
        for entry in dbl_entries:
            if not isinstance(entry, dict):
                continue
            wds = entry.get("wds")
            spect = entry.get("spect")
            if not wds or not isinstance(spect, str) or not spect.strip():
                continue
            target = by_wds.get(wds)
            if target is None:
                continue
            current = str(target.get("spect") or "")
            if _prefer_spect_for_export(spect, current):
                target["spect"] = spect


def _prefer_spect_for_export(candidate: str, current: str) -> bool:
    """Prefer composite and longer spectral strings for standalone export."""
    c = _normalize_export_spect(candidate)
    k = _normalize_export_spect(current)
    if not k:
        return True
    c_comp = " / " in c
    k_comp = " / " in k
    if c_comp and not k_comp:
        return True
    if c_comp == k_comp and len(c) > len(k):
        return True
    return False


def _normalize_export_spect(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\s*/\s*", " / ", value.replace("+", "/"))).strip()


if __name__ == "__main__":
    main()
