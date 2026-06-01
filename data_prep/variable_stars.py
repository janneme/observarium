"""Variable star pipeline: GCVS via VizieR TAP + SIMBAD HIP crossmatch.

Stage 1 – VizieR TAP queries the General Catalogue of Variable Stars (GCVS)
for stars with peak brightness <= *max_mag*, yielding (VarName, magMax, Min1).

Stage 2 – SIMBAD TAP maps each GCVS name ("V* alf Ori") to its Hipparcos
identifier, discarding stars not in the Hipparcos catalogue.

    The result is cached as ``sources/variable_stars_m{max_mag}.csv``.
"""

import csv
from pathlib import Path
from typing import Any

from astroquery.simbad import Simbad
from astroquery.utils.tap.core import TapPlus

from config import VAR_MAX_MAG

_VIZIER_TAP_URL = "https://tapvizier.cds.unistra.fr/TAPVizieR/tap"

# VizieR TAP: GCVS bright variables with documented amplitude.
_GCVS_ADQL = """\
SELECT "VarName", "magMax", "Min1"
FROM   "B/gcvs/gcvs_cat"
WHERE  "magMax" <= {max_mag}
  AND  "Min1"   IS NOT NULL
"""

# SIMBAD TAP: GCVS identifier → HIP identifier crossmatch.
_HIP_XMATCH_ADQL = """\
SELECT i_gcvs.id AS gcvs_id, i_hip.id AS hip_str
FROM ident i_gcvs
JOIN ident i_hip ON i_gcvs.oidref = i_hip.oidref
WHERE i_gcvs.id IN ({placeholders})
  AND i_hip.id LIKE 'HIP %'
"""

_CSV_FIELDS = ("hip", "min_mag", "max_mag")


def _norm_varname(raw: str) -> str:
    """Collapse internal whitespace: 'alf   Ori' → 'alf Ori'."""
    return " ".join(raw.split())


def _gcvs_simbad_id(var_name: str) -> str:
    """Build SIMBAD 'V* ...' identifier from a GCVS VarName."""
    return f"V* {_norm_varname(var_name)}"


class VariableStarPipeline:
    """Fetches variable-star magnitude ranges from GCVS and caches as CSV.

    The cached file is named ``variable_stars_m{max_mag}.csv`` inside
    *sources_dir*. Use :meth:`run` to (re-)fetch and :meth:`load_index` to
    read the existing cache for use by the star pipeline.
    """

    def __init__(
        self,
        sources_dir: Path,
        max_mag: float = VAR_MAX_MAG,
        cache_dir: Path | None = None,
        debug: bool = False,
    ) -> None:
        self._sources_dir = sources_dir
        self._max_mag = max_mag
        # Use explicit cache dir for downloads/output; fall back to sources
        self._cache_dir = cache_dir or sources_dir
        self._debug = debug

    def csv_path(self) -> Path:
        """Return the path to the cached CSV for this magnitude limit."""
        return self._cache_dir / f"variable_stars_m{self._max_mag:g}.csv"

    def run(self) -> Path:
        """Fetch GCVS + HIP crossmatch, write CSV, return its path."""
        gcvs_rows = self._fetch_gcvs()
        xmatch = self._fetch_hip_xmatch(gcvs_rows)
        rows = self._merge(gcvs_rows, xmatch)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        out = self.csv_path()
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(_CSV_FIELDS)
            writer.writerows(rows)
        if self._debug:
            print(f"Variable stars : {len(rows):,} written \u2192 {out.name}")
        return out

    def _fetch_gcvs(self) -> list[dict[str, Any]]:
        """Query VizieR TAP for GCVS bright variables."""
        tap = TapPlus(url=_VIZIER_TAP_URL)
        job = tap.launch_job(_GCVS_ADQL.format(max_mag=self._max_mag))
        rows: list[dict[str, Any]] = []
        for row in job.get_results():
            var_name = str(row["VarName"]).strip()
            try:
                mag_max = float(row["magMax"])
                min1 = float(row["Min1"])
            except (ValueError, TypeError):
                continue
            rows.append({"var_name": var_name, "mag_max": mag_max, "min1": min1})
        if self._debug:
            print(f"GCVS           : {len(rows):,} entries with magMax <= {self._max_mag}")
        return rows

    def _fetch_hip_xmatch(
        self, gcvs_rows: list[dict[str, Any]]
    ) -> dict[str, str]:
        """Return mapping SIMBAD 'V* ...' id → 'HIP XXXXX' id."""
        simbad_ids = [_gcvs_simbad_id(r["var_name"]) for r in gcvs_rows]
        placeholders = ", ".join(f"'{sid}'" for sid in simbad_ids)
        table = Simbad.query_tap(_HIP_XMATCH_ADQL.format(placeholders=placeholders))
        return {str(row["gcvs_id"]): str(row["hip_str"]) for row in table}

    def _merge(
        self,
        gcvs_rows: list[dict[str, Any]],
        xmatch: dict[str, str],
    ) -> list[tuple[int, float, float]]:
        """Join GCVS amplitude data with HIP crossmatch; return sorted rows.

        Entries where ``Min1 < magMax`` are silently dropped: GCVS stores the
        *amplitude* (not the absolute faint-end magnitude) in ``Min1`` for
        some variable types (DSCTC, ACV, BCEP, …). A genuine faint-end
        magnitude is always numerically larger (dimmer) than ``magMax``.
        """
        results: list[tuple[int, float, float]] = []
        skipped_amplitude = 0
        for row in gcvs_rows:
            if row["min1"] < row["mag_max"]:
                skipped_amplitude += 1
                continue
            simbad_id = _gcvs_simbad_id(row["var_name"])
            hip_str = xmatch.get(simbad_id, "")
            if not hip_str.startswith("HIP "):
                continue
            try:
                hip = int(hip_str[4:])
            except ValueError:
                continue
            results.append((hip, row["mag_max"], row["min1"]))
        if skipped_amplitude and self._debug:
            print(
                f"GCVS           : {skipped_amplitude} entries skipped"
                " (Min1 < magMax \u2014 amplitude notation)"
            )
        return sorted(results)

    def load_index(self) -> dict[int, tuple[float, float]]:
        """Read cached CSV and return a HIP \u2192 (min_mag, max_mag) dict.

        Returns an empty dict (with a warning) if the CSV is absent.
        Run ``--only variable_stars`` first to populate it.
        """
        path = self.csv_path()
        if not path.exists():
            print(
                f"Warning: {path.name} not found. "
                "Run --only variable_stars to fetch variable-star data."
            )
            return {}
        index: dict[int, tuple[float, float]] = {}
        with path.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                index[int(row["hip"])] = (float(row["min_mag"]), float(row["max_mag"]))
        if self._debug:
            print(f"Variable stars : {len(index):,} loaded from {path.name}")
        return index
