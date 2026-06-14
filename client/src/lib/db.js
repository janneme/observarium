import { openDB as idbOpenDB } from "idb";

const DB_NAME = "observarium";
const DB_VERSION = 3;

const RA_BUCKET = 5;
const DEC_BUCKET = 5;
export const ZONE_RA_CELLS = 72; // 360 / RA_BUCKET
export const ZONE_DEC_CELLS = 36; // 180 / DEC_BUCKET

// Colour palette: index 0–7, must match COLOR_PALETTE in data_prep/stars.py.
export const COLOR_PALETTE = [
  "#92b5ff", // 0 O
  "#b2c5ff", // 1 B
  "#cad8ff", // 2 A
  "#f8f7ff", // 3 F
  "#fff4e8", // 4 G
  "#ffd2a1", // 5 K
  "#ff8f6b", // 6 M
  "#ffffff", // 7 default
];

// Stars with mag ≤ T1_MAG_LIMIT live in the in-memory cache.
// Stars with mag > T1_MAG_LIMIT are fetched from IDB zones_t2 on demand.
export const T1_MAG_LIMIT = 9.0;

// Compute sky-zone integer (0–2591) from equatorial coordinates.
export function computeZone(ra_deg, dec_deg) {
  const ra_cell = Math.floor(ra_deg / RA_BUCKET) % ZONE_RA_CELLS;
  const dec_cell = Math.min(
    ZONE_DEC_CELLS - 1,
    Math.floor((dec_deg + 90) / DEC_BUCKET),
  );
  return dec_cell * ZONE_RA_CELLS + ra_cell;
}

let _db = null;
let _dbPromise = null;

function _resetDb() {
  _db = null;
  _dbPromise = null;
}

async function getDB() {
  if (_db) return _db;
  if (!_dbPromise) {
    _dbPromise = idbOpenDB(DB_NAME, DB_VERSION, {
      upgrade(db, oldVersion, _newVersion, transaction) {
        if (oldVersion < 1) {
          db.createObjectStore("objects", { keyPath: "id" });
          db.createObjectStore("images", { keyPath: "catalogueId" });
          db.createObjectStore("observations", { keyPath: "date" });
          db.createObjectStore("meta", { keyPath: "key" });
        }
        if (oldVersion < 2) {
          transaction.objectStore("objects").createIndex("by_zone", "zone");
        }
        if (oldVersion < 3) {
          db.createObjectStore("zones_t2", { keyPath: "zone" });
          // Stale star records from the objects store must be removed; they will
          // be reloaded as CSV blobs on next data download.
          transaction.objectStore("objects").clear();
        }
      },
      // Another connection (e.g. another tab) is trying to upgrade the DB.
      // Close our end so the upgrade can proceed; next getDB() reopens.
      blocking() {
        if (_db) _db.close();
        _resetDb();
      },
      // The browser forcibly closed the connection (storage error, DevTools
      // database deletion, etc.).  Clear the stale reference so next getDB()
      // opens a fresh connection.
      terminated() {
        _resetDb();
      },
    }).then(
      (db) => {
        _db = db;
        _dbPromise = null;
        return db;
      },
      (err) => {
        _dbPromise = null;
        throw err;
      },
    );
  }
  return _dbPromise;
}

// --------------------------------------------------------------------------
// Tier-1 in-memory cache
// --------------------------------------------------------------------------

let _tier1Cache = null; // null until loaded; [] means loaded but empty

function _parseMag(raw) {
  if (raw.includes(":")) {
    const [a, b] = raw.split(":");
    return [parseFloat(a), parseFloat(b)];
  }
  return parseFloat(raw);
}

function _parseT1Csv(csv) {
  const lines = csv.split("\n");
  // header: ra,de,mg,cl,hp,hd,sp,ds,pr,pd,fl,by,db,nm,nt,sm
  const stars = [];
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (!line) continue;
    const c = line.split(",");
    const ra = parseFloat(c[0]);
    const dec = parseFloat(c[1]);
    const mag = _parseMag(c[2]);
    const colour = COLOR_PALETTE[parseInt(c[3], 10)] || COLOR_PALETTE[7];
    const hip = c[4] ? parseInt(c[4], 10) : null;
    const hd = c[5] ? parseInt(c[5], 10) : null;
    const id = hip ? `star_HIP${hip}` : hd ? `star_HD${hd}` : null;
    if (!id) continue;
    const star = {
      id,
      type: "star",
      pos: [ra, dec],
      mag,
      clr: colour,
      zone: computeZone(ra, dec),
    };
    if (hip) star.hip = hip;
    if (hd) star.hd = hd;
    if (c[6]) star.spect = c[6];
    if (c[7]) star.dist = parseFloat(c[7]);
    if (c[8]) star.pm_ra = parseFloat(c[8]);
    if (c[9]) star.pm_dec = parseFloat(c[9]);
    if (c[10]) star.flam = parseInt(c[10], 10);
    if (c[11]) star.bay = c[11];
    if (c[12]) star.dbl = true;
    if (c[13]) star.name = c[13];
    if (c[14]) star.note = c[14];
    if (c[15]) star.smr = c[15];
    stars.push(star);
  }
  return stars;
}

