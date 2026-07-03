# Implementation Steps

Each step is sized for one focused coding session. Steps are ordered to deliver
a deployable MVP as early as possible, with quizzes and advanced features at the
end. Where behaviour is fully described in the README, only a reference is given
here; this document adds technical detail not present there.

---

## Phase 0 — Research & Project Skeleton

### Step 1: Research astronomical data sources ✅

**Deliverable:** `data/SOURCES.md` — see that file for the confirmed catalogue
files, their licences, download URLs and any known quirks.

---

### Step 2: Project skeleton ✅

**Deliverable:** Repository with directory layout, root `Makefile` skeleton,
`README.md` and `IMPLEMENTATION_STEPS.md` committed.

Suggested monorepo layout:

```
observarium/
├── Makefile                   # make deploy, make dev, make data-prep
├── README.md
├── IMPLEMENTATION_STEPS.md
├── client/                    # Svelte/Vite SPA (npm project)
├── server/                    # Python Lambda + local wrapper
│   ├── handler.py             # Lambda entry point
│   ├── local_server.py        # Thin HTTP wrapper (stdlib http.server)
│   └── requirements.txt
├── data_prep/                 # Data preparation scripts (Python)
│   ├── main.py                # CLI entry point
│   ├── sources/               # Raw downloaded catalogues (git-ignored)
│   ├── output/                # Uncompressed processed data (git-ignored)
│   └── requirements.txt
└── infra/                     # OpenTofu (Terraform-compatible)
    └── main.tf
```

Root `Makefile` targets to stub out: `deploy`, `dev-server`, `dev-client`,
`data-prep`, `data-upload`.

---

## Phase 1 — Data Preparation Pipeline

All steps in this phase produce files in `data_prep/output/`. The CLI entry
point (`data_prep/main.py`) should accept `--only stars`, `--only dso`,
`--object M42` etc. flags as described in **README §3.1.3**.

The final output schema for `objects.json` should be established in Step 3 and
extended in subsequent steps. Top-level keys: `stars`, `dso`, `constellations`,
`double_stars`, `solar_system`, `moon_features`. Each object follows the field
list in **README §2.1** where applicable.

---

### Step 3: Star catalogue pipeline ✅

**Deliverable:** `data_prep/output/stars.json` — produced by
`make data-prep ARGS="--only stars"`. Source: HYG v4.2 (Codeberg). Filter:
mag ≤ 8.0, dec ≥ −35°. Fields: `hip`, `hd`, `sao`, `name`, `ra`, `dec`,
`mag`, `spect`, `clr` (CSS hex), `dist_pc`, `minmag`/`maxmag` (variable stars
only), `const` (absent until Step 6). Null values omitted. 29 unit tests, ruff
clean, pylint 10/10.

---

### Step 3a: Full AT-HYG v3.3 catalogue + variable-star pipeline hardening ✅

**Deliverable:** Star pipeline supports magnitude runs beyond V=11 by
automatically switching from the 871k-star m11 subset to the full 2.5M-star
AT-HYG v3.3 catalogue (two-part download) when `--max-mag > 11`.

Changes made:

- `config.py`: added `ATHYG_FULL_URLS`, `ATHYG_FULL_FILENAMES`,
  `ATHYG_FULL_MAG_THRESHOLD` constants pointing to `athyg_v33-1.csv.gz` and
  `athyg_v33-2.csv.gz` on Codeberg.
- `stars.py` `run()`: selects full catalogue when `max_mag > 11`; downloads
  both parts via `Downloader` (cached after first run).
- `stars.py` `_process()`: handles the split-catalogue layout — part-2 has no
  header row and is read with fieldnames inherited from part-1.
- `stars.py` `_build_star()`: fixed spurious exclusion of stars with no
  parallax distance in AT-HYG (e.g. μ Cep / Garnet Star); only `dist == 0.0`
  (the Sun placeholder) is now excluded.
- `main.py` `_run_stars()`: auto-fetches the variable-star CSV if absent,
  removing the need to run `--only variable_stars` as a separate step.

Verified outputs (all with `--var-max-mag` set appropriately):

| `--max-mag` | Stars     | Variables encoded |
| ----------- | --------- | ----------------- |
| 5           | 1,207     | 10                |
| 6           | 3,725     | 15                |
| 7           | 11,632    | 18                |
| 8           | 33,591    | 80                |
| 9           | 91,734    | 108               |
| 10          | 242,560   | 171               |
| 11          | 634,257   | 185               |
| 12          | 1,445,008 | 190               |

---

### Step 3b: Curated star notes ✅

