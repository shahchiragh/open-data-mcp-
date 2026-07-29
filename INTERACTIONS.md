# Build Journal — Prompts & Interactions

A record of how this repo was built with Kiro: the tools created, how they were added, and
how the FloodGuard agent and geospatial powers were wired up.

> **Note on accuracy:** this journal was reconstructed from the repository artifacts (git
> history, source files, and `floodguard/DEPLOYMENT.md`), not from a saved verbatim chat
> transcript. The prompts below are representative of what drove each step and are written so
> you can reuse or adapt them. Where a step maps to a real commit or file, that's noted.

---

## Phase 1 — The OpenDataMCP server

Git history shows the starting point:

```
2819e54  Add Open Data Registry MCP server with search by name, tags, and dataset info tools
```

So the server began as RODA discovery and grew into a full STAC + analysis toolkit.

### 1.1 Scaffold the MCP server

> Prompt: *"Create a FastMCP server in `open_data_mcp.py` that exposes the AWS Registry of
> Open Data. Fetch the RODA NDJSON index once, cache it in memory for an hour, and add tools
> to search datasets by name, search by tags (match all or any), and get full info for a
> named dataset."*

Result: `_load_datasets()` (cached, async, lock-guarded) plus `search_datasets`,
`search_datasets_by_tags`, and `get_dataset_info`.

### 1.2 Add STAC discovery + querying

> Prompt: *"Add tools to discover STAC endpoints referenced inside RODA datasets, and to
> query a STAC collection by bounding box, datetime range, cloud cover, and limit. Return
> item ids, datetimes, bbox, cloud cover, and asset download links."*

Result: `search_stac_endpoints` (regex-extracts endpoint URLs from RODA "Explore" links) and
`query_stac_items` (client-side cloud-cover filtering, `/items` URL normalization).

> Prompt: *"Add a `get_scene_thumbnail` tool that, given a scene id, returns the thumbnail
> and true-color (visual) asset URLs, defaulting to the Sentinel-2 L2A collection on Earth
> Search."*

### 1.3 Add raster analysis tools (NDVI / NDBI)

> Prompt: *"Add a `calculate_ndvi` tool for Sentinel-2. Fetch the STAC item, read the Red
> (B04) and NIR (B08) COGs with rasterio over HTTP, optionally clip to a bbox (reproject the
> bbox into the raster CRS with pyproj), compute NDVI = (NIR − Red)/(NIR + Red), clip to
> [-1,1], write a GeoTIFF, and return min/max/mean/median/std."*

> Prompt: *"Now add `calculate_ndbi` the same way using SWIR (B11) and NIR (B08). B11 is 20 m
> and B08 is 10 m, so resample NIR down to the SWIR grid with scipy zoom before the band
> math."*

### 1.4 Add comparison + classification tools

> Prompt: *"Add `compare_ndvi_sidebyside` and `compare_ndbi_sidebyside` that compute the
> index for two scenes over the same bbox, trim to common dimensions, and render a matplotlib
> figure (scene 1, scene 2, and a diverging difference panel). Save the panels as GeoTIFFs
> too and return a stats summary. Use the Agg backend so it works headless."*

> Prompt: *"Add `classify_ndvi` that thresholds an NDVI raster into 5 land-cover classes
> (water, built-up/barren, shrub & grassland, sparse veg, dense veg) using NASA-style
> breakpoints, renders a classified map with a legend, and optionally writes a uint8
> GeoTIFF."*

---

## Phase 2 — Drought analysis (Shasta Lake)

> Prompt: *"Using the NDVI tools, pull Sentinel-2 scenes over Shasta Lake for late September
> in a recovery year (2017) and an extreme drought year (2021), then write
> `drought_analysis.py` that loads both NDVI rasters, computes per-class vegetation stats,
> writes a 2021−2017 difference raster, prints a change report, and renders a three-panel
> comparison figure."*

Outputs committed to the repo:

- `ndvi_shasta_2017_recovery.tif`, `ndvi_shasta_2021_drought.tif`
- `ndvi_shasta_diff_2021_vs_2017.tif`
- `shasta_2017_ndvi_classified.{png,tif}`, `shasta_2021_ndvi_classified.{png,tif}`
- `shasta_drought_ndvi_comparison.png`

---

## Phase 3 — The FloodGuard agent (Amazon Bedrock AgentCore)

The full, reproducible record lives in [`floodguard/DEPLOYMENT.md`](./floodguard/DEPLOYMENT.md).
The driving prompts:

### 3.1 Scaffold the agent

> Prompt: *"Scaffold an AgentCore project called `floodguard`: Python, Strands framework,
> Bedrock model provider, HTTP protocol, CodeZip build, no memory. Target account/region
> prod / us-east-1 and pin the runtime to Python 3.12."*

