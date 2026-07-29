"""FloodGuard flood-analysis tools for the insurance support agent.

These tools give a Strands agent geospatial situational awareness for flood
insurance claims. They are self-contained (no local MCP server required) so the
agent works identically in local development and when deployed to Amazon Bedrock
AgentCore runtime.

Data sources (all open, no credentials):
  * Earth Search STAC (Element84) — Sentinel-2 L2A optical + Sentinel-1 GRD SAR
  * OpenStreetMap Nominatim — geocoding place names to bounding boxes
  * Registry of Open Data on AWS (RODA) — open dataset discovery

Flood-detection science:
  * Sentinel-2 (optical): NDWI = (Green - NIR) / (Green + NIR). Open water is
    positive (~> 0). Comparing a "before" and "after" scene isolates newly
    inundated land = flood extent.
  * Sentinel-1 (SAR): VV backscatter. Smooth flood water reflects radar away
    from the sensor and appears dark (low dB). SAR sees through clouds, so it is
    the workhorse for flood mapping during storms.
"""

from __future__ import annotations

import os
import math
import logging

import httpx
from strands import tool

logger = logging.getLogger("floodguard.tools")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
S2_COLLECTION = "sentinel-2-l2a"
S1_COLLECTION = "sentinel-1-grd"
RODA_INDEX_URL = "https://registry.opendata.aws/index.ndjson"

# Cap how much imagery we pull per call so a chatbot turn stays responsive and
# memory-bounded inside the runtime microVM.
MAX_WINDOW_PIXELS = 2500 * 2500

# GDAL tuning for fast COG byte-range reads over HTTP (set before rasterio import
# side effects matter, and re-applied defensively inside the tools).
_GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "GDAL_HTTP_MULTIPLEX": "YES",
    "GDAL_HTTP_VERSION": "2",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.TIF,.tiff",
    "VSI_CACHE": "TRUE",
    "AWS_NO_SIGN_REQUEST": "YES",
}

# rasterio.Env requires GDAL_CACHEMAX as an int (MB); keep it separate from the
# string-valued options above.
_GDAL_ENV_TYPED = {"GDAL_CACHEMAX": 256}


def _apply_gdal_env() -> None:
    for k, v in _GDAL_ENV.items():
        os.environ.setdefault(k, v)
    os.environ.setdefault("GDAL_CACHEMAX", str(_GDAL_ENV_TYPED["GDAL_CACHEMAX"]))


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _validate_bbox(bbox: list[float]) -> list[float]:
    if not bbox or len(bbox) != 4:
        raise ValueError("bbox must be [west, south, east, north] in degrees")
    west, south, east, north = (float(v) for v in bbox)
    if west >= east or south >= north:
        raise ValueError("bbox must have west<east and south<north")
    if not (-180 <= west <= 180 and -180 <= east <= 180 and -90 <= south <= 90 and -90 <= north <= 90):
        raise ValueError("bbox coordinates out of range")
    return [west, south, east, north]


def _stac_search(collection: str, bbox: list[float], datetime_range: str,
                 limit: int = 10, query: dict | None = None) -> list[dict]:
    """POST to the Earth Search STAC /search endpoint and return features."""
    body: dict = {
        "collections": [collection],
        "bbox": bbox,
        "datetime": datetime_range,
        "limit": limit,
    }
    if query:
        body["query"] = query
    with httpx.Client(timeout=45, follow_redirects=True) as client:
        resp = client.post(f"{EARTH_SEARCH}/search", json=body)
        resp.raise_for_status()
        return resp.json().get("features", [])


def _get_item(collection: str, item_id: str) -> dict:
    url = f"{EARTH_SEARCH}/collections/{collection}/items/{item_id}"
    with httpx.Client(timeout=45, follow_redirects=True) as client:
        resp = client.get(url)
        if resp.status_code == 404:
            raise ValueError(f"Scene '{item_id}' not found in collection '{collection}'")
        resp.raise_for_status()
        return resp.json()


def _asset_href(assets: dict, *keys: str) -> str:
    for key in keys:
        a = assets.get(key)
        if a and a.get("href"):
            return a["href"]
    raise ValueError(f"None of the assets {keys} were found in the scene")