function _parseT2Csv(csv) {
  // rows: z,ra,de,mg,cl,hp,hd,sp,ds,pr,pd  (no header in zone blob)
  const lines = csv.split("\n");
  const stars = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line) continue;
    const c = line.split(",");
    const ra = parseFloat(c[1]);
    const dec = parseFloat(c[2]);
    const mag = _parseMag(c[3]);
    const colour = COLOR_PALETTE[parseInt(c[4], 10)] || COLOR_PALETTE[7];
    const hip = c[5] ? parseInt(c[5], 10) : null;
    const hd = c[6] ? parseInt(c[6], 10) : null;
    const id = hip ? `star_HIP${hip}` : hd ? `star_HD${hd}` : null;
    if (!id) continue;
    const star = {
      id,
      type: "star",
      pos: [ra, dec],
      mag,
      clr: colour,
      zone: parseInt(c[0], 10),
    };
    if (hip) star.hip = hip;
    if (hd) star.hd = hd;
    if (c[7]) star.spect = c[7];
    if (c[8]) star.dist = parseFloat(c[8]);
    if (c[9]) star.pm_ra = parseFloat(c[9]);
    if (c[10]) star.pm_dec = parseFloat(c[10]);
    stars.push(star);
  }
  return stars;
}

async function _ensureTier1Loaded() {
  if (_tier1Cache !== null) return;
  const db = await getDB();
  const row = await db.get("meta", "stars_t1");
  _tier1Cache = row ? _parseT1Csv(row.value) : [];
}

// --------------------------------------------------------------------------
// Public write helpers called by WelcomeScreen during data load
// --------------------------------------------------------------------------

export async function storeTier1Blob(csvText) {
  const db = await getDB();
  await db.put("meta", { key: "stars_t1", value: csvText });
  _tier1Cache = null; // invalidate cache so next query re-parses
}

export async function bulkPutZoneT2Blobs(items) {
  // items: Array<{zone: number, csv: string}>
  const db = await getDB();
  const tx = db.transaction("zones_t2", "readwrite");
  await Promise.all(items.map((item) => tx.store.put(item)));
  await tx.done;
}

// --------------------------------------------------------------------------
// Existing helpers (unchanged)
// --------------------------------------------------------------------------

export async function hasData() {
  const manifest = await getStoredManifest();
  if (!manifest) {
    const db = await getDB();
    const row = await db.get("meta", "stars_t1");
    if (row) return true;
    const count = await db.count("objects");
    return count > 0;
  }
  const completed = await getCompletedChunks();
  return (
    manifest.t2_chunks.every((c) => completed.has(c.filename)) &&
    !!(await getMeta("stars_t1"))
  );
}

export async function getMeta(key) {
  const db = await getDB();
  const row = await db.get("meta", key);
  return row ? row.value : undefined;
}

export async function setMeta(key, value) {
  const db = await getDB();
  await db.put("meta", { key, value });
}

export async function storeManifest(manifest) {
  const stored = {
    version: manifest.version,
    stars_t1: { filename: manifest.stars_t1.filename, hash: manifest.stars_t1.hash, size: manifest.stars_t1.size },
    objects: { filename: manifest.objects.filename, hash: manifest.objects.hash, size: manifest.objects.size },
    t2_chunks: manifest.t2_chunks.map(({ filename, hash, size, zones }) => ({ filename, hash, size, zones })),
  };
  await setMeta("dataManifest", stored);
}

export async function getStoredManifest() {
  return getMeta("dataManifest");
}

export async function getCompletedChunks() {
  const arr = await getMeta("completedChunks");
  return new Set(arr || []);
}

export async function markChunkComplete(filename) {
  const arr = (await getMeta("completedChunks")) || [];
  if (!arr.includes(filename)) {
    arr.push(filename);
    await setMeta("completedChunks", arr);
  }
}

export async function clearCompletedChunks() {
  await setMeta("completedChunks", []);
}

export async function bulkPutObjects(items) {
  const db = await getDB();
  const tx = db.transaction("objects", "readwrite");
  await Promise.all(items.map((item) => tx.store.put(item)));
  await tx.done;
}

export async function bulkPutImages(items) {
  const db = await getDB();
  const tx = db.transaction("images", "readwrite");
  await Promise.all(items.map((item) => tx.store.put(item)));
  await tx.done;
}

export async function bulkPutObservations(items) {
  const db = await getDB();
  const tx = db.transaction("observations", "readwrite");
  await Promise.all(items.map((item) => tx.store.put(item)));
  await tx.done;
}

// --------------------------------------------------------------------------
// Zone helpers
// --------------------------------------------------------------------------

