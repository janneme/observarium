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

# Number of topmost luminous stars to mark with an "extreme luminosity" note.
# These will receive a persistent note like "Among the X stars with highest luminosity".
EXTREME_STARS_NUM: int = 5
# (Use `EXTREME_STARS_NUM` for all top-N annotator defaults.)

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

# ---------------------------------------------------------------------------
# Constellations (Stellarium modern IAU skyculture)
# ---------------------------------------------------------------------------

#: Stellarium modern IAU skyculture index with lines, names and B1875 boundaries.
CONSTELLATIONS_IAU_URL: str = (
    "https://raw.githubusercontent.com/Stellarium/stellarium/master"
    "/skycultures/modern_iau/index.json"
)
CONSTELLATIONS_IAU_FILENAME: str = "stellarium_modern_iau_index.json"

# ---------------------------------------------------------------------------
# Double stars (WDS) and moon features
# ---------------------------------------------------------------------------

#: WDS TSV query via VizieR (HTTPS), requesting relevant columns only.
WDS_VIZIER_URL: str = (
    "https://vizier.cds.unistra.fr/viz-bin/asu-tsv?"
    "-source=B/wds/wds"
    "&-out.max=200000"
    "&-out=WDS,Disc,Comp,Date,sep1,sep2,mag1,mag2,Notes,RAJ2000,DEJ2000"
)
WDS_FILENAME: str = "wds.tsv"

# ORB6 (Sixth Catalog of Orbits of Visual Binary Stars) mirror via VizieR.
# We'll fetch a compact master table with orbital periods (column `P`).
ORB6_VIZIER_URL: str = (
    "https://vizier.cds.unistra.fr/viz-bin/asu-tsv?"
    "-source=J/MNRAS/517/2925/tablea3"
    "&-out.max=200000"
    "&-out=WDS,P"
)
ORB6_FILENAME: str = "orb6.tsv"

#: Supported moon feature types for the public Moon map output.
MOON_FEATURE_TYPES: tuple[str, ...] = (
    "Catena",
    "Crater",
    "Lacus",
    "Mare",
    "Mons",
    "Oceanus",
    "Palus",
    "Sinus",
    "Vallis",
)

#: USGS/IAU Gazetteer Moon nomenclature KMZ with centre points.
MOON_FEATURES_URL: str = (
    "https://asc-planetarynames-data.s3.us-west-2.amazonaws.com/"
    "MOON_nomenclature_center_pts.kmz"
)
MOON_FEATURES_FILENAME: str = "MOON_nomenclature_center_pts.kmz"

#: Minimum apparent angular size in degrees at mean Earth-Moon distance.
#: 0.01° is about 0.6 arcmin and keeps visually meaningful major features.
MIN_MOON_ITEM_SIZE: float = 0.01

#: Mean Earth-Moon distance used for deterministic angular-size filtering.
MEAN_MOON_DISTANCE_KM: float = 384_400.0

#: Circularity threshold for Moon features based on width/height axis ratio.
#: ratio <= 1.05 is treated as circular.
MOON_CIRCULAR_TOLERANCE: float = 1.05