def _read_window(url: str, bbox: list[float]):
    """Read a COG window covering bbox (EPSG:4326) as a float32 numpy array.

    Returns (array, pixel_area_m2). Raises if the requested window is too large.
    """
    import numpy as np
    import rasterio
    from rasterio.windows import from_bounds
    from pyproj import Transformer

    _apply_gdal_env()
    with rasterio.Env(**_GDAL_ENV, **_GDAL_ENV_TYPED):
        with rasterio.open(url) as src:
            transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
            left, bottom = transformer.transform(bbox[0], bbox[1])
            right, top = transformer.transform(bbox[2], bbox[3])
            window = from_bounds(left, bottom, right, top, src.transform)

            h = int(math.ceil(window.height))
            w = int(math.ceil(window.width))
            if h <= 0 or w <= 0:
                raise ValueError("bbox does not overlap the scene footprint")
            if h * w > MAX_WINDOW_PIXELS:
                raise ValueError(
                    f"Requested window {w}x{h} px exceeds the {MAX_WINDOW_PIXELS} px "
                    "limit; use a smaller bbox"
                )

            arr = src.read(1, window=window, boundless=True, fill_value=0).astype("float32")
            # Native pixel size in metres (Sentinel COGs are in a metric UTM CRS).
            px_w, px_h = src.res
            pixel_area = abs(px_w * px_h)
    return arr, pixel_area


def _meters_per_degree(lat_deg: float) -> tuple[float, float]:
    """Approximate metres per degree of longitude/latitude at a given latitude."""
    lat = math.radians(lat_deg)
    m_per_deg_lat = 111_132.92 - 559.82 * math.cos(2 * lat) + 1.175 * math.cos(4 * lat)
    m_per_deg_lon = 111_412.84 * math.cos(lat) - 93.5 * math.cos(3 * lat)
    return abs(m_per_deg_lon), abs(m_per_deg_lat)


def _read_window_warped(url: str, bbox: list[float]):
    """Read a COG/GRD window over bbox, warping GCP-georeferenced assets on the fly.

    Sentinel-1 GRD assets on Earth Search are georeferenced by GCPs rather than a
    plain CRS, so a direct windowed read has no usable transform. A WarpedVRT to
    EPSG:4326 (using the GCPs) makes the window addressable by lon/lat. Returns
    (array, pixel_area_m2) where pixel area is derived from the AOI latitude.
    """
    import numpy as np
    import rasterio
    from rasterio.windows import from_bounds
    from rasterio.vrt import WarpedVRT

    _apply_gdal_env()
    with rasterio.Env(**_GDAL_ENV, **_GDAL_ENV_TYPED):
        with rasterio.open(url) as src:
            vrt_opts = {"crs": "EPSG:4326"}
            # If the source has neither a CRS nor GCPs we cannot georeference it.
            gcps = None
            try:
                gcps, gcp_crs = src.gcps
            except Exception:
                gcp_crs = None
            if not src.crs and not gcps:
                raise ValueError("SAR asset has no CRS or GCPs; cannot georeference")

            with WarpedVRT(src, **vrt_opts) as vrt:
                window = from_bounds(bbox[0], bbox[1], bbox[2], bbox[3], vrt.transform)
                # WarpedVRT forbids boundless reads, so clip the window to the
                # VRT's own extent before reading.
                full = rasterio.windows.Window(0, 0, vrt.width, vrt.height)
                window = window.intersection(full)
                h = int(math.ceil(window.height))
                w = int(math.ceil(window.width))
                if h <= 0 or w <= 0:
                    raise ValueError("bbox does not overlap the scene footprint")
                if h * w > MAX_WINDOW_PIXELS:
                    raise ValueError(
                        f"Requested window {w}x{h} px exceeds the {MAX_WINDOW_PIXELS} px "
                        "limit; use a smaller bbox"
                    )
                arr = vrt.read(1, window=window).astype("float32")
                # Degree-sized pixels -> metres via the AOI centre latitude.
                px_w_deg, px_h_deg = vrt.res
                lat_c = (bbox[1] + bbox[3]) / 2.0
                m_lon, m_lat = _meters_per_degree(lat_c)
                pixel_area = abs(px_w_deg * m_lon) * abs(px_h_deg * m_lat)
    return arr, pixel_area


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
def geocode_place(place: str) -> dict:
    """Geocode a place name (city, island, address) to a bounding box and centre point.

    Use this first when a policyholder describes a location in words (e.g.
    "Maui, Hawaii") so later tools have a numeric bounding box to work with.

    Args:
        place: Free-text location, e.g. "Maui, Hawaii" or "Lahaina, HI".

    Returns:
        A dict with the resolved display name, centre lat/lon, and a
        bounding box as [west, south, east, north] in decimal degrees.
    """
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        resp = client.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": place, "format": "jsonv2", "limit": 1},
            headers={"User-Agent": "FloodGuard-InsuranceAgent/1.0"},
        )
        resp.raise_for_status()
        results = resp.json()
    if not results:
        return {"error": f"Could not geocode '{place}'"}
    r = results[0]
    # Nominatim boundingbox is [south, north, west, east] as strings.
    s, n, w, e = (float(x) for x in r["boundingbox"])
    return {
        "query": place,
        "display_name": r.get("display_name", place),
        "center": {"lat": float(r["lat"]), "lon": float(r["lon"])},
        "bbox": [w, s, e, n],
    }