function _zonesForArea(ra_min, ra_max, dec_min, dec_max) {
  const dc_min = Math.max(
    0,
    Math.floor((Math.max(-90, dec_min) + 90) / DEC_BUCKET),
  );
  const dc_max = Math.min(
    ZONE_DEC_CELLS - 1,
    Math.floor((Math.min(90, dec_max) + 90) / DEC_BUCKET),
  );
  const span = ra_max - ra_min;
  const ra0 = ((ra_min % 360) + 360) % 360;
  const ra1 = ((ra_max % 360) + 360) % 360;
  const rc_min = Math.floor(ra0 / RA_BUCKET);
  const rc_max = Math.floor(ra1 / RA_BUCKET);

  const zones = [];
  for (let dc = dc_min; dc <= dc_max; dc++) {
    const base = dc * ZONE_RA_CELLS;
    if (span >= 360) {
      for (let rc = 0; rc < ZONE_RA_CELLS; rc++) zones.push(base + rc);
    } else if (rc_min <= rc_max) {
      for (let rc = rc_min; rc <= rc_max; rc++) zones.push(base + rc);
    } else {
      for (let rc = rc_min; rc < ZONE_RA_CELLS; rc++) zones.push(base + rc);
      for (let rc = 0; rc <= rc_max; rc++) zones.push(base + rc);
    }
  }
  return zones;
}

// --------------------------------------------------------------------------
// Main query
// --------------------------------------------------------------------------

// Return all sky objects whose position overlaps the equatorial bounding box.
// ra_min/ra_max and dec_min/dec_max in degrees.
// mag_limit caps which stars are returned; defaults to include all.
export async function getObjectsInArea(
  ra_min,
  ra_max,
  dec_min,
  dec_max,
  mag_limit = 99,
) {
  await _ensureTier1Loaded();

  // 1. Filter Tier-1 in-memory array by bounding box + mag_limit.
  const span = ra_max - ra_min;
  const ra0n = ((ra_min % 360) + 360) % 360;
  const ra1n = ((ra_max % 360) + 360) % 360;
  const wraps = ra0n > ra1n;

  function _inRA(ra) {
    if (span >= 360) return true; // full-sky RA span; accept all
    return wraps ? ra >= ra0n || ra <= ra1n : ra >= ra0n && ra <= ra1n;
  }
  const results = [];
  for (const s of _tier1Cache) {
    const m = typeof s.mag === "number" ? s.mag : s.mag[0];
    if (m > mag_limit) break; // T1 is sorted by mag ascending; early exit
    const [ra, dec] = s.pos;
    if (dec < dec_min || dec > dec_max) continue;
    if (!_inRA(ra)) continue;
    results.push(s);
  }

  // 2. Fetch Tier-2 zone blobs when FOV is narrow enough to need faint stars.
  if (mag_limit > T1_MAG_LIMIT) {
    const db = await getDB();
    const zones = _zonesForArea(ra_min, ra_max, dec_min, dec_max);
    const blobs = await Promise.all(zones.map((z) => db.get("zones_t2", z)));
    for (const blob of blobs) {
      if (!blob) continue;
      const t2Stars = _parseT2Csv(blob.csv);
      for (const s of t2Stars) {
        const m = typeof s.mag === "number" ? s.mag : s.mag[0];
        if (m > mag_limit) break; // T2 per-zone blobs are sorted by mag ascending
        const [ra, dec] = s.pos;
        if (dec < dec_min || dec > dec_max) continue;
        if (!_inRA(ra)) continue;
        results.push(s);
      }
    }
  }

  // 3. Query objects store for DSOs and double stars (existing logic).
  const dc_min = Math.max(
    0,
    Math.floor((Math.max(-90, dec_min) + 90) / DEC_BUCKET),
  );
  const dc_max = Math.min(
    ZONE_DEC_CELLS - 1,
    Math.floor((Math.min(90, dec_max) + 90) / DEC_BUCKET),
  );
  const rc_min = Math.floor(ra0n / RA_BUCKET);
  const rc_max = Math.floor(ra1n / RA_BUCKET);

  const db = await getDB();
  const tx = db.transaction("objects", "readonly");
  const idx = tx.store.index("by_zone");
  const queries = [];
  for (let dc = dc_min; dc <= dc_max; dc++) {
    const base = dc * ZONE_RA_CELLS;
    if (span >= 360) {
      queries.push(
        idx.getAll(IDBKeyRange.bound(base, base + ZONE_RA_CELLS - 1)),
      );
    } else if (rc_min <= rc_max) {
      queries.push(idx.getAll(IDBKeyRange.bound(base + rc_min, base + rc_max)));
    } else {
      queries.push(
        idx.getAll(IDBKeyRange.bound(base + rc_min, base + ZONE_RA_CELLS - 1)),
      );
      queries.push(idx.getAll(IDBKeyRange.bound(base, base + rc_max)));
    }
  }
  const dsoArrays = await Promise.all(queries);
  for (const arr of dsoArrays) {
    for (const obj of arr) results.push(obj);
  }

  return results;
}
