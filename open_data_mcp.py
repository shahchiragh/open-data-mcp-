import asyncio
import json
import time
import httpx
from fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("OpenDataMCP")

# Single NDJSON index — one JSON object per line, contains all datasets
INDEX_URL = "https://registry.opendata.aws/index.ndjson"

# In-memory cache
_datasets_cache: list[dict] | None = None
_cache_timestamp: float = 0
_cache_lock = asyncio.Lock()
CACHE_TTL_SECONDS = 3600  # refresh once per hour


async def _load_datasets() -> list[dict]:
    """Fetch and parse the NDJSON index from RODA (single HTTP request, no GitHub API)."""
    global _datasets_cache, _cache_timestamp

    async with _cache_lock:
        now = time.time()
        if _datasets_cache is not None and (now - _cache_timestamp) < CACHE_TTL_SECONDS:
            return _datasets_cache

        async with httpx.AsyncClient() as client:
            resp = await client.get(INDEX_URL, timeout=60)
            resp.raise_for_status()

        datasets = []
        for line in resp.text.splitlines():
            line = line.strip()
            if line:
                datasets.append(json.loads(line))

        _datasets_cache = datasets
        _cache_timestamp = now
        return datasets


@mcp.tool()
async def search_datasets(query: str, max_results: int = 10) -> list[dict]:
    """Search AWS Open Data Registry datasets by name.

    Args:
        query: Search term to match against dataset names (case-insensitive).
        max_results: Maximum number of results to return (default 10).

    Returns:
        A list of matching datasets with their name, description, tags, and resources.
    """
    query_lower = query.lower()
    datasets = await _load_datasets()

    results: list[dict] = []
    for data in datasets:
        if query_lower in data.get("Name", "").lower():
            resources = []
            for r in data.get("Resources", []):
                resources.append({
                    "Description": r.get("Description", ""),
                    "ARN": r.get("ARN", ""),
                    "Region": r.get("Region", ""),
                    "Type": r.get("Type", ""),
                })
            results.append({
                "Name": data.get("Name", ""),
                "Description": data.get("Description", ""),
                "Tags": data.get("Tags", []),
                "License": data.get("License", ""),
                "ManagedBy": data.get("ManagedBy", ""),
                "Resources": resources,
            })
            if len(results) >= max_results:
                break

    return results


@mcp.tool()
async def search_datasets_by_tags(tags: list[str], match_all: bool = True) -> dict:
    """Search AWS Open Data Registry datasets by one or more tags.

    Args:
        tags: One or more tags to filter datasets by (case-insensitive).
              Valid tags include things like "satellite imagery", "climate",
              "genomic", "machine learning", "earth observation", etc.
        match_all: If True (default), return datasets that have ALL specified tags.
                   If False, return datasets that have ANY of the specified tags.

    Returns:
        A dict with the total count of matching datasets and a list of their names.
        Use get_dataset_info to fetch full details for any specific dataset.
    """
    tags_lower = {t.lower() for t in tags}
    datasets = await _load_datasets()

    names: list[str] = []
    for data in datasets:
        dataset_tags = {t.lower() for t in data.get("Tags", [])}

        if match_all:
            if not tags_lower.issubset(dataset_tags):
                continue
        else:
            if not tags_lower.intersection(dataset_tags):
                continue

        names.append(data.get("Name", ""))

    return {"count": len(names), "datasets": names}


