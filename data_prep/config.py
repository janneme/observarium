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

#: Amplitude threshold at the bright end of a magnitude-dependent variable-star filter.
#: For a star of apparent magnitude m the effective threshold is:
#:   T(m) = BRIGHT_VARIABLE_THRESHOLD * (1 + 2 * (m / 10) ** 3)
#: This is very flat at low magnitudes and accelerates at faint magnitudes, reaching
#: 3 × BRIGHT_VARIABLE_THRESHOLD at m = 10.
BRIGHT_VARIABLE_THRESHOLD: float = 0.7

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
# Gaia DR3 supplement (fills the gap above the AT-HYG / Tycho-2 ceiling)
# ---------------------------------------------------------------------------

#: Activate the Gaia supplement only when max_mag exceeds this value.
#: Below ~11.5 the AT-HYG/Tycho-2 catalogue is already complete.
GAIA_MAG_THRESHOLD: float = 11.5

#: Hard ceiling applied to Gaia queries regardless of --max-mag.
#: G ≈ 14 gives roughly 5-8 M additional stars (Europe-visible, non-Tycho).
GAIA_DEFAULT_MAX_MAG: float = 14.0

#: Cache filename template for the downloaded Gaia supplement.
#: Parameters: max_mag (numeric) and min_dec (numeric).
GAIA_FILENAME_TEMPLATE: str = "gaia_dr3_m{max_mag:g}_d{min_dec:g}.csv.gz"

# ---------------------------------------------------------------------------
# Deep sky objects (OpenNGC)
# ---------------------------------------------------------------------------

#: OpenNGC main catalogue CSV.
DSO_MAIN_URL: str = (
    "https://raw.githubusercontent.com/mattiaverga/OpenNGC/master/database_files/NGC.csv"
)
DSO_MAIN_FILENAME: str = "openngc_ngc.csv"

#: OpenNGC addendum CSV (non-NGC objects and updates).
DSO_ADDENDUM_URL: str = (
    "https://raw.githubusercontent.com/mattiaverga/OpenNGC/master/database_files/addendum.csv"
)
DSO_ADDENDUM_FILENAME: str = "openngc_addendum.csv"

#: Magnitude ceiling for non-Messier DSOs written to dso.json.
#: Matches the 0.8 * mag formula used by the upload script's per-set filter,
#: applied at the highest available star magnitude (GAIA_DEFAULT_MAX_MAG = 14).
DSO_MAX_MAG: float = round(0.8 * GAIA_DEFAULT_MAX_MAG, 1)

# ---------------------------------------------------------------------------
# Constellations (Stellarium modern IAU skyculture)
# ---------------------------------------------------------------------------

#: Stellarium modern skyculture index with lines, names and B1875 boundaries.
CONSTELLATIONS_IAU_URL: str = (
    "https://raw.githubusercontent.com/Stellarium/stellarium/master/skycultures/modern/index.json"
)
CONSTELLATIONS_IAU_FILENAME: str = "stellarium_modern_index.json"

# ---------------------------------------------------------------------------
# Double stars (WDS) and moon features
# ---------------------------------------------------------------------------

#: WDS TSV query via VizieR (HTTPS), requesting relevant columns only.
WDS_VIZIER_URL: str = (
    "https://vizier.cds.unistra.fr/viz-bin/asu-tsv?"
    "-source=B/wds/wds"
    "&-out.max=200000"
    "&-out=WDS,Disc,Comp,Date,sep1,sep2,mag1,mag2,SpType,Notes,RAJ2000,DEJ2000"
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
    "Dorsum",
    "Lacus",
    "Mare",
    "Mons",
    "Oceanus",
    "Palus",
    "Rima",
    "Satellite Feature",
    "Vallis",
)

#: Raw Gazetteer type -> canonical render/group type. Lets us ingest extra
#: IAU categories without introducing new visual treatments: satellite
#: craters render as ordinary craters, rimae/dorsa (both elongated, linear
#: features) get the same ridge-outline treatment as vallis/mons.
MOON_TYPE_ALIASES: dict[str, str] = {
    "Satellite Feature": "Crater",
    "Rima": "Vallis",
    "Dorsum": "Mons",
}