Maps to the `agentcore create …` command in DEPLOYMENT.md §4.1.

### 3.2 Build the flood toolset

> Prompt: *"Write `flood_tools.py` with self-contained Strands tools so the agent works the
> same locally and deployed: `geocode_place` (Nominatim), `search_flood_scenes`
> (Sentinel-1/2 via Earth Search STAC), `compute_water_extent` and `analyze_flood_change`
> (Sentinel-2 NDWI), `analyze_sar_flood` (Sentinel-1 VV backscatter, warped via WarpedVRT
> because GRD assets are GCP-georeferenced), `assess_flood_claim` (transparent triage bands),
> and `search_aws_open_data` (RODA). Cap the read window so a chatbot turn stays fast."*

### 3.3 Wire the agent + optional MCP client

> Prompt: *"In `main.py`, assemble the flood tools into a Strands `Agent` with an
> insurance-support system prompt, cache one agent per session id (bounded LRU), and stream
> responses through `@app.entrypoint`. Add an optional stdio MCP client that attaches the
> repo's `open_data_mcp.py` when `OPEN_DATA_MCP_PATH` is set, and returns `None` (so the
> cloud runtime doesn't depend on it) otherwise."*

Result: `main.py` + `mcp_client/client.py`.

### 3.4 Add geospatial deps, test, deploy

> Prompt: *"Add rasterio, numpy, pyproj, httpx to `pyproject.toml`, `uv sync`, run the direct
> pipeline test (`test_maui.py`) and the LLM end-to-end test (`test_agent.py`), then
> `agentcore validate` and `agentcore deploy --target prod`."*

### 3.5 The demo

> Prompt (`maui_demo_prompt.txt`): *"A policyholder named Keola in Kihei, Maui was flooded
> during the March 2026 Kona storm… find Sentinel-2 imagery before and after the event,
> estimate how much new flooding occurred using a small analysis area, and give a preliminary
> claim triage. Cite the scene IDs and dates you used."*

The deployed agent geocoded Kīhei, discovered real before/after Sentinel-2 scenes, ran NDWI
change detection reading COGs over HTTPS inside the microVM, and returned a triage with cited
scene ids. See DEPLOYMENT.md §7 for the representative output.

---

## Phase 4 — Geospatial Kiro Power Pack

> Prompt: *"Add the Geospatial Power Pack so Kiro itself can search STAC catalogs, read COG
> windows, run band math and zonal stats, and do GeoAI embeddings/change detection — with a
> single credential surface in `mcp.json`."*

The pack (`sample-geospatial-kiro-power-pack/`) provides:

- **A hub** (`kiro-geospatial`) and shared base (`geo-common`).
- **Pillar A (data access):** `geo-stac`, `geo-vector`, `geo-geocode-route`, `geo-terrain`,
  `geo-weather-climate`, `geo-biodiversity`, `geo-ogc`.
- **Pillar B (processing):** `geo-ops`, `geo-formats`, `geo-query`, `geo-raster`,
  `geo-pointcloud`, `geo-index`, `geo-3d`, `geo-warehouse`.
- **Pillar C (GeoAI):** `geo-foundation-models`, `geo-embedding-search`.
- **Skills** (COG/GeoParquet, CRS handling, tool selection, spatial SQL, tiling, GeoAI
  embedding) and **steering** workflows (COG conversion, zonal stats, STAC discover→analyze,
  embedding change detection, geocode→route).

These tools were used in this Geospatial MCP Build to search datasets, compute indices, and
run the change-detection style analyses reflected in the Shasta and FloodGuard work.

---

## Reusable prompt patterns

A few patterns that worked well across the session:

- **"Add a tool that …, read the COG over HTTP with rasterio, clip to a bbox by reprojecting
  the bbox into the raster CRS, and return stats + a GeoTIFF."** — the shape of every raster
  tool here.
- **"Make the tools self-contained so the agent behaves identically locally and deployed;
  keep the MCP server optional."** — the portability principle behind FloodGuard.
- **"Use the Agg matplotlib backend and write PNG + GeoTIFF outputs"** — so everything works
  headless and stays auditable.
- **"Cite the scene ids and dates"** — bake provenance into agent output for anything that
  makes a decision.

---

## Want a real transcript next time?

This journal is a reconstruction. To capture exact prompts going forward, you can:

- Keep prompts in files (like `maui_demo_prompt.txt`) and reference them from commits.
- Write meaningful commit messages per capability (as with commit `2819e54`).
- Append notable prompts to this file as you go — a Kiro **agent hook** on `agentStop` can
  automate that.
