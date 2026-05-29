# Astronomical Data Sources

Chosen catalogues and data files for Observarium, with licences, canonical
download URLs, and known quirks.

---

## 1. Stars — HYG Database v4.2

| Field | Value |
|---|---|
| **Canonical repo** | <https://codeberg.org/astronexus/hyg> |
| **File** | `data/hyg/CURRENT/hyg_v42.csv.gz` (gzip-compressed CSV) |
| **Licence** | CC-BY-SA 4.0 |
| **Record count** | ~119,614 stars |

**Description:** Merges Hipparcos (HIP), Yale Bright Star, and Gliese (nearby
stars) catalogues. Key columns used: `hip`, `proper`, `ra`, `dec`, `mag`,
`spect`, `dist` (parsecs), `hd`, `sao`, `var`, `var_min`, `var_max`.

**Quirks:**
- The old GitHub repo (`github.com/astronexus/HYG-Database`) is archived
  read-only since February 2025; all future updates are at Codeberg.
- `dist` values flagged as estimated should be passed through with an accuracy
  flag in the output JSON.
- `var_min`/`var_max` absent for non-variable stars — treat missing as no range.
- Europe visibility filter: keep `dec >= -35°`.

---

## 2. DSOs (Messier + NGC/IC) — OpenNGC

| Field | Value |
|---|---|
| **Repo** | <https://github.com/mattiaverga/OpenNGC> |
| **Files** | `database_files/NGC.csv` and `database_files/addendum.csv` |
| **Licence** | CC-BY-SA 4.0 |
| **Latest release** | v20260501 |

**Description:** NGC and IC objects with positions, types, sizes, magnitudes,
and other data. The `addendum.csv` contains non-NGC/IC objects including M40
(Winnecke 4) and M45 (Pleiades) — these must be merged with the main file to
get complete Messier coverage.

**Quirks:**
- M40 and M45 have no NGC/IC designation and appear only in `addendum.csv`.
- B-mag and V-mag have different source provenance per object; V-mag is
  preferred for our magnitude filter.
- Some objects carry a `NED` suffix in their identifier (multiple-component
  galaxies split by NED schema); filter these out or merge as appropriate.
- Large nebulae visible only with extreme equipment (e.g., Barnard's Loop,
  California Nebula) should be excluded per README §2.1c.

---

## 3. Constellation Lines — Stellarium `modern_iau` sky culture

| Field | Value |
|---|---|
| **Repo** | <https://github.com/Stellarium/stellarium> |
| **File** | `skycultures/modern_iau/index.json` |
| **Licence** | GPL-2.0 (Stellarium codebase); IAU data itself is public domain |

**Description:** `index.json` contains a `constellations` array. Each entry
has a `lines` key holding arrays of Hipparcos (HIP) numbers that form the
stick-figure segments. Star IDs cross-reference directly to HYG's `hip` column.

**Quirks:**
- Lines are encoded as arrays of HIP numbers; a star appearing multiple times
  in one array means the line doubles back (star is a vertex of multiple
  segments).
- The same file also contains IAU star names keyed to `"HIP <n>"` strings —
  useful for augmenting HYG proper names.
- Stellarium's GPL-2.0 applies to the software; the underlying IAU constellation
  data is public domain. Extract and store only the data array, not code.

---

## 4. Constellation Boundaries — IAU (via Stellarium `modern_iau`)

| Field | Value |
|---|---|
| **Embedded in** | `skycultures/modern_iau/index.json` (`edges` field) |
| **Original source** | <https://pbarbier.com/constellations/edges_18.txt> |
| **Epoch** | B1875 |
| **Licence** | Public domain (IAU boundary definitions) |

**Description:** The `edges` array in the same `index.json` file encodes IAU
boundary segments. Each record specifies a RA/Dec line segment and the two
neighbouring constellations.

**Quirks:**
- Coordinates are in epoch B1875; must be precessed to J2000 before use.
  Skyfield's `precession` utilities or `astropy` can handle this.
- The format is a space-delimited string: `"seq:seq direction RA Dec RA Dec
  CON1 CON2"`.

---

## 5. Double Stars — Washington Double Star Catalog (WDS)

| Field | Value |
|---|---|
| **VizieR CDS** | <https://cdsarc.cds.unistra.fr/ftp/B/wds> |
| **VizieR catalogue ID** | `B/wds` |
| **TAP endpoint** | `http://tapvizier.cds.unistra.fr/adql/?B/wds` |
| **Licence** | Public domain (US government / NASA-funded USNO) |
| **Record count** | ~157,000 pairs (as of May 2026) |

**Description:** Fixed-width text format. Key columns: WDS designation
(position-based), discoverer code, observation dates, number of observations,
position angle, separation (arcsec), component magnitudes, spectral types,
notes, RA/Dec (J2000). Updated continuously; last VizieR sync 2026-05-07.

**Quirks:**
- The USNO direct URL (`usno.navy.mil`) redirects to a different page; use the
  CDS mirror or VizieR TAP for reliable access.