#: USGS/IAU Gazetteer Moon nomenclature KMZ with centre points.
MOON_FEATURES_URL: str = (
    "https://asc-planetarynames-data.s3.us-west-2.amazonaws.com/MOON_nomenclature_center_pts.kmz"
)
MOON_FEATURES_FILENAME: str = "MOON_nomenclature_center_pts.kmz"

#: Minimum physical bounding-box size (km, longest dimension) for a feature
#: to be ingested at all. Features smaller than this are skipped entirely.
MOON_MIN_ITEM_SIZE_KM: float = 2.0

#: Moon's mean radius, used to convert a feature's bounding box from degrees
#: (selenographic, i.e. as seen from the Moon's own centre) to physical km.
MOON_RADIUS_KM: float = 1737.4

#: Circularity threshold for Moon features based on width/height axis ratio.
#: ratio <= 1.05 is treated as circular.
MOON_CIRCULAR_TOLERANCE: float = 1.05

#: Latitude (degrees) beyond which a feature's Gazetteer min/max longitude
#: bounding box is no longer trustworthy as a "width" — every meridian
#: converges at the poles, so a physically small feature there can record a
#: huge longitude span. See MoonFeaturePipeline._compute_size_axes.
MOON_POLAR_LAT_GUARD_DEG: float = 85.0

#: Moon feature types that are "areas" (seas) rather than point-like
#: features — mirrors client/src/components/MoonCanvas.svelte's AREA_TYPES.
#: Only these types are eligible for real LROC outline geometry below;
#: e.g. crater "Grimaldi" must never pick up the LROC mare-fill patch also
#: named "Grimaldi" (the dark floor material inside that crater, a
#: different and much smaller shape than the crater rim itself).
MOON_AREA_TYPES: frozenset[str] = frozenset({"mare", "oceanus", "lacus", "palus"})

#: LROC (Lunar Reconnaissance Orbiter Camera) team's digitized mare boundary
#: shapefile — real outlines (not bounding boxes), covering named maria,
#: oceani, lacus and palus between 65°N/S. -180..180 domain, matching this
#: pipeline's own longitude convention. Public NASA/PDS data.
#: https://data.lroc.im-ldi.com/lroc/view_rdr/SHAPEFILE_LROC_GLOBAL_MARE
LROC_MARE_URL: str = (
    "https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/"
    "EXTRAS/SHAPEFILE/LROC_GLOBAL_MARE/LROC_GLOBAL_MARE_180.ZIP"
)
LROC_MARE_FILENAME: str = "LROC_GLOBAL_MARE_180.zip"

#: Cap on outline vertices per feature after simplification — keeps
#: moon_features.json compact and canvas rendering cheap; a schematic map
#: doesn't need cartographic-grade vertex density.
MOON_OUTLINE_MAX_POINTS: int = 140

#: Rounding used when synthesizing a mons/montes ridge outline from its
#: bounding box — no real digitized outline exists publicly for these (see
#: moon_pipeline.md). 0 keeps sharp rectangle corners; 1 pulls them in all
#: the way to a full inscribed ellipse.
MOON_RIDGE_CORNER_RADIUS_RATIO: float = 0.8

#: Arc points sampled per ridge corner — enough to read as smooth rather
#: than faceted at typical zoom levels (4 corners x (this + 1) points total).
MOON_RIDGE_CORNER_SEGMENTS: int = 6

#: Vertex count used to sample a circular `geom` boundary — crater/catena/
#: vallis rims, and near-circular area features lacking a real outline.
MOON_CIRCLE_VERTEX_COUNT: int = 28

# ---------------------------------------------------------------------------
# Asteroids (MPC Orbit Database)
# ---------------------------------------------------------------------------

#: MPC Orbit Database (MPCORB.DAT.gz) — orbital elements for minor planets.
#: Source: https://www.minorplanetcenter.net/iau/MPCORB/
#: Format: Fixed-width text, ~100 MB gzipped. Licence: Public domain.
MPCORB_URL: str = "https://www.minorplanetcenter.net/iau/MPCORB/MPCORB.DAT.gz"
MPCORB_FILENAME: str = "MPCORB.DAT.gz"

#: Maximum apparent magnitude at opposition for asteroids to include.
#: Set to 9.0 to match approximate reach of 8×50 binoculars.
ASTEROID_MAX_MAGNITUDE: float = 9.0