@mcp.tool()
async def search_stac_endpoints(query: str = "") -> dict:
    """Search for STAC (SpatioTemporal Asset Catalog) endpoints within RODA datasets.

    Scans all datasets for STAC endpoint URLs found in their resource Explore links.
    Optionally filters by dataset name.

    Args:
        query: Optional search term to filter by dataset name (case-insensitive).
               If empty, returns all datasets that have STAC endpoints.

    Returns:
        A dict with the total count and a list of objects containing dataset name
        and its associated STAC endpoint URLs.
    """
    import re

    datasets = await _load_datasets()
    query_lower = query.lower()

    # Regex to extract URLs from markdown links like [text](url)
    link_pattern = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

    results: list[dict] = []
    for data in datasets:
        if query_lower and query_lower not in data.get("Name", "").lower():
            continue

        stac_endpoints: list[dict] = []
        for resource in data.get("Resources", []):
            for explore_item in resource.get("Explore") or []:
                if "stac" in explore_item.lower():
                    match = link_pattern.search(explore_item)
                    if match:
                        stac_endpoints.append({
                            "label": match.group(1),
                            "url": match.group(2),
                        })
                    else:
                        # Plain URL or unstructured text
                        stac_endpoints.append({
                            "label": explore_item.strip(),
                            "url": explore_item.strip(),
                        })

        if stac_endpoints:
            results.append({
                "dataset": data.get("Name", ""),
                "stac_endpoints": stac_endpoints,
            })

    return {"count": len(results), "datasets": results}


@mcp.tool()
async def query_stac_items(
    stac_url: str,
    bbox: list[float] | None = None,
    datetime_range: str | None = None,
    limit: int = 10,
    cloud_cover_max: float | None = None,
) -> dict:
    """Query a STAC endpoint for available items (images/scenes).

    Queries a STAC API collection endpoint and returns matching items with their
    metadata and asset links.

    Args:
        stac_url: The STAC collection URL (e.g., from search_stac_endpoints).
                  Can be a collection URL or a /items endpoint URL.
        bbox: Optional bounding box filter as [west, south, east, north] in WGS84.
              Example: [-74.1, 40.6, -73.9, 40.8] for New York City.
        datetime_range: Optional datetime filter in RFC 3339 format.
                        Single date: "2024-01-01T00:00:00Z"
                        Range: "2024-01-01T00:00:00Z/2024-06-30T23:59:59Z"
        limit: Maximum number of items to return (default 10, max 100).
        cloud_cover_max: Optional maximum cloud cover percentage (0-100).
                         Only applies to optical imagery datasets.

    Returns:
        A dict with the number of items returned and a list of items, each containing
        id, datetime, bbox, cloud_cover (if available), and asset download links.
    """
    limit = min(limit, 100)

    # Normalize the URL to point to the /items endpoint
    items_url = stac_url.rstrip("/")
    if not items_url.endswith("/items"):
        items_url = items_url + "/items"

    # Build query parameters
    params: dict = {"limit": limit}
    if bbox:
        params["bbox"] = ",".join(str(v) for v in bbox)
    if datetime_range:
        params["datetime"] = datetime_range

    async with httpx.AsyncClient() as client:
        resp = await client.get(items_url, params=params, timeout=30)
        if resp.status_code != 200:
            return {"error": f"STAC request failed with status {resp.status_code}: {resp.text[:500]}"}
        data = resp.json()

    features = data.get("features", [])

    items: list[dict] = []
    for feature in features:
        props = feature.get("properties", {})
        cloud_cover = props.get("eo:cloud_cover")

        # Apply cloud cover filter client-side if specified
        if cloud_cover_max is not None and cloud_cover is not None:
            if cloud_cover > cloud_cover_max:
                continue

        # Extract asset hrefs
        assets = {}
        for asset_key, asset_val in feature.get("assets", {}).items():
            href = asset_val.get("href", "")
            title = asset_val.get("title", asset_key)
            assets[asset_key] = {"title": title, "href": href}

        items.append({
            "id": feature.get("id", ""),
            "datetime": props.get("datetime", ""),
            "bbox": feature.get("bbox"),
            "cloud_cover": cloud_cover,
            "platform": props.get("platform", ""),
            "assets": assets,
        })

    return {
        "items_returned": len(items),
        "number_matched": data.get("numberMatched"),
        "items": items,
    }