@tool
def search_flood_scenes(
    bbox: list[float],
    start_date: str,
    end_date: str,
    sensor: str = "optical",
    max_cloud_cover: float = 30.0,
    limit: int = 8,
) -> dict:
    """Search Sentinel-1 (SAR) or Sentinel-2 (optical) scenes over an area and time window.

    Sentinel-2 (sensor="optical") is best for clear-sky NDWI water mapping.
    Sentinel-1 (sensor="sar") sees through clouds and is the workhorse during
    active storm/flood events. For a flood claim you typically want a "before"
    scene (pre-event, dry baseline) and an "after" scene (during/just after the
    flood), then pass their ids to the analysis tools.

    Args:
        bbox: Area of interest as [west, south, east, north] in degrees.
        start_date: ISO date (YYYY-MM-DD) start of the search window.
        end_date: ISO date (YYYY-MM-DD) end of the search window.
        sensor: "optical" for Sentinel-2 L2A, or "sar" for Sentinel-1 GRD.
        max_cloud_cover: Max cloud cover percent (optical only; ignored for SAR).
        limit: Maximum number of scenes to return (default 8).

    Returns:
        A dict listing matching scenes with id, datetime, cloud cover (optical),
        and platform, sorted oldest-first so before/after selection is easy.
    """
    bbox = _validate_bbox(bbox)
    dt = f"{start_date}T00:00:00Z/{end_date}T23:59:59Z"

    if sensor == "sar":
        collection = S1_COLLECTION
        query = {"sar:instrument_mode": {"eq": "IW"}}
    else:
        collection = S2_COLLECTION
        query = {"eo:cloud_cover": {"lte": max_cloud_cover}}

    features = _stac_search(collection, bbox, dt, limit=limit, query=query)

    scenes = []
    for f in features:
        props = f.get("properties", {})
        scenes.append({
            "id": f.get("id"),
            "collection": collection,
            "datetime": props.get("datetime"),
            "cloud_cover": props.get("eo:cloud_cover"),
            "platform": props.get("platform"),
            "polarizations": props.get("sar:polarizations"),
        })
    scenes.sort(key=lambda s: s.get("datetime") or "")
    return {
        "sensor": sensor,
        "collection": collection,
        "bbox": bbox,
        "scene_count": len(scenes),
        "scenes": scenes,
    }


