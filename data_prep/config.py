"""Application-wide constants for the data preparation pipeline."""

# ---------------------------------------------------------------------------
# Star catalogue
# ---------------------------------------------------------------------------

#: Maximum apparent visual magnitude to include in the star catalogue.
#: An 8×50 finder scope reaches ~9 mag; 8.0 gives a comfortable margin.
MAX_STAR_MAGNITUDE: float = 8.0

#: Minimum declination (degrees) for the Europe visibility filter.
#: −35° covers the southernmost European latitudes with margin.
EUROPE_MIN_DEC: float = -35.0

#: Magnitude range (inclusive) above which a variable star uses [min,max] mag encoding.
VARIABLE_THRESHOLD: float = 1.0

#: Default brightest-magnitude cutoff for the SIMBAD variable-star query.
#: Stars that never reach this brightness at peak are excluded from the index.
VAR_MAX_MAG: float = 4.0

#: AT-HYG v3.3 "reduced to magnitude 11" subset (871k stars, complete to V=11).
#: Source: https://codeberg.org/astronexus/athyg  Licence: CC-BY-SA 4.0
ATHYG_URL: str = (
    "https://codeberg.org/astronexus/athyg/media/branch/main"
    "/data/subsets/athyg_33_reduced_m11.csv.gz"
)
ATHYG_FILENAME: str = "athyg_33_reduced_m11.csv.gz"

#: AT-HYG v3.3 full catalogue, split into two parts (~2.5M stars, complete to V≈17).
#: Download both parts; they share the same header and are processed sequentially.
ATHYG_FULL_URLS: tuple[str, str] = (
    "https://codeberg.org/astronexus/athyg/media/branch/main/data/athyg_v33-1.csv.gz",
    "https://codeberg.org/astronexus/athyg/media/branch/main/data/athyg_v33-2.csv.gz",
)
ATHYG_FULL_FILENAMES: tuple[str, str] = ("athyg_v33-1.csv.gz", "athyg_v33-2.csv.gz")

#: max_mag threshold above which the full catalogue is used instead of the m11 subset.
ATHYG_FULL_MAG_THRESHOLD: float = 11.0

# ---------------------------------------------------------------------------
# Deep sky objects (OpenNGC)
# ---------------------------------------------------------------------------

#: OpenNGC main catalogue CSV.
DSO_MAIN_URL: str = (
    "https://raw.githubusercontent.com/mattiaverga/OpenNGC/master"
    "/database_files/NGC.csv"
)
DSO_MAIN_FILENAME: str = "openngc_ngc.csv"

#: OpenNGC addendum CSV (non-NGC objects and updates).
DSO_ADDENDUM_URL: str = (
    "https://raw.githubusercontent.com/mattiaverga/OpenNGC/master"
    "/database_files/addendum.csv"
)
DSO_ADDENDUM_FILENAME: str = "openngc_addendum.csv"

#: Number of brightest non-Messier DSOs to include.
NON_MESSIER_NUM: int = 250