@mcp.tool()
async def get_scene_thumbnail(
    scene_id: str,
    stac_url: str = "https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a",
) -> dict:
    """Fetch the thumbnail URL (and metadata) for a specific STAC scene/item.

    Args:
        scene_id: The scene/item identifier (e.g., "S2A_19TCG_20241219_0_L2A").
        stac_url: The STAC collection URL. Defaults to the Sentinel-2 L2A COGs
                  collection on Earth Search.

    Returns:
        A dict with the scene id, datetime, cloud cover, thumbnail URL,
        and true color image (visual) URL. Returns an error if not found.
    """
    # Build the item URL: collection/items/scene_id
    items_url = stac_url.rstrip("/")
    if items_url.endswith("/items"):
        item_url = f"{items_url}/{scene_id}"
    else:
        item_url = f"{items_url}/items/{scene_id}"

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(item_url, timeout=30)
        if resp.status_code == 404:
            return {"error": f"Scene '{scene_id}' not found at {item_url}"}
        if resp.status_code != 200:
            return {"error": f"Request failed with status {resp.status_code}: {resp.text[:300]}"}

    data = resp.json()
    props = data.get("properties", {})
    assets = data.get("assets", {})

    thumbnail = assets.get("thumbnail", {}).get("href")
    visual = assets.get("visual", {}).get("href")

    return {
        "id": data.get("id", scene_id),
        "datetime": props.get("datetime", ""),
        "cloud_cover": props.get("eo:cloud_cover"),
        "platform": props.get("platform", ""),
        "bbox": data.get("bbox"),
        "thumbnail_url": thumbnail,
        "visual_url": visual,
    }


@mcp.tool()
async def get_dataset_info(name: str) -> dict:
    """Get detailed information about a specific AWS Open Data Registry dataset.

    Args:
        name: The exact or partial name of the dataset (case-insensitive).

    Returns:
        Full dataset record including name, description, tags, license, contact,
        documentation links, update frequency, managed by, and all resources.
        Returns an error message if no matching dataset is found.
    """
    name_lower = name.lower()
    datasets = await _load_datasets()

    # Try exact match first
    for data in datasets:
        if data.get("Name", "").lower() == name_lower:
            return data

    # Fall back to partial match
    for data in datasets:
        if name_lower in data.get("Name", "").lower():
            return data

    return {"error": f"No dataset found matching '{name}'"}