@tool
def compute_water_extent(scene_id: str, bbox: list[float]) -> dict:
    """Compute the open-water extent in a Sentinel-2 scene over a bounding box using NDWI.

    NDWI = (Green B03 - NIR B08) / (Green B03 + NIR B08). Pixels with NDWI > 0
    are classified as open water. Use this on a single scene to measure standing
    water, or call analyze_flood_change to compare a before/after pair.

    Args:
        scene_id: A Sentinel-2 L2A scene id (from search_flood_scenes, sensor="optical").
        bbox: Area of interest [west, south, east, north] in degrees. Keep it
              small (a neighbourhood or property cluster) for a fast, focused read.

    Returns:
        A dict with the water-covered area in km2, the fraction of the AOI under
        water, NDWI statistics, and the analysed pixel grid size.
    """
    import numpy as np

    bbox = _validate_bbox(bbox)
    item = _get_item(S2_COLLECTION, scene_id)
    assets = item.get("assets", {})
    green_url = _asset_href(assets, "green", "B03", "b03")
    nir_url = _asset_href(assets, "nir", "B08", "b08")

    green, px_area = _read_window(green_url, bbox)
    nir, _ = _read_window(nir_url, bbox)

    # Align shapes defensively (both are native 10 m bands, should already match).
    h = min(green.shape[0], nir.shape[0])
    w = min(green.shape[1], nir.shape[1])
    green, nir = green[:h, :w], nir[:h, :w]

    valid = (green + nir) > 0
    ndwi = np.zeros_like(green, dtype="float32")
    ndwi[valid] = (green[valid] - nir[valid]) / (green[valid] + nir[valid])

    water = (ndwi > 0) & valid
    water_pixels = int(water.sum())
    valid_pixels = int(valid.sum()) or 1
    water_area_km2 = water_pixels * px_area / 1_000_000.0

    ndwi_valid = ndwi[valid]
    return {
        "scene_id": scene_id,
        "datetime": item.get("properties", {}).get("datetime"),
        "bbox": bbox,
        "grid": {"height": h, "width": w, "pixel_size_m": round(math.sqrt(px_area), 2)},
        "water_area_km2": round(water_area_km2, 4),
        "water_fraction": round(water_pixels / valid_pixels, 4),
        "ndwi_stats": {
            "min": round(float(ndwi_valid.min()), 3) if ndwi_valid.size else None,
            "max": round(float(ndwi_valid.max()), 3) if ndwi_valid.size else None,
            "mean": round(float(ndwi_valid.mean()), 3) if ndwi_valid.size else None,
        },
    }


@tool
def analyze_flood_change(before_scene_id: str, after_scene_id: str, bbox: list[float]) -> dict:
    """Quantify newly flooded land between two Sentinel-2 scenes (before vs after an event).

    Computes NDWI water masks for both scenes and reports the change. "Newly
    flooded" pixels are those that were dry in the before scene and became water
    in the after scene — this is the core number for a flood insurance claim.

    Args:
        before_scene_id: Sentinel-2 scene id from before the flood (dry baseline).
        after_scene_id: Sentinel-2 scene id during/after the flood.
        bbox: Area of interest [west, south, east, north] in degrees (keep small).

    Returns:
        A dict with before/after water area, newly flooded area in km2, the
        percentage increase in water coverage, and the analysed grid size.
    """
    import numpy as np

    bbox = _validate_bbox(bbox)

    def _ndwi(scene_id):
        item = _get_item(S2_COLLECTION, scene_id)
        assets = item.get("assets", {})
        green, px_area = _read_window(_asset_href(assets, "green", "B03"), bbox)
        nir, _ = _read_window(_asset_href(assets, "nir", "B08"), bbox)
        h = min(green.shape[0], nir.shape[0])
        w = min(green.shape[1], nir.shape[1])
        green, nir = green[:h, :w], nir[:h, :w]
        valid = (green + nir) > 0
        ndwi = np.zeros_like(green, dtype="float32")
        ndwi[valid] = (green[valid] - nir[valid]) / (green[valid] + nir[valid])
        return ndwi, valid, px_area, item.get("properties", {}).get("datetime")

    before_ndwi, before_valid, px_area, before_dt = _ndwi(before_scene_id)
    after_ndwi, after_valid, _, after_dt = _ndwi(after_scene_id)

    h = min(before_ndwi.shape[0], after_ndwi.shape[0])
    w = min(before_ndwi.shape[1], after_ndwi.shape[1])
    before_water = (before_ndwi[:h, :w] > 0)
    after_water = (after_ndwi[:h, :w] > 0)
    valid = before_valid[:h, :w] & after_valid[:h, :w]

    before_water &= valid
    after_water &= valid
    newly_flooded = after_water & ~before_water & valid

    to_km2 = lambda mask: int(mask.sum()) * px_area / 1_000_000.0
    before_km2 = to_km2(before_water)
    after_km2 = to_km2(after_water)
    flooded_km2 = to_km2(newly_flooded)

    pct_increase = None
    if before_km2 > 0:
        pct_increase = round((after_km2 - before_km2) / before_km2 * 100.0, 1)

    return {
        "before_scene_id": before_scene_id,
        "after_scene_id": after_scene_id,
        "before_datetime": before_dt,
        "after_datetime": after_dt,
        "bbox": bbox,
        "grid": {"height": h, "width": w, "pixel_size_m": round(math.sqrt(px_area), 2)},
        "before_water_km2": round(before_km2, 4),
        "after_water_km2": round(after_km2, 4),
        "newly_flooded_km2": round(flooded_km2, 4),
        "water_increase_pct": pct_increase,
        "method": "Sentinel-2 NDWI (>0 = open water); newly flooded = dry-before & water-after",
    }