**README refs:** §2.1 field 11  
**Deliverable:** Notable stars in `stars.json` gain a `note` field with a short
plain-English description (e.g. "brightest star in the sky", "extremely red
carbon star", "fastest-moving star visible to the naked eye").

Technical notes:

- Maintain the notes in `data_prep/notes_stars.csv` with columns:
  `hip` (primary key), `note`.
- `StarPipeline._process` loads the CSV once into a `dict[int, str]` and
  merges it by `hip` during the main loop.
- The field is omitted when absent (consistent with the null-omission policy).
- No external download needed — the CSV is hand-authored and committed to the
  repository.
- Seed the file with at least the ~30 most recognisable named stars: Sirius,
  Canopus, Arcturus, Vega, Capella, Rigel, Procyon, Achernar, Betelgeuse,
  Hadar, Altair, Aldebaran, Antares, Spica, Pollux, Fomalhaut, Deneb, Mimosa,
  Regulus, Adhara, Castor, Gacrux, Shaula, Bellatrix, Elnath, Miaplacidus,
  Alnilam, Alnitak, Mintaka, Gamma Vel, Mira (also variable), Barnard's Star
  (fastest proper motion), 61 Cygni (first star with measured parallax).

---

### Step 4: Deep sky object pipeline ✅

**README refs:** §2.1b, §2.1c, §2.1 fields 1–11  
**Deliverable:** `data_prep/output/dso.json`

Technical notes:

- Source: OpenNGC CSV. Filter: Messier objects (all) + brightest
  `NON_MESSIER_NUM` non-Messier objects excluding large diffuse nebulae
  (OpenNGC type `EN`, `RN`, `DN` with `maj_ax > 60'`).
- Map OpenNGC type codes to the README type vocabulary:
  `OC`→open cluster, `GC`→globular cluster, `G`→spiral/elliptical galaxy
  (use sub-type from `morph` column), `PN`→planetary nebula, `EN`→emission
  nebula, `RN`→reflection nebula, `DN`→dark nebula.
- Size: use `maj_ax` × `min_ax` (arcmin) and `pos_ang` for orientation.
- Central star magnitude for PNe: OpenNGC has `cstar_mag` column.
- Add curated `note` text (README field 11) manually for the most notable
  objects — a CSV sidecar file `data_prep/notes_dso.csv` is sufficient.
- Images will be linked by catalogue number in Step 8.

Implementation notes:

- Implemented in `data_prep/dso.py` with CLI integration in `data_prep/main.py`
  (`python main.py --only dso`).
- Writes `data_prep/output/dso.json` from OpenNGC main + addendum CSV files.
- Includes all Messier objects and the brightest `NON_MESSIER_NUM` non-Messier
  objects, excluding large diffuse nebulae (`EN`/`RN`/`DN` and equivalents)
  with `maj_ax > 60'`.
- Type mapping covers OpenNGC codes used by Messier and non-Messier entries;
  uncommon Messier-only classes are mapped via a fallback to keep full Messier
  coverage.
- Curated notes are loaded from `data_prep/notes_dso.csv` (`id,note`).

---

### Step 5: Constellation data pipeline ✅

**README refs:** §2.1e  
**Deliverable:** `data_prep/output/constellations.json` with lines, boundaries
and names.

Technical notes:

- **Lines:** Stellarium Western skyculture `constellation_lines.fab` file.
  Star IDs are HIP numbers — cross-reference to HYG to get RA/Dec coordinates.
  Store as arrays of `[hip_a, hip_b]` pairs; the client looks up star positions
  at render time.
- **Boundaries:** IAU boundary file uses epoch B1875 coordinates. Precess to
  J2000 using `astropy.coordinates.FK5` → `ICRS` transform.
- **Names:** IAU 3-letter abbreviation + full Latin name + optional common name.
- Assign each star its containing constellation (point-in-polygon test against
  IAU boundaries) and store on the star object — satisfies README field 5.

Implementation notes:

- Implemented in `data_prep/constellations.py` with CLI integration in
  `data_prep/main.py` (`python main.py --only constellations`).
- Source: Stellarium `modern_iau/index.json` downloaded to
  `data_prep/sources/stellarium_modern_iau_index.json`.
- Outputs `data_prep/output/constellations.json` as a dictionary keyed by IAU
  abbreviation (e.g. `And`, `CMa`), each entry containing:
  - `name` (native/IAU name)
  - optional `common` (byname)
  - `lines` as HIP edge pairs `[hip_a, hip_b]`
  - `bounds` as boundary edge segments with J2000 coordinates
    `[[ra_h1, dec_d1], [ra_h2, dec_d2]]`
- Boundary edges are provided by Stellarium in B1875 and are precessed to
  J2000/ICRS using `astropy.coordinates.FK5` -> `ICRS`.
- Stars already carry constellation assignment from AT-HYG `con` and are
  grouped by constellation in the star pipeline.

---

### Step 6: Double star & Moon features pipeline ✅

**README refs:** §2.1f, §2.1g  
**Deliverables:** double-star metadata embedded in
`data_prep/output/stars.m*.json`, plus `data_prep/output/moon_features.json`

**Double stars:**

- Source: WDS via VizieR HTTPS TSV export.
- Inclusion is magnitude-driven: both pair components must be `<= --max-mag`
  (same threshold as stars pipeline).
- Add CLI parameter `--min-double-star-sep` (default `2.0`) and keep upper
  bound at 60″ to represent practical visual pairs.
- Separation is stored as scalar when one measure exists, otherwise as
  `[min,max]` from observed/catalogued values.
- For multi-star systems, keep all pair-wise entries (AB, AC, BC...).
- Where known physical association exists in WDS notes, store
  `"phys": "<components>"` (e.g. `"phys": "AB"`).
- Where WDS notes indicate a non-physical (visual/optical) pair, store
  `"vis": "<components>"` (e.g. `"vis": "AB"`) so callers can
  distinguish confirmed visual pairs from unknown/physical ones.
- When available, attach orbital period information (years) from the ORB6
  orbit catalogue (fetched via VizieR) to pairs as `"period": <years>`.

**Moon features:**

- Source: IAU Gazetteer CSV. Filter: `target = "Moon"`, feature types:
  `Catena`, `Crater`, `Lacus`, `Mare`, `Mons`, `Oceanus`, `Palus`, `Sinus`,
  `Vallis`. Keep: `name`, `lat`, `lon`, `diam_km`, `feature_type`.
- Longitude/latitude here are selenographic (Moon surface coordinates) —
  store as-is; the client renders the schematic Moon map directly (no
  coordinate transform needed).

Implementation notes:

- Implemented `data_prep/double_stars.py` and `data_prep/moon_features.py` with
  CLI integration in `data_prep/main.py`.
- Double-star matching is performed during stars pipeline execution and merged
  into `stars.m*.json` under each star as `dbl` metadata.
- Double stars are filtered by `--max-mag` and `--min-double-star-sep`.
- Moon features currently read from local source file
  `data_prep/sources/moon_features.csv` (columns: `target,feature_type,name,lat,lon,diam_km`),
  then filtered to `target=Moon` and allowed feature types from README.
- Output `data_prep/output/moon_features.json` stores selenographic
  `lat`/`lon` as-is plus `diam_km` when available.

---

### Step 7: Solar system ephemeris pipeline ✅

**README refs:** §2.1d  
**Deliverable:** `data_prep/output/solar_system.json` containing planet
metadata and minor-planet orbital elements. Solar system positions are computed
at runtime in the client using the bundled Astronomy Engine library.

Technical notes:

- Use [Astronomy Engine](https://github.com/cosinekitty/astronomy) — it is a
  single JS file (no WASM, no server call) covering Sun, Moon, planets and
  can compute apparent magnitude. Include it in the Svelte client bundle.
- `solar_system.json` has two sections:
  - `planets`: Array of 7 observable major planets (excludes Earth and Pluto)
    with display metadata (name, symbol, color, inner flag for phase display,
    typical magnitude range).
  - `minor_planets`: Array of brightest asteroids (magnitude ≤
    `ASTEROID_MAX_MAGNITUDE`) with orbital elements (H, G, a, e, i, Ω, ω, M,
    epoch) sourced from MPC MPCORB database. Client computes positions and
    magnitudes at runtime using these elements.
- Minor-planet orbital elements: Source from MPC MPCORB.DAT.gz, filter by
  estimated opposition magnitude and H ≤ 8.0, output includes computed
  `min_mag`/`max_mag` range for visibility planning.
- This step produces `solar_system.json` with planet catalog (inline metadata)
  and minor-planet pipeline (MPCORB download, parsing, filtering). All 129+
  tests passing, ruff clean.

---

### Step 8: Object images pipeline ✅

**README refs:** §2.1 field 10  
**Deliverable:** `data_prep/output/images/` directory with one JPEG per object,
named by catalogue number (e.g. `M042.jpg`, `NGC7293.jpg`).

Technical notes:

- Build a manifest CSV `data_prep/image_sources.csv` with columns:
  `catalogue_id`, `url`, `credit`, `licence`. Populate manually for the most
  interesting ~100–200 objects.
- Download script fetches each URL, resizes to fit within 400×400 using
  `Pillow` (`Image.thumbnail`), converts to JPEG at quality 70.
- Incremental: skip if the output file already exists (re-run is safe).
- Images are referenced in `objects.json` by catalogue number — no separate
  manifest needed at runtime.

Implementation notes:

- Implemented in `data_prep/images.py` with CLI integration in `data_prep/main.py`
  (`python main.py --only images`).
- Manifest stored as JSON (`data_prep/sources/image_sources.json`) with 596 DSO
  entries, each containing: `catalogue_id`, `url`, `verified` (1=validated, 0=template, -1=failed).
- URL validation script (`data_prep/scripts/validate_image_sources.py`) uses HTTP/2
  with full browser security headers (sec-fetch-\*, sec-ch-ua) required by Wikimedia,
  per-domain parallel processing with exponential backoff [10s, 20s, 40s] to handle
  rate limiting intelligently.
- Image download uses `httpx` with HTTP/2 and same browser headers, grouped by domain
  with parallel ThreadPoolExecutor processing and retry logic matching validation script.
- Fixed PIL decompression bomb protection (`Image.MAX_IMAGE_PIXELS = None`) for large
  astronomical images (e.g., M42 Orion Nebula at 18000×18000 pixels).
- `--image-limit` parameter counts only NEW downloads, not already-processed files.
- All 113 verified images successfully processed; output JPEGs are 400×400 thumbnails
  at quality 70, typically 15-50 KB each.

---

### Step 9: Data bundling & `make data-upload` ✅

**README refs:** §3.1.3, §3.1.4, §3.2.2  
**Deliverable:** `make data-upload` bundles object data and images into ZIPs,
generates a manifest, and syncs everything to the configured storage backend.

Storage backend selection:

- Env `STORAGE=local|s3` selects the backend.
- `STORAGE=local` stores artifacts under the repository-root `storage/`
  directory (this folder must be in `.gitignore`).
- `STORAGE=s3` stores artifacts in the S3 data bucket (`DATA_BUCKET`).
- The storage abstraction must be usable from both `data_prep/` and `server/`.

Key namespace (identical across backends):

- `stars_t1.zip` — T1 star CSV (mag ≤ 9.0), single entry `stars_t1.csv`.
- `objects.zip` — merged `objects.json` (DSOs, double stars, constellations,
  solar system, moon features; no star entries).
- `t2_000.zip`, `t2_001.zip`, … — T2 star chunks (mag > 9.0), one entry per
  zone named `{zone:04d}.csv`; headerless rows `z,ra,de,mg,cl,hp,hd,sp,ds,pr,pd`.
- `images.zip` — unchanged; excluded from manifest-driven download.
- `manifest.json` — describes all payload files (excludes `images.zip`).
- `manifest.hash` — hex SHA-256 of `manifest.json`.
- `observations/{username}.json`.

Technical notes:

- **T2 bin-packing:** zones are packed sequentially, accumulating until the
  estimated compressed size (`raw_bytes / 3.0`) exceeds `TARGET_CHUNK_BYTES`
  (5 MB), then a new chunk starts. Produces `t2_NNN.zip` files of roughly 5 MB
  each (last chunk smaller).
- **`manifest.json` format:**
  ```json
  {
    "version": "YYYY-MM-DD",
    "stars_t1": {"filename": "stars_t1.zip", "hash": "sha256:…", "size": 12345},
    "objects":  {"filename": "objects.zip",  "hash": "sha256:…", "size": 12345},
    "t2_chunks": [
      {"filename": "t2_000.zip", "hash": "sha256:…", "size": 12345, "zones": [0,1,…]},
      …
    ]
  }
  ```
- **`manifest.hash`:** plain-text hex SHA-256 of `manifest.json`; used by
  `GET /data-hash` so the client can detect data updates with one small request.
- Change detection: compare SHA-256 of each local artifact against the
  backend's stored copy; sync only if different.
- `images.zip` is built and synced as before but is intentionally excluded from
  the manifest — it uses a separate pre-signed URL flow via `GET /images-url`.
- `make data-upload` is called as step 3 of the full `make deploy` sequence.

Validation order (mandatory):

1. First run and verify with `STORAGE=local` (no cloud dependencies).
2. Only after verifying local results, re-run with `STORAGE=s3`.

---

### Step 9a: Storage abstraction retrofit (server + data prep)

**Deliverable:** A shared storage abstraction layer that is imported and used
by both `data_prep/` and `server/`, so the solution can run fully locally.

Technical notes:

- Provide a small backend interface that supports at least:
  - read/write bytes by key
  - read/write JSON by key
  - existence checks
  - retrieving a stable content identifier (e.g. SHA-256 for local mode; ETag
    or metadata hash for S3 mode)
- Local backend must resolve the repository root reliably (do not assume
  current working directory is the repo root).
- `server/` must not require boto3/S3 connectivity when `STORAGE=local`.

---

## Phase 2 — AWS Infrastructure & Lambda

### Step 10: Terraform infrastructure ✅

**README refs:** §3.1.4, §3.2.1–§3.2.5  
**Deliverable:** `terraform apply` creates all AWS resources; outputs Lambda
Function URL and client bucket website endpoint.

Resources to define in `infra/main.tf`:

| Resource                       | Key settings                                                                                                                                         |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `aws_s3_bucket` (data)         | Private; no public access block override                                                                                                             |
| `aws_s3_bucket` (client)       | Static website hosting enabled; public read bucket policy                                                                                            |
| `aws_cognito_user_pool`        | Password policy, no self-registration                                                                                                                |
| `aws_cognito_user_pool_client` | `ALLOW_USER_PASSWORD_AUTH` flow; no client secret (public client)                                                                                    |
| `aws_iam_role` + policy        | Lambda execution role: `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` on data bucket; `logs:*` on the log group                                   |
| `aws_cloudwatch_log_group`     | `/aws/lambda/observarium`, retention 30 days                                                                                                         |
| `aws_lambda_function`          | Python 3.12, handler `handler.lambda_handler`, env vars: `DATA_BUCKET`, `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`, `COGNITO_REGION`                |
| `aws_lambda_function_url`      | `authorization_type = "NONE"`, CORS: allow origin = client bucket website URL, methods GET/POST/DELETE/OPTIONS, headers Content-Type + Authorization |

Create initial Cognito user manually with `aws cognito-idp admin-create-user`
(no self-service signup needed).

Implementation notes:

- Deployed to region `eu-central-1` with AWS profile `personal`.
- Created 15 AWS resources: 2 S3 buckets (data + client website), Cognito User
  Pool + Client, IAM role + policy, CloudWatch Log Group, Lambda Function with
  Function URL, random ID for unique bucket names, bucket policies and
  configurations.
- **Critical fix:** As of October 2025, Lambda Function URLs with
  `authorization_type = "NONE"` require **two** permissions in the resource-based
  policy:
  1. `lambda:InvokeFunctionUrl` with condition `lambda:FunctionUrlAuthType = "NONE"`
  2. `lambda:InvokeFunction` with condition `lambda:InvokedViaFunctionUrl = "true"`
- Terraform's `aws_lambda_function_url` resource only creates the first
  permission automatically. The second must be added via
  `aws_lambda_permission` resource with `--invoked-via-function-url` flag (CLI)
  or imported into Terraform state.
- See: https://docs.aws.amazon.com/lambda/latest/dg/urls-auth.html
- Outputs:
  - Data bucket: `observarium-data-0b5ad51e`
  - Client bucket: `observarium-client-0b5ad51e`
  - Client website: `http://observarium-client-0b5ad51e.s3-website.eu-central-1.amazonaws.com`
  - Lambda URL: `https://qswhlcrn6nbfwirq4kk3ycohz40nefmg.lambda-url.eu-central-1.on.aws/`
  - Cognito User Pool: `eu-central-1_7lQBM35tr`
  - Cognito Client ID: `7tunopdnaetvaf561vo330eih5`
- **`STORAGE = "s3"` Lambda env var is mandatory.** Without it the Lambda falls
  back to `LocalBackend`, which tries to create `/var/storage` on Lambda's
  read-only filesystem and crashes immediately with `OSError: Read-only file
  system`. Set in `main.tf` under `environment.variables`.
- **S3 CORS configuration required for pre-signed URL downloads.** Browsers
  enforce CORS on `fetch()` requests, including requests to pre-signed S3 URLs.
  The data bucket must have an `aws_s3_bucket_cors_configuration` resource
  allowing `GET` from `*`; otherwise the browser blocks the download even though
  the pre-signed URL itself is valid.
- **`deploy-lambda` Makefile target stages the zip via S3.** The Lambda zip
  including manylinux wheels exceeds ~60 MB, above the 70 MB direct HTTP upload
  limit. The target uploads to `s3://<data-bucket>/_lambda/lambda_function.zip`
  first, then calls `aws lambda update-function-code --s3-bucket --s3-key`.
  Wheels must be installed with `--platform manylinux2014_x86_64
  --python-version 3.12 --only-binary :all:` for Linux/x86_64 compatibility.

---

### Step 11: Lambda skeleton + local dev server ✅

**README refs:** §3.1.2  
**Deliverable:** Lambda returns `{"status": "ok"}` for a health-check request;
local dev server replicates the same behaviour.

Technical notes:

- `server/handler.py`: top-level router parses `event["rawPath"]` and
  `event["requestContext"]["http"]["method"]` to dispatch to handler functions.
- `server/local_server.py`: `http.server.BaseHTTPRequestHandler` subclass that
  constructs a Lambda-shaped `event` dict from the HTTP request and calls
  `handler.lambda_handler`. No external dependencies beyond stdlib.
- `make dev-server` runs `python server/local_server.py --port 8787`.
- Install `boto3`, `PyJWT`, `cryptography` (for JWKS verification) in
  `server/pyproject.toml` (using `uv` package manager, not requirements.txt).
- CORS: add `Access-Control-Allow-Origin`, `Access-Control-Allow-Headers`,
  and `Access-Control-Allow-Methods` headers to every response in a shared
  `build_response()` helper. Handle `OPTIONS` preflight in the router.

Implementation notes:

- Created `server/pyproject.toml` with dependencies: boto3 ≥1.35.0, PyJWT ≥2.9.0,
  cryptography ≥43.0.0 (no build-system section needed for non-package projects).
- Implemented full HTTP router in `handler.py`:
  - `build_response()` helper adds CORS headers to all responses
  - Routes: `GET /` (health check), `POST /login`, `GET /manifest`,
    `GET /images-url`, `GET /data-hash`, `GET /observations`,
    `POST /observations`, `DELETE /observations/{date}`
  - All endpoints except health check return 501 (not yet implemented) with
    descriptive error messages
  - 404 for unknown routes
  - OPTIONS method handled for CORS preflight
- Implemented `local_server.py` with full Lambda Function URL event emulation:
  - Constructs Lambda event dict from HTTP request with proper structure
    (version, rawPath, requestContext.http.method, headers, body, etc.)
  - Handles GET, POST, DELETE, OPTIONS methods
  - Generic error handling returns 500 on exceptions
  - Runs on port 8787 by default
- Created `server/Makefile` with targets: `dev` (runs local server), `sync`
  (installs dependencies), `lint`, `test`
- Updated root `Makefile` to delegate `dev-server` to `server/Makefile`
- Deployed updated Lambda function to AWS; all endpoints working:
  - `GET /` returns `{"status": "ok"}` with 200
  - Other endpoints return appropriate 501/404 responses
- **CORS ownership split:** `build_response()` must NOT add
  `Access-Control-Allow-Origin` headers. Lambda Function URL config injects
  them in production; `local_server.py` injects them for local dev. If the
  handler also adds them the browser receives duplicate headers and rejects
  the request with a CORS error.
- **`run.py` process group shutdown:** `make dev-server` spawns `make` which
  spawns `python3 local_server.py`. `process.terminate()` on the outer `make`
  process does not propagate to its children. Fixed by launching each subprocess
  with `start_new_session=True` (own process group) and sending `SIGTERM` to
  the entire group via `os.killpg`; waits 3 s then `SIGKILL` if still alive.
- **Vite env file precedence:** to override `VITE_SERVER_URL` for a local cloud
  test, create `client/.env.development.local` (highest precedence). A plain
  `client/.env.local` is shadowed by `client/.env.development` and will be
  ignored during `npm run dev`.

---

### Step 12: Lambda — authentication ✅

**README refs:** §3.2.1 (user login), §3.2.3  
**Deliverable:** `POST /login` returns a Cognito access token.

Technical notes:

- Call `boto3` `cognito-idp` `initiate_auth` with
  `AuthFlow="USER_PASSWORD_AUTH"` and `AuthParameters={"USERNAME": ..., "PASSWORD": ...}`.
- On success return `{"access_token": ..., "expires_in": ...}`.
- On `NotAuthorizedException` / `UserNotFoundException` return HTTP 401 with a
  generic message (do not distinguish between wrong user and wrong password).
- The client stores the returned token in `sessionStorage` (README §2.3).
- JWT verification helper (for subsequent endpoints): fetch Cognito JWKS from
  `https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json`,
  cache in module-level variable (warm Lambda reuse), verify with `PyJWT`
  `decode()` using RS256 and the matching public key. Raise HTTP 401 if invalid.

---

### Step 13: Lambda — data endpoints ✅

**README refs:** §3.2.1 (read objects, read images), §3.2.2  
**Deliverable:** `GET /manifest` returns the full manifest with pre-signed
download URLs; `GET /images-url` returns a pre-signed URL for `images.zip`;
`GET /data-hash` returns the SHA-256 of `manifest.json`.

Technical notes:

- `GET /manifest` requires a valid Cognito JWT (Step 12). Reads `manifest.json`
  from the storage backend, then augments each entry (`stars_t1`, `objects`, and
  every element in `t2_chunks`) with a `url` field pointing to a pre-signed
  GET URL. Returns the augmented manifest as JSON.
- `GET /images-url` requires a valid JWT and returns a pre-signed URL for
  `images.zip` (unchanged from the original design).
- `GET /data-hash` (no authentication) reads `manifest.hash` from storage and
  returns `{"hash": "<hex-sha256>"}`. Used by the client to detect data updates
  with a single small request before deciding whether to re-download.

---

### Step 13b: Data endpoints — support `STORAGE=local` via storage backend ✅

**Deliverable:** `GET /manifest`, `GET /images-url`, and `GET /data-hash`
work in both `STORAGE=local` and `STORAGE=s3` modes by using the shared storage
abstraction.

Technical notes:

- `STORAGE=s3`: pre-signed S3 GET URLs with `ExpiresIn=300` (5 minutes) for all
  manifest entries and `images.zip`.
- `STORAGE=local`: `backend.generate_presigned_get(key)` returns
  `http://localhost:8787/local-storage/{key}`, which the local server streams
  directly from the `storage/` directory. No change needed in handler logic —
  the backend abstraction handles both cases transparently.
- `/data-hash` reads `manifest.hash` from backend in both modes (plain-text
  SHA-256 written by `data_upload.py` during bundle generation).

---

### Step 14: Lambda — observation CRUD

**README refs:** §3.2.1 (add/modify/delete observations), §3.2.2  
**Deliverable:** Full observation sync API.

Technical notes:

- Storage: one JSON file per user in the data bucket at key
  `observations/{username}.json`. `username` is extracted from the verified
  Cognito JWT `sub` claim.
- `GET /observations` — reads and returns the file (empty array `[]` if not
  found).
- `POST /observations` — accepts the full updated observation array in the
  request body; overwrites the S3 object. Conflict resolution is last-write-wins
  (acceptable for single-user personal use; README §3.2.2 note).
- `DELETE /observations/{date}` — reads the file, removes the entry for the
  given date, writes back.
- Request bodies are JSON; validate that the top-level value is an array before
  writing.

---

### Step 14b: Observation CRUD — support `STORAGE=local` via storage backend

**Deliverable:** Observation CRUD persists without AWS when `STORAGE=local`, by
using the shared storage abstraction layer.

Technical notes:

- Use the same key scheme in both modes: `observations/{username}.json`.
- `STORAGE=local`: store and read observations under the repository-root
  `storage/` directory (gitignored), with the same logical key layout as S3.
- `STORAGE=s3`: preserve existing S3 behaviour.

---

## Phase 3 — Client Foundation (MVP)

### Step 15: Svelte project setup + color scheme system ✅

**README refs:** §2.2a, §3.1.1  
**Deliverable:** Vite + Svelte 4 project in `client/` with working daily/nightly
theme switching.

Technical notes:

- Scaffold: `npm create vite@latest client -- --template svelte`.
- Color scheme: store active scheme in a Svelte writable store. Apply as a
  `data-theme="nightly"` attribute on `<body>`. Define all colours as CSS custom
  properties in two `:root[data-theme]` blocks. Nightly palette: background
  `#000`, primary content `#cc0000` (red), accent `#0000cc` (blue), no green.
- Full-screen + no zoom: `<meta name="viewport" content="width=device-width,
initial-scale=1, maximum-scale=1, user-scalable=no">` plus CSS
  `html, body { height: 100%; overflow: hidden; touch-action: none; }`.
- `make dev-client` runs `npm --prefix client run dev`.

---

### Step 16: Custom keyboard engine ✅

**README refs:** §2.2d  
**Deliverable:** Reusable `<CustomInput>` and `<CustomTextarea>` Svelte
components that accept all text input without triggering the system keyboard.

**Status:** Implemented in `client/src/components/CustomInput.svelte`, `client/src/components/CustomTextarea.svelte`, and `client/src/components/OnScreenKeyboard.svelte` — includes CZ/EN layouts, Shift/Caps, dead-key composition for Czech accents, visible caret, arrow navigation, and uniform key sizing.

Technical notes:

- Each component renders a styled `<div>` that displays the current value with
  a blinking cursor (CSS `animation: blink 1s step-end infinite`).
- Internal state: `value` (string), `cursorPos` (integer index).
- Operations exposed to the on-screen keyboard via a Svelte store or context:
  `insertChar(ch)`, `backspace()`, `cursorLeft()`, `cursorRight()`,
  `cursorUp()` / `cursorDown()` (textarea only).
- A single hidden `<input type="hidden">` keeps the value in sync for any
  form-adjacent usage (no focus, no keyboard trigger).
- The `<OnScreenKeyboard>` component renders two layouts (Czech / English)
  switchable by a toggle key. Key rows to include for Czech: standard QWERTZ
  plus `á č ď é ě í ň ó ř š ť ú ů ý ž`. Shift state handled internally.
- `<CustomTextarea>` wraps text at component width (measure characters in a
  hidden `<canvas>` using `measureText`); cursor line/column derived from
  `cursorPos` + wrap positions.
- Suppress any native focus on real inputs elsewhere: ensure no `<input>` or
  `<textarea>` without `type="hidden"` is present in components that use the
  custom keyboard.

---

### ✅ Step 17: Welcome screen + IndexedDB setup + data loading

**Status:** Completed 2026-06-10

**README refs:** §5.1, §2.3  
**Deliverable:** First-run screen that authenticates, fetches data via
URLs returned by the API (pre-signed in `STORAGE=s3`, direct local routes in
`STORAGE=local`), unpacks ZIPs with JSZip, and stores everything in IndexedDB.

Technical notes:

- IndexedDB schema (use the `idb` npm library for a Promise-based wrapper):
  - Store `objects` — keyPath `id` (e.g. `"star_HIP71683"`), one record per
    DSO/double-star/etc. Index `by_zone` on field `zone` (integer sky-grid
    cell, DB version 2 — see sky-zone index note below). Stars are no longer
    stored here; see two-tier star storage note below.
  - Store `images` — keyPath `catalogueId`, value is a Blob.
  - Store `observations` — keyPath `date` (ISO date string).
  - Store `meta` — keyPath `key`; used for `dataHash`, `lastSync`,
    `telescopes`, `eyepieces`, `findingPaths`, `quizStates`, and the
    Tier-1 star blob (`stars_t1`).
  - Store `zones_t2` — keyPath `zone`; one record per 5°×5° sky cell, value
    is a CSV blob of Tier-2 stars (mag > 9.0). Added in DB version 3.
- **Sky-zone spatial index (DB version 2):** every DSO and double-star record
  carries a `zone` integer identifying its 5°×5° sky-grid cell, indexed under
  `by_zone`.
  - Zone formula: `dec_cell = clamp(floor((dec+90)/5), 0, 35)`,
    `ra_cell = floor(ra/5) % 72`, `zone = dec_cell * 72 + ra_cell`.
    Gives 2592 cells (72 RA × 36 Dec).
  - Within each Dec band the zone integers are contiguous, enabling one
    IDB range query per band. RA wrap-around (viewport crossing 0°/360°) is
    handled with two range queries per affected Dec band.
  - `computeZone(ra_deg, dec_deg)` is exported from `db.js` and called during
    `parseObjects` in `WelcomeScreen.svelte` for DSOs and double stars.
  - DB version bump from 1 → 2 creates the `by_zone` index in the `upgrade`
    callback.
- **Two-tier star storage (DB version 3):** stars are split by magnitude rather
  than stored in the `objects` store.
  - Tier-1 (mag ≤ 9.0): stored as a single CSV blob in `meta` under key
    `stars_t1`. Parsed once into `_tier1Cache` (in-memory array, sorted by mag
    ascending) and reused for all subsequent queries without hitting IDB.
  - Tier-2 (mag > 9.0): stored as per-zone CSV blobs in `zones_t2`, one record
    per 5°×5° cell. Only the zones overlapping the current viewport are fetched,
    and only when `mag_limit > T1_MAG_LIMIT` (9.0).
  - Write helpers: `storeTier1Blob(csvText)` (puts blob in `meta`, invalidates
    cache) and `bulkPutZoneT2Blobs(items)` (batch-writes zone records).
  - DB version 3 upgrade creates `zones_t2` and clears the `objects` store
    (stale star rows from prior schema are removed; fresh data is reloaded as
    CSV blobs on next download).
  - `getObjectsInArea(ra_min, ra_max, dec_min, dec_max, mag_limit)` queries
    three sources in order: (1) Tier-1 in-memory cache, (2) Tier-2 `zones_t2`
    blobs (skipped when `mag_limit ≤ T1_MAG_LIMIT`), (3) `objects` store for
    DSOs and double stars.
  - RA full-sky guard: `_inRA()` returns `true` unconditionally when
    `span = ra_max − ra_min ≥ 360°`, preventing a pathological tiny window
    that modulo arithmetic would otherwise produce at wide FOVs. The same guard
    is present in `_zonesForArea()`.
- Loading sequence (README §5.1): call `POST /login` → store token in
  `sessionStorage` → call `GET /manifest` → read `completedChunks` from
  IDB meta → compute `totalBytes` (sum of `size` for incomplete entries) →
  fetch and ingest `stars_t1.zip` via `ingestT1` (`storeTier1Blob`) →
  fetch and ingest `objects.zip` via `ingestObjects` (`bulkPutObjects`, `setMeta`
  for constellations/solar_system/moon_features) → for each `t2_chunks` entry
  not already completed: fetch and ingest `t2_NNN.zip` via `ingestChunk`
  (`bulkPutZoneT2Blobs`, `markChunkComplete`) → call `storeManifest` to persist
  manifest sans URLs → fetch images via `GET /images-url` → call
  `GET /observations` → insert into `observations` store.
- Resume support: `completedChunks` (IDB meta key) tracks finished chunk
  filenames; already-completed chunks are skipped on reload.
- Progress accuracy: `totalBytes` is known before any download starts (sum of
  `size` fields for incomplete entries); `objectsProgress` tracks exact byte
  offset across sequential chunk downloads.
- Per-chunk progress: `onChunkProgress(chunkSize)` returns a callback that
  maps `[0..1]` download progress for one chunk into the global `[0..1]`
  progress scale.
- Progress bar: percentage computed from streaming `Content-Length` via
  `fetchWithProgress`; images progress splits 70% network / 30% JSZip unpack.
- After loading, navigate to Main Screen via Svelte client-side routing
  (use `svelte-spa-router`).

---

### Step 18: Sky rendering engine ✅

**README refs:** §5.2 (first half), §2.1e  
**Deliverable:** A `SkyCanvas` Svelte component that projects RA/Dec coordinates
onto a 2D canvas given a centre point, FOV, and rotation.

Technical notes:

- **Projection:** Gnomonic (tangent-plane) projection — standard for small-FOV
  star charts. Given centre `(RA₀, Dec₀)`, FOV, and canvas dimensions, map each
  star's `(RA, Dec)` to pixel `(x, y)`.
- **Formulas** (all angles in radians):
  ```
  Δα = RA − RA₀
  cos_c = sin(Dec₀)·sin(Dec) + cos(Dec₀)·cos(Dec)·cos(Δα)
  x_proj = cos(Dec)·sin(Δα) / cos_c
  y_proj = (cos(Dec₀)·sin(Dec) − sin(Dec₀)·cos(Dec)·cos(Δα)) / cos_c
  x_px = W/2 + x_proj · (H / FOV_rad)
  y_px = H/2 − y_proj · (H / FOV_rad)  ← y-axis flipped; scale uses H
  ```
- **Alt/Az for horizon:** Use Astronomy Engine `Horizon()` to convert
  `(RA, Dec)` → `(Altitude, Azimuth)` for current time and location.
  Objects with Altitude < 0 are below the horizon.
- **Rotation:** Apply a 2D rotation matrix around the canvas centre to support
  arbitrary sky rotation (used in quizzes and Finder View).
- Write unit tests for the projection math with a few known star positions.

Implementation notes:

- `client/src/lib/skymath.js`: pure-math module (no DOM). Exports
  `projectGnomonic(ra, dec, ra0, dec0)` → `{x, y}` (normalised), `null` when
  `cos_c ≤ 0`; `toPixel(x, y, W, H, fovDeg, rotation)` → `{px, py}`;
  `projectToPixel` (convenience wrapper); `isOnScreen(px, py, W, H, margin)`.
  Scale factor is `H / toRad(fovDeg)` so FOV is the vertical field of view.
- `client/src/lib/skymath.test.js`: Vitest unit tests — centre projects to
  `(W/2, H/2)`, pole offset reaches top edge, RA wrap-around, rotation matrix,
  and behind-plane null return.
- `client/src/lib/horizon.js`: thin `astronomy-engine` wrapper. Exports
  `getLST`, `getAltitude`, `isAboveHorizon`, `zenith` (RA = LST, Dec = lat).
- `client/src/components/SkyCanvas.svelte`: canvas component. Props: `ra0`,
  `dec0`, `fov`, `rotation`, `objects`, `lat`, `lon`, `time`. Tracks canvas
  size with `ResizeObserver`. RAF loop redraws only when `dirty = true`.
  `updateAboveMap` pre-computes per-object `isAboveHorizon` on each
  `objects`/`lat`/`lon`/`time` change and stores results in a `Map` keyed
  by object `id` — avoids calling Astronomy Engine once per star per frame.
- **Horizon overlay:** 72 azimuth sample points at altitude = 0 are converted
  to equatorial coordinates via direction cosines
  (`dec = arcsin(cos(φ)·cos(az))`, `ha = atan2(−sin(az), −sin(φ)·cos(az))`),
  projected, sorted by canvas-x, and the below-horizon region filled with a
  semi-transparent overlay plus a dashed horizon line. In gnomonic projection
  the horizon is a straight line, so edge extrapolation is exact.

---

### Step 19: Main Screen — star & DSO rendering ✅

**README refs:** §5.2, §2.1 fields 1–9  
**Deliverable:** Main Screen renders stars and DSOs correctly scaled by magnitude,
with horizon boundary and FOV-aware magnitude filtering.

Technical notes:

- **Adaptive magnitude limit** — logarithmic formula anchored so each halving
  of FOV raises the limit by 1 magnitude (constant apparent star density):
  ```js
  // FOV_FOR_STAR_MAG_5=480: fov=240→6, fov=120→7, fov=60→8, fov=30→9,
  //   fov=15→10, fov=7.5→11, fov=3.75→12 (hard cap).
  const FOV_FOR_STAR_MAG_5 = 480
  function adaptiveMagLimit(fovDeg) {
    return Math.min(12, Math.max(5, 5 + Math.log2(FOV_FOR_STAR_MAG_5 / fovDeg)))
  }
  ```
  Used by `SkyCanvas` to decide which objects to render on the canvas.

- **Step-function mag limit for DB queries** — a coarser step function maps
  FOV to a fetch mag limit for `getObjectsInArea`. This avoids re-fetching IDB
  on every pixel of zoom:
  ```js
  function fovToMagLimit(f) {
    if (f >= 60) return 6
    if (f >= 30) return 7
    if (f >= 20) return 8
    if (f >= 10) return 10
    return 12
  }
  ```
  `MainScreen` tracks `loadMagLimit = fovToMagLimit(fov)` after each fetch and
  triggers a reload when zooming in raises the limit (`fovToMagLimit(fov) > loadMagLimit`).

- **DSO magnitude limit** — tied to the star limit, offset to match extended-
  object visual brightness relative to stars:
  ```js
  const dsoMagLim = 8 + 0.5 * (magLim - 5)
  ```
  Anchored at (starMag=5 → dsoMag=8) and (starMag=13 → dsoMag=12).
  DSOs without a recorded magnitude default to mag=8 (always shown).

- **Dynamic star radius** — fixed-range linear interpolation: stars are always
  rendered as points between `MIN_R` and `MAX_R` pixels regardless of FOV.
  Zooming in reveals more faint stars but does not enlarge existing ones —
  consistent with the visual experience in a telescope where stars remain points:
  ```js
  const BRIGHT_MAG = 2.0
  const MIN_R = 1.2   // faintest visible star, any FOV
  const MAX_R = 4.5   // brightest star (Sirius-class), any FOV
  function starRadius(mag) {
    const m = Array.isArray(mag) ? mag[0] : mag  // double stars store [primary, secondary]
    const magLim = adaptiveMagLimit(fov)
    const t = Math.max(0, Math.min(1, (magLim - m) / (magLim - BRIGHT_MAG)))
    return MIN_R + (MAX_R - MIN_R) * t
  }
  ```
  At any FOV, the brightest stars render at 4.5 px and the faintest at 1.2 px.
  Stars brighter than `BRIGHT_MAG` are clamped to `MAX_R`; this is intentional —
  at high zoom a mag 1 and mag 5 star may share the same rendered size.

- **Two-pass rendering** in `draw()`:
  - Pass 1: DSOs filtered by `dsoMagLim`; drawn first so stars paint on top.
  - Pass 2: stars and double stars filtered by `magLim`.
  - Stars missing a magnitude value (`mag == null`) are excluded in pass 2
    (they are not in the catalog at all); DSOs missing a magnitude default
    to 8 and pass the filter.

- **DSO symbols**: canvas shapes per type. When the angular size maps to less
  than `DSO_SYMBOL_THRESHOLD × min(W,H)` pixels, a fixed-size symbol
  (`SYM_R = 8 px`) is drawn; otherwise a size-proportional shape is used.
  Types: open cluster (dashed circle), globular cluster (circle + cross),
  planetary nebula (circle + tick marks), spiral/elliptical galaxy (ellipse
  at orientation angle), dark nebula (dashed square), emission/reflection
  nebula (open square), galaxy cluster (pentagon), quasar/BL Lac (× cross).

- **Double star marker**: drawn as a normal star dot (via `drawStar`) plus an
  outer ring at `starRadius + 2.5 px`, rendered above-horizon only.

- **Star colour**: nightly mode renders all stars in `#e06a5a` (desaturated
  red to preserve dark-adaptation); daily mode uses the spectral `clr` field
  from the catalog. Below-horizon objects use `globalAlpha = 0.22`/`0.20`.

- **Spatial query** (`MainScreen.svelte`): loads objects via
  `getObjectsInArea(ra0 − margin, ra0 + margin, dec0 − margin, dec0 + margin,
  fovToMagLimit(fov))` where `margin = fov × 1.5`. After each fetch,
  `loadRa0`, `loadDec0`, `loadMargin`, and `loadMagLimit` are recorded.
  `maybeReload()` issues a fresh query when any of the following hold:
  - View centre drifted more than 50% of `loadMargin` in RA or Dec.
  - FOV has grown beyond what was loaded (`fov > loadMargin / 1.5`).
  - Zooming in raises the step-function mag limit (`fovToMagLimit(fov) > loadMagLimit`).

  A `fetching` flag prevents concurrent DB queries.

- **Keyboard navigation** (`MainScreen.svelte`):
  - `+`/`=`: zoom in → `fov × 0.80`, clamped to minimum 5°.
  - `-`: zoom out → `fov × 1.20`, clamped to maximum 180°.
  - Arrow keys: pan by `fov × 0.50`; RA step is divided by `cos(dec)` so
    that the angular distance on sky stays constant at all declinations.
  - After every key event `maybeReload()` is called to trigger re-fetch
    if the new view is outside the already-loaded area.

---

### Step 20: Main Screen — interactions ✅

**README refs:** §5.2 (interactions), §4.1 (FOV circle toggle)  
**Deliverable:** Pan, pinch-zoom, tap-to-select, FOV circle, and boundary
clamping all work on mobile.

Technical notes:

- **Touch events:** use `pointermove`/`pointerdown`/`pointerup` (works for
  mouse and touch). Track active pointer IDs to distinguish single-finger pan
  from two-finger pinch.
- **Pan:** translate `(RA₀, Dec₀)` along the inverse projection by the pixel
  delta. Clamp so the rendered area never includes declinations outside the
  European visibility range (README §5.2 boundary rule).
- **Pinch-zoom:** compute distance ratio between two pointers across frames;
  multiply FOV by inverse ratio. Clamp to `[NORMAL_VIEW_MIN_FOV, NORMAL_VIEW_MAX_FOV]`.
- **Tap selection:** on `pointerup` with no movement (`TAP_THRESHOLD = 5` px),
  find all rendered objects within `TAP_RADIUS = 20` device pixels of the tap
  point.
  - **Zero hits:** deselect (set `selectedObject` store to `null`).
  - **One hit:** toggle selection — if the tapped object is already selected,
    deselect it; otherwise select it. `ObjectDetails` is never opened
    automatically from a sky tap.
  - **Multiple hits:** open the **loupe overlay** (`LoupePanel`) centred on the
    centroid of the hit objects. FOV is derived from the minimum pairwise
    angular separation so all candidates are visible. See Loupe notes below.
  - Selected object is stored in the `selectedObject` writable store
    (`stores/selectedObject.js`). `ObjectDetails` visibility is independent,
    controlled by the `objectDetailsActive` store (`stores/ui.js`).

- **Loupe overlay (`client/src/components/LoupePanel.svelte`):** full-screen
  fixed overlay (`inset: 0; z-index: 100`) shown when a sky tap is ambiguous.
  - Renders a square `SkyCanvas` with rounded corners; `magLimitOverride` prop
    bypasses the adaptive limit so faint objects stay visible at the loupe FOV.
  - Close button `✕` (top-right of the square) dispatches `close` with no
    state change — returns to sky view, nothing selected or deselected.
  - Tap anywhere in the square: picks the closest object unconditionally,
    dispatches `select` with `{ obj: closest }`.
  - `MainScreen` `on:select` handler: closes loupe, then toggles selection —
    deselect if `e.detail.obj` is already selected, otherwise select it.
    `ObjectDetails` is not opened automatically.

- **Object Details flow (separate from tap selection):**
  - TopBar row 2 is visible when `$selectedObject && !menuOpen &&
    !$searchViewActive`. It shows icon + name + constellation for the selected
    object. Clicking/tapping it dispatches `objectdetails`, which opens the
    About panel via `objectDetailsActive.set(true)`.
  - `ObjectDetails` back button and `Escape` key both call `close()`, which
    sets `objectDetailsActive.set(false)`. The `selectedObject` is **not**
    cleared — the user returns to the sky view with row 2 still visible.
  - The two states (`selectedObject` and `objectDetailsActive`) are fully
    independent: selection changes only via sky/loupe taps; About visibility
    changes only via TopBar open and back/Escape close.
- **FOV circle:** when enabled (Menu toggle, README §C4), draw a dashed circle
  on the canvas representing `FINDER_FOV` degrees diameter, centred on the
  current view centre. The circle is suppressed when its radius would exceed
  `min(W, H) / 2` (i.e. it would clip the canvas edge).

---

### Step 21: Top bar + menu ✅

**README refs:** §4.1, §4.2  
**Deliverable:** Top bar with all elements and a slide-in menu with all toggle
and navigation items.

Technical notes:

- Top bar layout: CSS Grid or Flexbox, two-row height on small screens
  (README §B2). Row 1: date-time | menu-toggle (centred) | battery.
  Row 2 (when object selected): object-type icon + name + constellation tap
  target.
- Battery: `navigator.getBattery()` API — available on Android Chrome; wrap
  in a try/catch for unsupported browsers.
- Date-time picker: a custom bottom-sheet modal component using
  `<CustomInput>`-style rendering (no native `<input type="datetime-local">`).
  Displays two scrollable drum-rolls (date and time) styled to match the active
  color scheme.
- Menu: full-height slide-in panel from the left. Each item is an SVG icon +
  label. Toggle items update the corresponding Svelte store (constellation
  lines, boundaries, DSOs, horizon, FOV circle visible/hidden). Navigation
  items call `router.push()`. The "Synchronize observation data" item shows a
  badge with the count of pending changes (README §C5) — read from a
  `pendingChanges` derived store.

---

### Step 22: Constellation rendering ✅

**README refs:** §2.1e, §4.2  
**Deliverable:** Constellation lines, boundaries and name labels toggled via
the menu; all rendered on the sky canvas.

Technical notes:

- **Lines:** for each constellation, iterate its `[hip_a, hip_b]` pairs,
  project both stars, draw a line segment. Skip if either star is off-canvas
  or below horizon.
- **Boundaries:** the IAU boundary is a list of RA/Dec polygon vertices —
  project and draw as polyline segments. Do not fill; stroke in a dim colour.
- **Names:** project the constellation's centroid (precompute and store in the
  JSON) and render a text label. In nightly mode use dim red; suppress label if
  centroid is off-canvas.
- Lines and boundaries are drawn on a separate off-screen canvas and composited
  onto the main canvas — avoids re-projecting all stars when only toggles change.

Implementation notes:

- Constellation data loaded from IDB `meta["constellations"]` in `onMount`
  via `getMeta`; stored in the `constellations` reactive variable.
- Centroid computed client-side via circular mean of boundary vertices
  (boundary RA is in hours; converted to degrees × 15 before projection).
- HIP lookup built from the `objects` prop per draw call; line segments
  where either HIP is missing (out-of-area star) are silently skipped.
- `showConstellationNames` is a separate store/prop from `showConstellationLines`;
  name labels are toggled independently.
- Boundary segments use 8-step RA/Dec subdivision instead of a simple
  endpoint test; this preserves the visible portion of segments that cross
  the hemisphere edge (where one endpoint would project to null).
- `showDsos` and `showHorizon` are wired through `MainScreen` as `SkyCanvas`
  props; draw calls are guarded by these flags.
- All props wired from `stores/ui.js` through `MainScreen`.

**← MVP is deployable after this step.**
At this point the app loads data, authenticates, shows a navigable star chart
with constellation overlays, and object selection is functional. Deploy to S3
with `make deploy` and verify on a real Android device.

### Step 22a: About panel ✅

**Deliverable:** Informational modal accessible via the "About" button in the
menu, showing the app name, build version, and data source credits.

Implementation notes:

- `client/src/components/AboutPanel.svelte`: centered fixed overlay (backdrop
  z-index 50, panel z-index 51). Dispatches a `close` event; closes on backdrop
  click, close-button click, or Escape key.
- `on:pointerdown|stopPropagation` on the panel div prevents `MainScreen`'s
  `setPointerCapture` from intercepting pointer events, which would otherwise
  swallow the close-button click.
- Version string from `import.meta.env.VITE_APP_VERSION_DATE` (falls back to
  `'0.1.0'`).
- Data sources credited: AT-HYG v3.3 / Gaia DR3, OpenNGC, Stellarium modern
  sky culture, WDS via VizieR, USGS / IAU Gazetteer.
- Nightly theme overrides via `:global([data-theme='nightly'])`: background
  `#110000`, text `#ff8080`, icon accent `#cc2200` (G=0 rule observed).
- `MenuPanel` dispatches an `about` event on button click; `MainScreen` handles
  it with `showAbout = true` and conditionally renders `<AboutPanel>`.
- Note: this is a static info panel. Step 32 spec calls for augmenting with live
  IndexedDB stats (record counts, storage size). That enhancement is deferred.

---

## Phase 4 — Object Discovery

### Step 23: Finder View ✅

**README refs:** §5.3, §5.3.1, §5.3.2  
**Deliverable:** Finder View screen with round clip, fixed FOV, swipe-only
navigation and its four action buttons.

Technical notes:

- Reuse `SkyCanvas` from Step 18 with `fov = FINDER_FOV`, `rotation = 0`
  (or match current Main Screen rotation). Clip to a circle using CSS
  `border-radius: 50%` on a square wrapper, or `clip-path: circle(50%)`.
- Constellation lines and boundaries are hidden unconditionally (README §5.3).
- The round view position is fixed (`position: sticky` or `position: fixed`)
  so it does not scroll with the button list (README §5.12 fixed finder rule
  also applies here during path editing).
- "Guide to find the object" button: only rendered when a finding path exists
  for the currently selected object (README §5.3.1). Read finding paths from
  the `findingPaths` IndexedDB meta entry.
- "Record guide to find object" button: always rendered; navigates to screen
  5.12 (README §5.3.2).

Implementation notes:

- `client/src/components/FinderPanel.svelte`: fixed full-screen overlay
  (`position: fixed; inset: 0; z-index: 100`) with a column flex layout.
  Circle occupies `calc(100vw - 2vh)` square with `1vh` margin on all sides,
  so the sky view takes up as much width as possible while remaining a circle.
- `clip-path: circle(50%)` applied to the inner `.circle-wrap` div (not the
  container) so the `::after` ring border on `.circle-container` renders
  outside the clipped region.
- `on:pointerdown|stopPropagation` on the overlay prevents `MainScreen`'s
  `pointerdown` handler (which calls `e.preventDefault()`) from suppressing
  synthesized `click` events on the overlay's children.
- `finderMode` prop added to `SkyCanvas`: in daily theme, stars with mag > 3
  render white; stars mag ≤ 3 render their spectral colour blended 72% toward
  white (`_blendToWhite`), mimicking the faint colour tints visible to the eye
  for only the brightest stars. Nightly theme is unaffected.
- Keyboard arrow keys pan the finder by `FINDER_FOV / 3` (2.5°) per press,
  with RA step divided by `cos(dec)`. The listener is registered in capture
  phase (`addEventListener('keydown', handler, true)`) so it intercepts before
  `MainScreen`'s handler and the main view does not pan simultaneously.
  Mounted/destroyed with `onMount`/`onDestroy`.

---

### Step 24: Search screen ✅

**README refs:** §5.4  
**Deliverable:** Fully functional Search screen with instant results, in-app
keyboard and result action icons.

Technical notes:

- Search is performed client-side against the in-memory object index (load all
  object names and catalogue numbers into a `Map` on startup — typically < 5 MB).
- Ranking: exact prefix match on proper name > prefix match on catalogue number
  > substring match on name. Limit to top 20 results.
- Catalogue number normalisation: strip spaces and leading zeros before matching,
  so "6543", "NGC6543", "NGC 6543" all resolve to the same object.
- The `CustomInput` component from Step 16 is used for the search field.
  System keyboard suppressed.

---

### Step 25: Object Details screen ✅

**README refs:** §5.16, §2.1 fields 1–11  
**Deliverable:** Object Details screen with all fields, Observed button state,
phase display and rise/transit/set times.

Technical notes:

- **Rise/transit/set:** use Astronomy Engine `SearchRiseSet()` and
  `SearchHourAngle()` for the current date and stored GPS location. Compute
  for the current calendar day (midnight to midnight local time). Display as
  local time strings.
- **Moon phase:** `Astronomy.MoonPhase()` returns the ecliptic longitude of the
  Moon; derive illumination fraction with
  `illumination = (1 − cos(phase_angle)) / 2`. Render the stored schematic Moon
  image with an SVG overlay mask to show the lit portion.
- **Inner planet phase:** `Astronomy.Illumination()` returns phase angle and
  fraction for any body.
- **"Observed" button state:** derive a `isObservedToday` boolean from the
  `observations` IndexedDB store (check if today's date entry contains this
  object's id). Render with filled vs outline icon variant.

---

### Step 26: Solar system & special object rendering ✅

**README refs:** §2.1d, §5.2  
**Deliverable:** Planets, Sun, Moon and visible asteroids rendered on the Main
Screen and Finder View with correct positions for the current date/time.

Technical notes:

- Use Astronomy Engine to compute `(RA, Dec)` and apparent magnitude for each
  solar system body at the time stored in the app's time Svelte store (which may
  differ from wall clock time if the user adjusted it via the top-bar picker).
- Recompute positions whenever the time store changes or the view is panned;
  throttle to once per second for live updates.
- Planet symbols: use distinct SVG icons per planet type overlaid on canvas.
- Asteroids: iterate `asteroids.json`, compute position and magnitude at current
  time using Astronomy Engine's `DefineStar` + orbital elements workaround or
  a simple two-body propagator for the short time range needed.

---

## Phase 5 — Observations & Sync

### Step 27: Telescopes screen ✅

**README refs:** §5.6  
**Deliverable:** Telescopes and eyepieces CRUD screen, data stored in IndexedDB
`meta` store under key `telescopes` and `eyepieces`.

Technical notes:

- Both lists are JSON arrays stored in the `meta` store. Assign a UUID to each
  item on creation (`crypto.randomUUID()`).
- "In use" check before deletion: scan all `observations` records for any
  reference to the telescope/eyepiece UUID.
- Focal lengths use mm throughout (README §5.6 corrected unit).

---

### Step 28: Observation form + Observed button ✅

**README refs:** §5.16 (Observed button and form)  
**Deliverable:** The Observed button on Object Details opens a form; saving
creates/updates today's observation record in IndexedDB and marks the change
as pending sync.

Technical notes:

- Observation record schema: `{ date, location: {name?, lat?, lon?} | null, notes, objects: [...] }`.
  Each object entry: `{ id, telescopeResults: [{telescopeId, seen, eyepieceIds, eyepieceId | null}], notes }`.
- Location: use `navigator.geolocation.getCurrentPosition()` to prefill;
  provide a "Clear location" button (README §B3). The form also supports
  manual location name (city/site).
- Pending sync tracking: maintain a `pendingChanges` count in the `meta` store,
  increment on every write. The menu badge in Step 21 reads this value.
- Use `<CustomTextarea>` from Step 16 for the notes fields.

Status note:

- Implemented and in active use from "Object Details" via the "Observed" button.

---

### Step 29: Observations list screen ✅

**README refs:** §5.5  
**Deliverable:** Expandable observation history sorted by date descending.

Technical notes:

- Editable field: each observation object entry has a free-text `notes` field.
  The Edit icon renders that specific `notes` field as a `<CustomTextarea>`;
  Accept writes back to IndexedDB and increments `pendingChanges`.
- Expand/collapse state is local UI state only (not persisted).

---

### Step 30: Update object data screen ✅

**README refs:** §5.13  
**Deliverable:** Hash-check screen that fetches fresh data only when needed.

Technical notes:

- Call `GET /data-hash` — returns `{"hash": "<hex-sha256>"}` of the current
  `manifest.json`. Compare against the `dataManifest.version` (or recompute
  from stored manifest bytes) to determine whether any data changed.
- If the hash differs, call `GET /manifest` and compare each entry's `hash`
  field (`"sha256:…"`) against the corresponding entry in the stored manifest
  (`getStoredManifest()`). Only re-download entries whose hash changed.
  - `stars_t1` or `objects` changed → re-ingest that single ZIP.
  - Individual `t2_chunks` entries changed → `clearCompletedChunks()` for
    those filenames, then re-ingest those chunks only.
- Show separate status per data type ("Object data: up to date",
  "Star data: update available", "N of M chunks updated").
- Re-download uses the same `ingestT1`, `ingestObjects`, `ingestChunk` helpers
  as the Welcome Screen (Step 17); call `storeManifest` after all re-downloads
  complete.

---

### Step 31: Synchronize observations screen ✅

**README refs:** §5.14  
**Deliverable:** One-shot observation sync screen.

Technical notes:

- Accessible from the menu at any time; when `pendingChanges > 0` the menu item
  shows the pending count as a badge.
- Display: list of dates with modified observation records before syncing.
- On "Synchronize":
  - If local pending changes exist, call `POST /observations` with the full
    observation array from IndexedDB (last-write-wins strategy), then clear
    local pending metadata.
  - Always fetch server observations afterwards and replace the local
    observation store so the screen also supports pull-only sync.

---

### Step 32: About screen + full `make deploy` ✅

**README refs:** §5.15, §3.1.4  
**Deliverable:** About screen populated with live stats; `make deploy` runs the
full four-step sequence end-to-end.

Technical notes:

- Stats are derived from IndexedDB on screen mount: count records in `objects`
  by type, count `observations`, count unique object IDs across all observations,
  count entries in `findingPaths`.
- Data sizes: `navigator.storage.estimate()` gives an approximate total; for
  per-store sizes iterate and sum value byte lengths.
- `make deploy` steps (README §3.1.4): run `tofu init -upgrade` and
  `tofu apply`, then package and push Lambda zip, then `make data-upload`
  (typically with `STORAGE=s3` for cloud deploy), then
  `npm --prefix client run build && aws s3 sync client/dist/ s3://CLIENT_BUCKET --delete`.
- Deployment output prints the CloudFront client URL and Lambda server URL.

---

## Phase 6 — Object Finding Paths

### Step 33: Object Finding Paths screen (define & edit) ✅

**README refs:** §5.12  
**Deliverable:** Full path recording UI with fixed Finder View, expandable step
list and all editing buttons.

Technical notes:

- Finding paths stored in `meta` IndexedDB under key `findingPaths` as:
  `{ [objectId]: { [startStarHip]: { steps: [{startPoint, endPoint, multiplier}] } } }`.
- Fixed-position Finder View: use `position: sticky; top: 0` within the
  screen's scroll container so the finder stays visible while the path list
  scrolls.
- Start/end point selection mode: temporarily allow two-finger zoom on the
  Finder View (override the "no zoom" rule, README §5.12). Render a crosshair
  indicator. Snap to nearest object within 15 px; if no object, store raw
  `{ra, dec}` coordinates.
- Multiplier picker: render buttons `0.5x, 1x, 1.5x, 2x, ...` up to
  `floor(2 × FINDER_FOV / vector_length × 2) / 2` (steps of 0.5, max 2×FOV).
- Step deletion confirmation dialog: text must enumerate the affected step
  numbers (README §A3).

---

### Step 34: Guide to Find the Object (5.3.1 + 5.3.2) ✅

**README refs:** §5.3.1, §5.3.2  
**Deliverable:** Step-through guide mode overlaid on the Finder View; Record
button navigates to Step 33.

Technical notes:

- Guide state machine: `{ pathId, currentStepIndex }` held in a Svelte store.
  Entering guide mode via 5.3.1 button initialises the state machine and
  switches the Finder View into read-only guide mode.
- Arrow overlay: draw the step vector as an arrow on the Finder canvas using
  `canvas.save()` / `translate` / `rotate` / `restore`. Label with multiplier
  if ≠ 1 (e.g. "2×").
- Final step: draw a small target circle at the object's projected position.
- Next/Previous buttons update `currentStepIndex` and re-render the arrow.
- "Record" button (5.3.2): `router.push('/finding-paths/' + selectedObjectId)`.

---

### Step 34b: Finding Paths List Screen (5.17) ✅

**README refs:** §5.17, §5.17.1, §5.17.2, §5.17.3  
**Deliverable:** New full-screen overlay accessible from the menu ("p") between
"Observations" and "Telescopes", showing a filterable table of all defined finding
paths with add, view, and delete actions.

Technical notes:

- New Svelte screen component (e.g. `FindingPathsListScreen.svelte`). Registered in
  `MainScreen` with the same overlay pattern used by `ObservationsScreen`. Menu item
  keyboard shortcut "p"; position between "Observations" and "Telescopes".
- Read all finding paths on mount via `getAllFindingPaths()` (returns the full
  `findingPaths` meta object). Build a flat list of `{ objectId, startHip }` pairs for
  the table; resolve labels via the search index.
- **Filter chips** — reuse the same chip/SearchPanel pattern as object search:
  - Target filter: `SearchPanel` with `resultFilter` limited to objects present in the
    finding paths data. Chip stores `objectId`.
  - Start filter: `SearchPanel` with `resultFilter` limited to stars whose HIP number
    appears as a start key in any finding path. Chip stores `startHip`.
  - Suggestion lists are built independently (the active chip in one filter does not
    narrow the other). The table applies both chips as an AND intersection.
- **Table** — sorted with natural sort on the catalog number string (split on digit
  boundaries, compare numeric parts numerically). Group rows by `objectId` so that
  multiple start paths for the same object are rendered under one target cell.
  - Draft detection: `path.steps?.length && path.steps[path.steps.length - 1]?.final`
    evaluates to `true` for a complete path; any other state = draft.
  - Step count for non-draft paths: `path.steps.length`.
- **Tap target label** — dispatch to About/Object Details (same navigation used
  elsewhere). Preserve filter state in a Svelte store or pass as props on return.
- **Tap start-star label** — open `FindingPathsScreen` with `contextObject` and
  `initialStartHip` set. On back, restore filter state.
- **Delete** — `ConfirmDialog` → `deleteFindingPathForObject(objectId, startHip)`;
  rebuild the flat list after deletion.
- **ADD flow** — tapping the add icon opens a `SearchPanel` restricted to objects
  with catalog numbers (not just stars). On selection, navigate to
  `FindingPathsScreen` with `contextObject` and `initialSelectStart=true`.

---

## Phase 7 — Visual Range

### Step 34c: Visual Range — Plan Generator ✅

**Plan doc:** `VISUAL_RANGE.md`  
**Deliverable:** Pure plan-generation function `generatePlan()` in
`client/src/lib/visualRangePlan.js`. Takes `{ getObjectsInArea, dsos, startStar,
telescope, eyepiece, initialMag }` and returns either a fully pre-computed
measurement plan `{ ok: true, steps }` or a structured failure `{ ok: false, reason }`.

Technical notes:

- **Exports:** `INITIAL_STAR_MAX_MAG = 4.0`, `INITIAL_MAG_MIN = 7.0`,
  `INITIAL_MAG_MAX = 11.0`, `INITIAL_MAG_STEP = 0.5`,
  `INITIAL_MAG_RANGE_START_FACTOR = 0.7`.
- **Internal constants:** `MEASURE_STEP = 0.5`, `STEP_MAG_TOLERANCE = 0.2`,
  `MAX_INITIAL_STEPS = 3`, `MAX_MOVE_STEPS = 3`,
  `MOVE_STARS_MIN_MAG_DIFF = 1.5`, `MAX_MAG_DIFF = 6.0`,
  `CLOSE_NEIGHBOURHOOD_REL_RADIUS = 0.02`, `DSO_MAX_SB = 24.0`,
  `BFS_BEAM_WIDTH = 30`, `PLAN_SEARCH_RADIUS_FACTOR = 2.5`.
- **Spatial indexes:** two independent indexes over the fetched star array.
  Coarse 5°×5° zones (matching `db.js` zone IDs) for guide-path BFS and
  brightness-range checks. Fine 0.1°×0.1° zones for isolation queries at
  radius ≈0.033° where scanning full coarse zones would be prohibitively slow
  in dense fields.
- **Phase 0 — pre-processing:**
  - Fetch all stars within `PLAN_SEARCH_RADIUS_FACTOR × FOV_diameter` of the
    start star up to the plan ceiling magnitude + tolerance.
  - DSO exclusion: mark galaxies, emission/reflection/bright nebulae, planetary
    nebulae, supernova remnants, and globular clusters as significant when their
    mean surface brightness `SB = mag + 2.5 × log₁₀(π × (a_arcmin×30) ×
    (b_arcmin×30)) < DSO_MAX_SB` (24.0 mag/arcsec²).
  - Candidate pre-filtering per magnitude band: reject variable stars, stars
    with an extremely red or blue spectral colour (`CLR_BLUEST = '#92b5ff'`,
    `CLR_REDDEST = '#ff8f6b'`), stars with a brighter neighbour within
    `CLOSE_NEIGHBOURHOOD_REL_RADIUS × FOV_diameter`, and stars whose position
    overlaps a significant DSO footprint.
- **Phase 1 — find initial measurement location:** enumerate all pairs of
  initial-magnitude candidates within 2× FOV radius; sort pair midpoints by
  angular distance from start star; for each, verify `MAX_MAG_DIFF` constraint
  and call `findGuidePath(startStar.pos, midpoint, MAX_INITIAL_STEPS, …)`.
- **Phase 2 — build step chain:** for each subsequent magnitude band, first try
  staying at the current centre (no moves required); otherwise enumerate nearby
  candidate pairs sorted by distance and call
  `findGuidePath(currentCentre, …, MAX_MOVE_STEPS, …)`. Stop when no reachable
  pair exists or the plan ceiling is reached.
- **`findGuidePath`:** beam-limited BFS over telescope positions snapped to a
  `fovRadius / 4` grid. At each position, enumerates candidate guide-star pairs
  where both stars lie within `guideInnerR = fovRadius × 0.85` of the current
  centre (85% inset margin ensures guide stars are visually interior to the FOV,
  not at the edge), for distance multipliers k ∈ {1, 2, 3} with
  `dist(S, E) × k ≤ 2 × FOV_diameter`. Beam capped at `BFS_BEAM_WIDTH = 30`
  states closest to target. Returns the first path reaching within `fovRadius / 2`
  of the target, or `null` on failure.
- **Candidate selection per step:** chooses the faintest (C1) and
  second-faintest (C2) qualifying candidates within FOV radius. Next step's
  magnitude band is derived from C2's actual magnitude, so the chain remains
  valid if only C2 was observed.
- **Tests:** `client/test/lib/visualRangePlan.test.js` (Vitest, Node environment).
  Two telescope configs (6″ f/5, 12″ f/4) × five start stars (Vega HIP 91262,
  Mizar HIP 65378, Arcturus HIP 69673, Mirach HIP 5447, Betelgeuse HIP 27989).
  Star data loaded from `data_prep/output/stars_t1.m*.csv` / `stars_t2.m*.csv`
  and `dso.json` via Node `fs` — no IndexedDB. Catalogue depth gating: depth m9
  or absent → skip all; m12 → 6″ only; m14 → both telescopes. Run with
  `make test-telescope-range` or as part of `make test`.

---

### Step 34d: Visual Range — UI Screens + Integration ✅

**Plan doc:** `VISUAL_RANGE.md`  
**Deliverable:** Two-screen Visual Range UI (`VisualRangeSetupScreen`,
`VisualRangeMeasureScreen`) with menu integration, `SkyCanvas` overlay support,
and observation-log integration.

Technical notes:

- **`VisualRangeSetupScreen.svelte`** (z-index 12):
  - Star picker reuses `SearchPanel` with a `resultFilter` limiting results to
    `type === 'star'` and `mag ≤ INITIAL_STAR_MAX_MAG` (4.0).
  - Initial magnitude options computed per-telescope as a pill range from
    `ceil(INITIAL_MAG_RANGE_START_FACTOR × theoreticalMax / 0.5) × 0.5` to
    `floor(theoreticalMax / 0.5) × 0.5`, where
    `theoreticalMax = 2.1 + 5 × log₁₀(diameter_mm)`. Invalid selected magnitude
    is cleared automatically when the telescope changes.
  - All selections (star, telescopeId, eyepieceId, initialMag) are persisted to
    `localStorage` under `observarium.visualRange.setup` and restored on mount
    after telescopes/eyepieces are loaded from IndexedDB.
  - "Begin" calls `generatePlan()`; shows an inline error paragraph if
    `ok: false`; transitions to `VisualRangeMeasureScreen` on success.
- **`VisualRangeMeasureScreen.svelte`** (z-index 13):
  - Circular sky view: `SkyCanvas` in `finderMode`, with `showDsos`,
    `showSolarSystem`, `showConstellationLines`, `showConstellationNames`, and
    `showConstellationBoundaries` all `false`. Double-star types mapped to plain
    star. `magLimitOverride` set to the current step's faintest candidate
    magnitude + 0.5 so stars beyond the target visibility level are suppressed.
  - `overlayArrows` prop on `SkyCanvas` (array): each entry is either a guide
    arrow `{ fromRa, fromDec, toRa, toDec, label? }` (drawn as a labelled line
    with arrowhead) or a candidate marker `{ markerRa, markerDec }` (drawn as a
    target circle). In the `move` phase the array contains guide arrows; in the
    `test` phase it contains a single marker at the candidate star.
  - **State machine:** `phase ∈ { move, test, result }` × `stepIndex` ×
    `moveIndex` × `candidateSlot`. The starting telescope position of each step
    is pre-computed as `_stepStarts[]` by sequentially applying each step's
    moves from `startStar.pos`.
  - **History stack:** `saveHistory()` / `goBack()` support the Previous button
    in both `move` and `test` phases, restoring full state.
  - **"Add to observation":** appends a formatted note
    `Visual range (TELESCOPE, EYEPIECE): mag M.M at HH:MM near STAR (CONSTELLATION)`
    to `obs.notes` (never pushes to `obs.objects`). Auto-creates today's
    observation if none exists. Button disabled after first use; shows
    confirmation text inline.
- **`RangeIcon.svelte`:** SVG icon for the Visual Range menu entry.
- **Menu integration** (`MenuPanel.svelte`, `MainScreen.svelte`): "Visual Range"
  item with keyboard shortcut `r`, positioned between "Finding Paths" and
  "Telescopes". Keyboard handler wired in `MainScreen`.
- **`SkyCanvas.svelte` modifications:** new `overlayArrows` prop (array of
  guide-arrow or marker objects). Guide arrows project celestial coordinates to
  canvas pixels, draw a line with an arrowhead, and optionally render a text label
  (distance multiplier). Markers draw a target circle at the candidate position.
- **`vite.config.mjs`:** test environment set to `'node'` so the plan generator
  test suite can access Node `fs` to read CSV star fixtures directly.

---

## Phase 8 — Quizzes

### Step 35: Quiz framework ✅

**README refs:** §2.2g  
**Deliverable:** Shared quiz infrastructure: setup modal, progress indicator,
state persistence and Back button.

Technical notes:

- **Setup modal** (global/local + difficulty) is a reusable `<QuizSetup>`
  component. If a saved state exists in `localStorage` for this quiz type +
  difficulty, add a "Continue previous quiz" option.
- **State persistence:** key = `quiz_{type}_{difficulty}_{global|local}`.
  Value: `{ pool: [objectIds], mastery: {objectId: score}, currentQuestion }`.
  Write to `localStorage` after every answer.
- **Progress indicator:** `progressPct = sum(min(mastery[id], 1) for id in pool) / pool.length * 100`.
  On correct answer: `mastery[id] += 0.25` (4 consecutive correct = mastered).
  On incorrect answer: `mastery[id] = max(0, mastery[id] − 0.5)`.
  Quiz ends when `progressPct === 100`.
- **Back button:** always rendered; on press save state to `localStorage` and
  emit quiz close event so `MainScreen` returns to the previous view state.

Implementation notes:

- Implemented shared logic in `client/src/lib/quizFramework.js`:
  `loadQuizState`, `saveQuizState`, `clearQuizState`, `applyQuizAnswer`,
  `computeProgressPct`, and weighted next-question selection.
- Implemented reusable UI in `client/src/components/QuizSetup.svelte` and
  `client/src/components/QuizProgress.svelte`.
- Setup choices (`scope`, `difficulty`) are persisted separately in
  `localStorage` and restored when reopening quiz setup.
- Back/close behavior saves quiz state and returns to previous app screen via
  the quiz `close` event.

---

### Step 36: Finder Scope Quiz

**README refs:** §5.7  
**Deliverable:** Quiz that presents 4 Finder Views in a 2×2 grid and asks the
user to identify the star by name.

Technical notes:

- Reuse `SkyCanvas` at `FINDER_FOV` for each of the 4 panels.
- Apply a random rotation (0–360°) per panel per question (different rotation
  for each panel).
- The 3 distractor stars are selected from the same difficulty-level pool,
  ensuring all 4 have similar magnitudes (within ±0.5 mag of each other).

---

### Step 37: Constellation Quiz ✅

**README refs:** §5.8  
**Deliverable:** Quiz that highlights a star and asks for name + constellation.

Technical notes:

- Uses a fixed quiz FOV derived from an anchor constellation span to keep zoom
  consistent across questions. If the selected star would be out of frame, the
  view is automatically recentered to keep the target visible.
- Selected star is highlighted with an in-canvas marker; constellation lines are
  hidden during the question and revealed after answering.

Implementation notes:

- Implemented in `client/src/screens/ConstellationQuizScreen.svelte` and wired
  from menu in `client/src/screens/MainScreen.svelte`.
- Difficulty pools currently use: easy `<= 1.5`, medium `<= 3`, hard `<= 4`.
- During reveal phase, constellation line endpoints missing from per-question
  object payload are resolved via fallback HIP-position mapping, so full target
  constellation schemas can still be rendered.

---

### Step 38: Deep Sky Quiz

**README refs:** §5.9, §5.9.1, §5.9.2, §5.9.3  
**Deliverable:** Multi-type DSO quiz combining Finder View, image and type
question rounds.

Technical notes:

- Randomly interleave the three question types within a session.
- Image questions: images must already be in IndexedDB (loaded in Step 17).
  Display as `<img src={objectURLFromBlob}>`.
- Only objects that have images are eligible for image-type questions.

---

### Step 39: Find Planet Quiz

**README refs:** §5.10  
**Deliverable:** Quiz that adds a fake star and asks the user to identify it.

Technical notes:

- Render a real sky fragment using `SkyCanvas`. Choose a region with enough
  stars of the target magnitude to provide plausible distractors.
- The fake star position must be at least 1° away from any real star of
  similar magnitude (avoid it being obviously placed in empty sky).
- Label 4 candidates (1 fake + 3 real) with numbers 1–4 drawn on canvas.
- On answer: reveal which label was the fake, and briefly overlay the real
  star chart without the fake point.

---

### Step 40: Moon Quiz

**README refs:** §5.11  
**Deliverable:** Quiz that highlights Moon features and asks for their name.

Technical notes:

- Render the schematic Moon map (from `moon_features.json`, Step 6) as an SVG
  or canvas element.
- Highlight a feature by drawing a coloured circle at its `(lat, lon)` mapped
  to the map's pixel coordinate system.
- **Local mode:** filter to features within ±30° of the current terminator
  longitude, computed from `Astronomy.MoonPhase()`.
- Four option buttons render feature names; correct answer outlined in green
  (daily mode) or blue (nightly mode — no green allowed, README §2.2a).