@mcp.tool()
async def calculate_ndvi(
    scene_id: str,
    stac_url: str = "https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a",
    bbox: list[float] | None = None,
    output_path: str | None = None,
) -> dict:
    """Calculate NDVI (Normalized Difference Vegetation Index) for a Sentinel-2 scene.

    NDVI = (NIR - Red) / (NIR + Red)
    For Sentinel-2: NIR = B08 (nir), Red = B04 (red).

    Args:
        scene_id: The STAC item/scene ID (e.g. "S2A_19TCG_20241219_0_L2A").
        stac_url: Full STAC collection URL. Defaults to Earth Search
            Sentinel-2 L2A.
        bbox: Optional bounding box [west, south, east, north] in EPSG:4326 to
              clip the calculation to a smaller area. Recommended for large scenes
              to reduce download time and memory usage.
        output_path: Optional file path to save the NDVI GeoTIFF. If not
                     provided, saves to ./ndvi_{scene_id}.tif.

    Returns:
        A dict with NDVI statistics (min, max, mean, median, std), output file path,
        CRS, and dimensions. Values range from -1 (water/bare) to +1 (dense vegetation).
    """
    import numpy as np
    import rasterio
    from rasterio.windows import from_bounds
    from pyproj import Transformer

    # Fetch the STAC item to get band URLs
    item_url = stac_url.rstrip("/")
    if item_url.endswith("/items"):
        item_url = f"{item_url}/{scene_id}"
    else:
        item_url = f"{item_url}/items/{scene_id}"

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(item_url, timeout=30)
        if resp.status_code == 404:
            return {"error": f"Scene '{scene_id}' not found at {item_url}"}
        resp.raise_for_status()

    item = resp.json()
    assets = item.get("assets", {})

    # Get Red (B04) and NIR (B08) band URLs
    red_asset = assets.get("red") or assets.get("B04") or assets.get("b04")
    nir_asset = assets.get("nir") or assets.get("B08") or assets.get("b08")

    if not red_asset:
        return {"error": "Could not find Red band (B04) asset in scene."}
    if not nir_asset:
        return {"error": "Could not find NIR band (B08) asset in scene."}

    red_url = red_asset.get("href", "")
    nir_url = nir_asset.get("href", "")

    if not red_url or not nir_url:
        return {"error": "Band URLs are empty."}

    # Read the bands using rasterio (supports COG over HTTP/S3)
    with rasterio.open(red_url) as red_src:
        profile = red_src.profile.copy()
        crs = red_src.crs

        if bbox:
            # Transform bbox from EPSG:4326 to the raster's CRS
            transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
            left, bottom = transformer.transform(bbox[0], bbox[1])
            right, top = transformer.transform(bbox[2], bbox[3])
            window = from_bounds(left, bottom, right, top, red_src.transform)
            red_band = red_src.read(1, window=window).astype(np.float32)
            transform = rasterio.windows.transform(window, red_src.transform)
        else:
            red_band = red_src.read(1).astype(np.float32)
            transform = red_src.transform

    with rasterio.open(nir_url) as nir_src:
        if bbox:
            transformer = Transformer.from_crs("EPSG:4326", nir_src.crs, always_xy=True)
            left, bottom = transformer.transform(bbox[0], bbox[1])
            right, top = transformer.transform(bbox[2], bbox[3])
            window = from_bounds(left, bottom, right, top, nir_src.transform)
            nir_band = nir_src.read(1, window=window).astype(np.float32)
        else:
            nir_band = nir_src.read(1).astype(np.float32)

    # Calculate NDVI: (NIR - Red) / (NIR + Red)
    denominator = nir_band + red_band
    # Avoid division by zero
    ndvi = np.where(denominator == 0, 0.0, (nir_band - red_band) / denominator)

    # Clip NDVI to valid range [-1, 1]
    ndvi = np.clip(ndvi, -1.0, 1.0)

    # Compute statistics (excluding nodata/zero-denominator areas)
    valid_mask = denominator > 0
    if valid_mask.any():
        ndvi_valid = ndvi[valid_mask]
        stats = {
            "min": float(np.min(ndvi_valid)),
            "max": float(np.max(ndvi_valid)),
            "mean": float(np.mean(ndvi_valid)),
            "median": float(np.median(ndvi_valid)),
            "std": float(np.std(ndvi_valid)),
        }
    else:
        stats = {"min": 0.0, "max": 0.0, "mean": 0.0, "median": 0.0, "std": 0.0}

    # Save NDVI as GeoTIFF
    if not output_path:
        output_path = f"./ndvi_{scene_id}.tif"

    profile.update(
        dtype=rasterio.float32,
        count=1,
        compress="deflate",
        nodata=0.0,
        transform=transform,
        height=ndvi.shape[0],
        width=ndvi.shape[1],
    )

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(ndvi, 1)

    return {
        "scene_id": scene_id,
        "output_path": output_path,
        "crs": str(crs),
        "dimensions": {"height": ndvi.shape[0], "width": ndvi.shape[1]},
        "statistics": stats,
    }