@tool
def analyze_sar_flood(before_scene_id: str, after_scene_id: str, bbox: list[float],
                      threshold_db: float = -17.0) -> dict:
    """Detect flooding from a Sentinel-1 SAR before/after pair using VV backscatter.

    SAR penetrates cloud, so it is the primary sensor during active storms. Calm
    flood water is smooth and reflects the radar away from the sensor, so it
    appears dark (low VV backscatter in dB). Pixels that were bright (land)
    before and become dark (below threshold) after indicate new inundation.

    Args:
        before_scene_id: Sentinel-1 GRD scene id before the event.
        after_scene_id: Sentinel-1 GRD scene id during/after the event.
        bbox: Area of interest [west, south, east, north] in degrees (keep small).
        threshold_db: VV backscatter threshold in dB below which a pixel is
                      treated as water (default -17 dB).

    Returns:
        A dict with the SAR-detected newly flooded area in km2 and the fraction
        of the AOI newly inundated.
    """
    import numpy as np

    bbox = _validate_bbox(bbox)

    def _vv_db(scene_id):
        item = _get_item(S1_COLLECTION, scene_id)
        assets = item.get("assets", {})
        vv_url = _asset_href(assets, "vv", "VV")
        vv, px_area = _read_window_warped(vv_url, bbox)
        # Earth Search S1 GRD assets are linear amplitude/intensity; convert to dB.
        # Guard against non-positive values (nodata) which have no valid log.
        positive = vv > 0
        vv_db = np.full(vv.shape, np.nan, dtype="float32")
        vv_db[positive] = 10.0 * np.log10(vv[positive])
        return vv_db, px_area

    before_db, px_area = _vv_db(before_scene_id)
    after_db, _ = _vv_db(after_scene_id)

    h = min(before_db.shape[0], after_db.shape[0])
    w = min(before_db.shape[1], after_db.shape[1])
    before_db, after_db = before_db[:h, :w], after_db[:h, :w]

    valid = ~np.isnan(before_db) & ~np.isnan(after_db)
    before_water = (before_db < threshold_db) & valid
    after_water = (after_db < threshold_db) & valid
    newly_flooded = after_water & ~before_water & valid

    to_km2 = lambda mask: int(np.count_nonzero(mask)) * px_area / 1_000_000.0
    valid_px = int(np.count_nonzero(valid)) or 1

    return {
        "before_scene_id": before_scene_id,
        "after_scene_id": after_scene_id,
        "bbox": bbox,
        "threshold_db": threshold_db,
        "grid": {"height": h, "width": w, "pixel_size_m": round(math.sqrt(px_area), 2)},
        "newly_flooded_km2": round(to_km2(newly_flooded), 4),
        "newly_flooded_fraction": round(int(np.count_nonzero(newly_flooded)) / valid_px, 4),
        "method": "Sentinel-1 VV backscatter change (dark = water); flooded = bright-before & dark-after",
    }