- Filter by: separation 0.5″–60″, Δmag ≤ 3 for colour contrast, and at least
  one component with mag ≤ 8. This reduces the catalog to a manageable set.
- Spectral types are not available for all pairs; fall back to magnitude
  difference for colour contrast estimation.
- Physical vs. optical pair flag is not explicit; use proper motion similarity
  as a heuristic or rely on notes.

---

## 6. Solar System Positions — Skyfield + JPL DE421

| Field | Value |
|---|---|
| **Library** | Skyfield (`pip install skyfield`) |
| **PyPI** | <https://pypi.org/project/skyfield/> |
| **Source** | <https://github.com/skyfielders/python-skyfield/> |
| **Licence** | MIT |
| **Ephemeris file** | JPL DE421 (`de421.bsp`, ~17 MB, auto-downloaded by Skyfield) |
| **Ephemeris coverage** | 1900–2050 |

**Description:** Pure-Python library. Computes planet, Moon, and Sun positions
with sub-milliarcsecond accuracy. `de421.bsp` is downloaded from NASA on first
use via `load('de421.bsp')`.

**Quirks:**
- Skyfield downloads ephemeris files to the current directory by default;
  configure a persistent `data_prep/sources/` path using a custom `Loader`.
- Apparent magnitudes for planets are not built into Skyfield; use the
  `planetary_magnitude()` function from the `skyfield.almanac` module or
  implement the IAU 2012 magnitude model.
- For the data-prep pipeline, generate a lookup table (position + magnitude
  for each planet per day or hour) rather than computing at request time.

---

## 7. Asteroids — MPC Orbit Database (MPCORB)

| Field | Value |
|---|---|
| **URL (uncompressed)** | <https://www.minorplanetcenter.net/iau/MPCORB/MPCORB.DAT> |
| **URL (gzip)** | <https://www.minorplanetcenter.net/iau/MPCORB/MPCORB.DAT.gz> |
| **Format** | Fixed-width text (MPC packed format) |
| **Licence** | Public domain (NASA-funded, IAU MPC) |
| **Size** | ~300 MB uncompressed; ~100 MB gzip |

**Description:** Orbital elements for all numbered and unnumbered minor planets.
Filter at runtime by absolute magnitude `H` (column 9–13): keep objects that
can reach apparent magnitude ≤ `ASTEROID_MAX_MAGNITUDE` at opposition.

**Quirks:**
- The full file is large; use `MPCORB.DAT.gz` and stream-parse with Python's
  `gzip` module without full decompression.
- MPC uses a packed alphanumeric designation system for unnumbered objects;
  unpack with the `mpc` Python library or implement the unpacking spec from the
  [MPC documentation](https://www.minorplanetcenter.net/iau/MPC_Documentation.html).
- Apparent magnitude requires integration with Skyfield (orbital propagation
  via `sgp4` or Skyfield's `mpc` module) — compute at data-prep time for the
  relevant date range.
- File is updated daily; re-download when refreshing data.

---

## 8. Moon Features — IAU Gazetteer of Planetary Nomenclature

| Field | Value |
|---|---|
| **Website** | <https://planetarynames.wr.usgs.gov/> |
| **Advanced search** | <https://planetarynames.wr.usgs.gov/AdvancedSearch> |
| **GIS downloads** | <https://planetarynames.wr.usgs.gov/GIS_Downloads> |
| **Licence** | Public domain (USGS / IAU / NASA) |

**Description:** Filter by target = Moon and feature types: Catena, Crater,
Dorsum, Lacus, Mare, Mons, Oceanus, Palus, Planitia, Rima, Rupes, Sinus,
Vallis. Columns: feature name, latitude, longitude, diameter (km), approval
status, feature type.

**Quirks:**
- Data downloadable as CSV via the Advanced Search UI or GIS shapefiles.
- Coordinates are in selenographic (Moon-centred) system, not RA/Dec.
- Some feature types (Catena, Dorsum) are not visually useful for a basic Moon
  map; exclude unless clearly prominent.
- Approval status: use only "Approved" features.

---

## 9. Object Images — ESO Image Archive and NASA APOD

| Field | Value |
|---|---|
| **ESO** | <https://www.eso.org/public/images/> |
| **NASA APOD** | <https://apod.nasa.gov/apod/archivepix.html> |
| **Licence** | **Per image** — must be checked individually |

**Description:** A manually curated list of up to ~400×400 px JPEG images for
the most visually interesting objects. Stored in `data_prep/sources/images/`
and bundled in the image ZIP at deploy time.

**Quirks:**
- ESO images are typically released under CC-BY 4.0 for non-ESO-staff images
  or with a custom ESO licence (free for non-commercial educational use); verify
  each image's specific licence on its detail page.
- NASA images are often public domain (government work), but some APOD images
  are copyrighted by the contributing photographer; always check the credit line.
- Build and maintain `data_prep/sources/images/manifest.json` listing object
  ID, filename, credit, and licence for each image.
- Target ≤ 70% JPEG quality, max 400×400 px (README §2.1 field 10).