@mcp.tool()
async def compare_ndvi_sidebyside(
    scene_id_1: str,
    scene_id_2: str,
    bbox: list[float],
    label_1: str = "Scene 1",
    label_2: str = "Scene 2",
    show_difference: bool = True,
    colormap: str = "RdYlGn",
    output_path: str = "",
    stac_url: str = "https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a",
) -> str:
    """Generate a side-by-side NDVI comparison plot for two Sentinel-2 scenes.

    Computes NDVI for both scenes within the given bounding box, then produces
    a multi-panel PNG figure showing each scene's NDVI and optionally the difference.

    Args:
        scene_id_1: First Sentinel-2 scene ID (e.g. recovery/baseline year).
        scene_id_2: Second Sentinel-2 scene ID (e.g. drought/event year).
        bbox: Bounding box [west, south, east, north] in EPSG:4326.
        label_1: Label for the first scene panel.
        label_2: Label for the second scene panel.
        show_difference: If True, adds a third panel showing NDVI difference.
        colormap: Matplotlib colormap for NDVI panels (default: RdYlGn).
        output_path: Output PNG path. Auto-generated if empty.
        stac_url: STAC collection URL. Defaults to Sentinel-2 L2A on Earth Search.

    Returns:
        Summary string with output file path and basic NDVI statistics.
    """
    import numpy as np
    import rasterio
    from rasterio.windows import from_bounds
    from pyproj import Transformer
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm

    async def _fetch_ndvi(scene_id: str) -> tuple[np.ndarray, dict]:
        """Fetch Red and NIR bands for a scene and compute NDVI within bbox.

        Returns:
            Tuple of (ndvi_array, rasterio_profile) so we can save GeoTIFFs.
        """
        item_url = stac_url.rstrip("/")
        if item_url.endswith("/items"):
            item_url = f"{item_url}/{scene_id}"
        else:
            item_url = f"{item_url}/items/{scene_id}"

        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(item_url, timeout=30)
            resp.raise_for_status()

        item = resp.json()
        assets = item.get("assets", {})

        red_asset = assets.get("red") or assets.get("B04") or assets.get("b04")
        nir_asset = assets.get("nir") or assets.get("B08") or assets.get("b08")
        if not red_asset or not nir_asset:
            raise ValueError(f"Cannot find Red/NIR bands for scene {scene_id}")

        red_url = red_asset["href"]
        nir_url = nir_asset["href"]

        west, south, east, north = bbox

        with rasterio.open(red_url) as src:
            crs = src.crs
            transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
            left, bottom = transformer.transform(west, south)
            right, top = transformer.transform(east, north)
            window = from_bounds(left, bottom, right, top, src.transform)
            red = src.read(1, window=window).astype(np.float32)
            transform = src.window_transform(window)
            profile = src.profile.copy()
            profile.update(
                dtype=rasterio.float32,
                count=1,
                compress="deflate",
                nodata=0.0,
                transform=transform,
                height=int(window.height),
                width=int(window.width),
                crs=crs,
            )

        with rasterio.open(nir_url) as src:
            crs = src.crs
            transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
            left, bottom = transformer.transform(west, south)
            right, top = transformer.transform(east, north)
            window = from_bounds(left, bottom, right, top, src.transform)
            nir = src.read(1, window=window).astype(np.float32)

        denom = nir + red
        ndvi = np.where(denom == 0, 0.0, (nir - red) / denom)
        return np.clip(ndvi, -1.0, 1.0), profile

    # Compute NDVI for both scenes
    ndvi_1, profile_1 = await _fetch_ndvi(scene_id_1)
    ndvi_2, profile_2 = await _fetch_ndvi(scene_id_2)

    # Handle shape mismatch by trimming to common dimensions
    min_h = min(ndvi_1.shape[0], ndvi_2.shape[0])
    min_w = min(ndvi_1.shape[1], ndvi_2.shape[1])
    ndvi_1 = ndvi_1[:min_h, :min_w]
    ndvi_2 = ndvi_2[:min_h, :min_w]

    # Compute difference (scene2 - scene1)
    diff = ndvi_2 - ndvi_1

    # Determine output paths
    if not output_path:
        output_path = f"ndvi_comparison_{scene_id_1[:20]}_vs_{scene_id_2[:20]}.png"
    base_stem = output_path.rsplit(".", 1)[0]  # strip extension
    tif_path_1 = f"{base_stem}_scene1.tif"
    tif_path_2 = f"{base_stem}_scene2.tif"
    tif_path_diff = f"{base_stem}_diff.tif"

    # Save NDVI GeoTIFFs for later review
    for arr, profile, path in [
        (ndvi_1, profile_1, tif_path_1),
        (ndvi_2, profile_2, tif_path_2),
        (diff, profile_1, tif_path_diff),
    ]:
        p = profile.copy()
        p.update(height=min_h, width=min_w)
        with rasterio.open(path, "w", **p) as dst:
            dst.write(arr, 1)

    # Create figure
    n_panels = 3 if show_difference else 2
    fig, axes = plt.subplots(1, n_panels, figsize=(7 * n_panels, 6))

    # Panel 1 — first scene
    im1 = axes[0].imshow(ndvi_1, cmap=colormap, vmin=-1, vmax=1)
    axes[0].set_title(label_1, fontsize=13, fontweight="bold")
    axes[0].axis("off")
    plt.colorbar(im1, ax=axes[0], fraction=0.046, pad=0.04, label="NDVI")

    # Panel 2 — second scene
    im2 = axes[1].imshow(ndvi_2, cmap=colormap, vmin=-1, vmax=1)
    axes[1].set_title(label_2, fontsize=13, fontweight="bold")
    axes[1].axis("off")
    plt.colorbar(im2, ax=axes[1], fraction=0.046, pad=0.04, label="NDVI")

    # Panel 3 — difference
    if show_difference:
        vmax_diff = max(abs(float(diff.min())), abs(float(diff.max())), 0.01)
        norm = TwoSlopeNorm(vmin=-vmax_diff, vcenter=0, vmax=vmax_diff)
        im3 = axes[2].imshow(diff, cmap="RdBu", norm=norm)
        axes[2].set_title(
            f"Difference ({label_2} \u2212 {label_1})", fontsize=13, fontweight="bold"
        )
        axes[2].axis("off")
        plt.colorbar(im3, ax=axes[2], fraction=0.046, pad=0.04, label="\u0394NDVI")

    plt.tight_layout()

    # Save figure
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    # Build stats summary
    stats = (
        f"Comparison saved to: {output_path}\n"
        f"GeoTIFFs saved:\n"
        f"  Scene 1 NDVI: {tif_path_1}\n"
        f"  Scene 2 NDVI: {tif_path_2}\n"
        f"  Difference:   {tif_path_diff}\n"
        f"\n"
        f"{label_1} — median NDVI: {np.nanmedian(ndvi_1):.3f}, "
        f"mean: {np.nanmean(ndvi_1):.3f}\n"
        f"{label_2} — median NDVI: {np.nanmedian(ndvi_2):.3f}, "
        f"mean: {np.nanmean(ndvi_2):.3f}\n"
        f"Difference — median \u0394NDVI: {np.nanmedian(diff):.3f}, "
        f"mean: {np.nanmean(diff):.3f}\n"
        f"Pixels degraded (\u0394NDVI < -0.1): "
        f"{(diff < -0.1).sum() / diff.size * 100:.1f}%"
    )
    return stats