@tool
def assess_flood_claim(
    policyholder: str,
    property_address: str,
    newly_flooded_km2: float,
    property_in_flood_zone: bool = True,
    coverage_limit_usd: float = 250000.0,
) -> dict:
    """Produce a preliminary flood insurance claim assessment from analysis results.

    This applies FloodGuard's (fictional, demo) triage rules to the geospatial
    flood measurements so a support agent can give the policyholder an initial
    read. It does NOT approve or deny a claim — it routes and estimates.

    Args:
        policyholder: Name of the policyholder.
        property_address: Street address or place description of the insured property.
        newly_flooded_km2: Newly flooded area near the property (from analyze_flood_change
                           or analyze_sar_flood).
        property_in_flood_zone: Whether the property sits in a designated flood zone.
        coverage_limit_usd: The policy's coverage limit in USD (default 250,000).

    Returns:
        A dict with a severity rating, a recommended claim-handling track, an
        estimated payout band, and clear next steps for the policyholder.
    """
    # Simple, transparent triage bands based on detected inundation footprint.
    if newly_flooded_km2 <= 0.0:
        severity = "none"
        track = "No inundation detected in imagery — request ground photos before opening a claim."
        payout_band = "$0"
    elif newly_flooded_km2 < 0.05:
        severity = "minor"
        track = "Fast-track / low-complexity adjuster review."
        payout_band = f"up to ${int(coverage_limit_usd * 0.15):,}"
    elif newly_flooded_km2 < 0.5:
        severity = "moderate"
        track = "Standard adjuster assignment with satellite evidence attached."
        payout_band = f"${int(coverage_limit_usd * 0.15):,} - ${int(coverage_limit_usd * 0.5):,}"
    else:
        severity = "major"
        track = "Priority catastrophe (CAT) team; expedite advance payment."
        payout_band = f"${int(coverage_limit_usd * 0.5):,} - ${int(coverage_limit_usd):,}"

    zone_note = (
        "Property is in a designated flood zone; flood peril is covered under the policy."
        if property_in_flood_zone
        else "Property is outside mapped flood zones; verify the policy includes flood peril."
    )

    return {
        "policyholder": policyholder,
        "property_address": property_address,
        "detected_flood_extent_km2": round(float(newly_flooded_km2), 4),
        "severity": severity,
        "flood_zone_note": zone_note,
        "recommended_track": track,
        "estimated_payout_band": payout_band,
        "coverage_limit_usd": coverage_limit_usd,
        "next_steps": [
            "Confirm the policyholder's identity and active policy number.",
            "Attach the Sentinel before/after imagery analysis to the claim file.",
            "Collect ground-level photos and a proof-of-loss inventory.",
            "Assign per the recommended track above.",
        ],
        "disclaimer": "Preliminary automated triage from satellite imagery. Not a coverage decision.",
    }


@tool
def search_aws_open_data(query: str, max_results: int = 8) -> dict:
    """Search the Registry of Open Data on AWS (RODA) for relevant open datasets.

    Mirrors the OpenDataMCP discovery capability: find open, cloud-hosted
    datasets (satellite imagery, climate, elevation, hazard data) by keyword so
    the agent can point an adjuster at authoritative data beyond Sentinel.

    Args:
        query: Keyword to match against dataset names, e.g. "sentinel", "flood",
               "elevation", "landsat".
        max_results: Maximum number of datasets to return (default 8).

    Returns:
        A dict with matching dataset names, descriptions, tags, and S3/STAC
        resource references.
    """
    q = query.lower()
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        resp = client.get(RODA_INDEX_URL)
        resp.raise_for_status()
        lines = resp.text.splitlines()

    import json as _json
    results = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        data = _json.loads(line)
        name = data.get("Name", "")
        desc = data.get("Description", "")
        tags = [t.lower() for t in data.get("Tags", [])]
        if q in name.lower() or q in desc.lower() or any(q in t for t in tags):
            results.append({
                "name": name,
                "description": desc[:300],
                "tags": data.get("Tags", [])[:8],
                "resources": [
                    {"ARN": r.get("ARN", ""), "region": r.get("Region", ""), "type": r.get("Type", "")}
                    for r in data.get("Resources", [])[:3]
                ],
            })
            if len(results) >= max_results:
                break

    return {"query": query, "count": len(results), "datasets": results}


# All flood-analysis tools, in the order the agent should generally reason about them.
FLOOD_TOOLS = [
    geocode_place,
    search_flood_scenes,
    compute_water_extent,
    analyze_flood_change,
    analyze_sar_flood,
    assess_flood_claim,
    search_aws_open_data,
]