@mcp.tool()
async def classify_ndvi(
    input_path: str,
    output_path: str = "",
    label: str = "NDVI Classification",
    save_geotiff: bool = True,
) -> dict:
    """Classify an NDVI raster into land cover classes and generate a visualization.

    Applies standard NDVI thresholds (following NASA/deforestation analysis conventions)
    to categorize pixels into land cover types:
      - Class 1 (Water):              NDVI < 0
      - Class 2 (Built-up / Barren):  0 ≤ NDVI < 0.1
      - Class 3 (Shrub & Grassland):  0.1 ≤ NDVI < 0.3
      - Class 4 (Sparse Vegetation):  0.3 ≤ NDVI < 0.5
      - Class 5 (Dense Vegetation):   NDVI ≥ 0.5

    Args:
        input_path: Path to an NDVI GeoTIFF file (values in [-1, 1]).
        output_path: Output PNG path for the classification map.
                     Auto-generated from input filename if empty.
        label: Title for the classification plot.
        save_geotiff: If True, also saves the classified raster as a GeoTIFF.

    Returns:
        A dict with class pixel counts, percentages, output file paths,
        and classification summary statistics.
    """
    import numpy as np
    import rasterio
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, BoundaryNorm
    from matplotlib.patches import Patch
    import os

    # Read the NDVI raster
    with rasterio.open(input_path) as src:
        ndvi = src.read(1).astype(np.float32)
        profile = src.profile.copy()
        crs = src.crs
        transform = src.transform

    # Define classification bins and labels
    class_bins = [-1.0, 0.0, 0.1, 0.3, 0.5, 1.0]
    class_names = [
        "Water",
        "Built-up / Barren",
        "Shrub & Grassland",
        "Sparse Vegetation",
        "Dense Vegetation",
    ]
    class_colors = ["#2166ac", "#d6604d", "#f4a582", "#92c5de", "#1b7837"]

    # Apply classification using digitize (returns class index 1-5)
    classified = np.digitize(ndvi, bins=class_bins[1:], right=False)
    # digitize gives 0 for values < first bin edge, and up to len(bins) for values >= last
    # Remap: values < 0 → class 1, 0-0.1 → class 2, 0.1-0.3 → class 3, 0.3-0.5 → class 4, >=0.5 → class 5
    classified = np.clip(classified, 1, 5)

    # Compute class statistics
    total_pixels = ndvi.size
    class_stats = {}
    for i, name in enumerate(class_names, start=1):
        count = int((classified == i).sum())
        pct = count / total_pixels * 100
        class_stats[name] = {"class_id": i, "pixel_count": count, "percentage": round(pct, 2)}

    # Determine output paths
    if not output_path:
        base = os.path.splitext(os.path.basename(input_path))[0]
        output_path = f"{base}_classified.png"

    base_stem = output_path.rsplit(".", 1)[0]
    tif_output_path = f"{base_stem}.tif"

    # Save classified GeoTIFF if requested
    if save_geotiff:
        tif_profile = profile.copy()
        tif_profile.update(
            dtype=rasterio.uint8,
            count=1,
            compress="deflate",
            nodata=0,
        )
        with rasterio.open(tif_output_path, "w", **tif_profile) as dst:
            dst.write(classified.astype(np.uint8), 1)

    # Create visualization
    cmap = ListedColormap(class_colors)
    norm = BoundaryNorm(boundaries=[0.5, 1.5, 2.5, 3.5, 4.5, 5.5], ncolors=5)

    fig, ax = plt.subplots(1, 1, figsize=(10, 8))
    im = ax.imshow(classified, cmap=cmap, norm=norm, interpolation="nearest")
    ax.set_title(label, fontsize=14, fontweight="bold")
    ax.axis("off")

    # Build legend
    legend_patches = [
        Patch(facecolor=class_colors[i], label=f"{class_names[i]} ({class_stats[class_names[i]]['percentage']:.1f}%)")
        for i in range(5)
    ]
    ax.legend(
        handles=legend_patches,
        loc="lower right",
        fontsize=9,
        framealpha=0.9,
        title="Land Cover Class",
    )

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    # Build result
    result = {
        "input_path": input_path,
        "classification_map": output_path,
        "crs": str(crs) if crs else "unknown",
        "dimensions": {"height": ndvi.shape[0], "width": ndvi.shape[1]},
        "total_pixels": total_pixels,
        "classes": class_stats,
        "dominant_class": max(class_stats, key=lambda k: class_stats[k]["pixel_count"]),
    }

    if save_geotiff:
        result["classified_geotiff"] = tif_output_path

    return result


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
