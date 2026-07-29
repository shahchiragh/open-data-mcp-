# Geospatial MCP Build — Open Data MCP, Drought Analysis & FloodGuard Agent

A hands-on exploration of geospatial AI built with [Kiro](https://kiro.dev). This repo
brings together three things that build on each other:

1. **`OpenDataMCP`** — a custom [FastMCP](https://github.com/jlowin/fastmcp) server that
   turns the [AWS Registry of Open Data (RODA)](https://registry.opendata.aws/) and public
   STAC catalogs into agent-callable tools (dataset search, STAC queries, and
   NDVI/NDBI/land-cover analysis on Sentinel-2 imagery).
2. **A drought analysis script** — a standalone NDVI comparison of Shasta Lake, CA between
   a recovery year (2017) and an extreme drought year (2021).
3. **FloodGuard** — a geospatially-aware flood-insurance claims agent built on the
   **Strands Agents SDK** and deployed to **Amazon Bedrock AgentCore**, plus the
   **Geospatial Kiro Power Pack** used to give Kiro itself geospatial superpowers.

> If you want the story of *how* this was built — the prompts, the tools added, the agent
> powers wired up — see [`INTERACTIONS.md`](./INTERACTIONS.md). For the verbatim lab
> instructions and prompts, see [`GEOSPATIAL_MCP_BUILD_LABS.md`](./GEOSPATIAL_MCP_BUILD_LABS.md).

---

## Repository layout

```
.
├── open_data_mcp.py              # FastMCP server: RODA + STAC + NDVI/NDBI tools
├── drought_analysis.py           # Shasta Lake NDVI drought comparison (2017 vs 2021)
├── ndvi_shasta_*.tif             # NDVI rasters + difference GeoTIFFs (outputs)
├── shasta_*_ndvi_classified.*    # Land-cover classification outputs (PNG + GeoTIFF)
├── shasta_drought_ndvi_comparison.png
│
├── floodguard/                   # Flood-claims agent on Amazon Bedrock AgentCore
│   ├── app/floodguard/           # Strands agent + self-contained flood tools
│   ├── agentcore/                # AgentCore config + CDK deployment
│   ├── DEPLOYMENT.md             # Full, reproducible build + deploy record
│   └── maui_demo_prompt.txt      # Demo scenario (Maui 2026 flooding)
│
└── sample-geospatial-kiro-power-pack/   # The Geospatial Kiro Power (MCP servers + skills)
```

---

## 1. OpenDataMCP server

`open_data_mcp.py` is a single-file MCP server. It fetches the RODA NDJSON index once
(cached for an hour), then exposes discovery and analysis tools over stdio. Imagery is read
cloud-natively via COG byte-range reads — no bulk downloads.

### Tools

| Tool | What it does |
| --- | --- |
| `search_datasets` | Search RODA datasets by name |
| `search_datasets_by_tags` | Filter RODA datasets by tags (match all/any) |
| `get_dataset_info` | Full record for a specific dataset |
| `search_stac_endpoints` | Discover STAC endpoints referenced in RODA datasets |
| `query_stac_items` | Query a STAC collection by bbox / datetime / cloud cover |
| `get_scene_thumbnail` | Thumbnail + true-color URL for a specific scene |
| `calculate_ndvi` | NDVI (vegetation) for a Sentinel-2 scene → GeoTIFF + stats |
| `calculate_ndbi` | NDBI (built-up) for a Sentinel-2 scene → GeoTIFF + stats |
| `compare_ndvi_sidebyside` | Two-scene NDVI comparison figure + difference raster |
| `compare_ndbi_sidebyside` | Two-scene NDBI comparison figure + difference raster |
| `classify_ndvi` | Threshold an NDVI raster into 5 land-cover classes + map |

### Run it

```bash
# Dependencies: fastmcp, httpx, numpy, rasterio, pyproj, scipy, matplotlib
uv run python open_data_mcp.py     # serves over stdio
```

### Register it with Kiro (MCP)

Add it to your workspace MCP config at `.kiro/settings/mcp.json`:

```json
{
  "mcpServers": {
    "OpenDataMCP": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/repo", "open_data_mcp.py"],
      "disabled": false,
      "autoApprove": ["search_datasets", "search_datasets_by_tags", "get_dataset_info"]
    }
  }
}
```

---

## 2. Drought analysis (Shasta Lake)

`drought_analysis.py` loads two pre-computed NDVI rasters (2017 recovery vs 2021 extreme
drought), computes per-class vegetation statistics, writes a difference raster, and renders
a three-panel comparison figure.

```bash
uv run python drought_analysis.py
# → shasta_drought_ndvi_comparison.png
# → ndvi_shasta_diff_2021_vs_2017.tif
```

The report quantifies the drought signal: lower mean NDVI in 2021, a rise in the
water/bare-soil class as the lake receded, and dense-vegetation loss on the surrounding
hillsides.

---

## 3. FloodGuard agent (Amazon Bedrock AgentCore)

`floodguard/` is a demo AI support chatbot for a fictional flood-insurance agency. It is
geospatially aware, understands **Sentinel-2 (optical, NDWI)** and **Sentinel-1 (SAR VV
backscatter)** imagery, and triages flood claims from a before/after scene pair.

Highlights:

- Built with the **Strands Agents SDK**, wrapped by `BedrockAgentCoreApp`.
- Seven self-contained tools (`geocode_place`, `search_flood_scenes`,
  `analyze_flood_change`, `analyze_sar_flood`, `assess_flood_claim`, …) so the agent behaves
  identically locally and in the cloud.
- Optional **OpenDataMCP** integration over stdio in local dev (set `OPEN_DATA_MCP_PATH`).
- Deployed via **AWS CDK** to AgentCore Runtime (CodeZip, ARM64, Python 3.12).

Full, reproducible build and deploy steps — including the Maui 2026 flooding demo — are in
[`floodguard/DEPLOYMENT.md`](./floodguard/DEPLOYMENT.md).

> **Security note:** the reference deployment uses `networkMode: PUBLIC`. Access is still
> gated by IAM SigV4 (no unauthenticated calls), but for production you should scope invoke
> permissions to specific principals and consider a JWT authorizer or VPC networking.

---

## 4. Geospatial Kiro Power Pack

`sample-geospatial-kiro-power-pack/` is a modular Kiro Power that gives Kiro unified access
to the fragmented geospatial landscape. It is organized around a dual-fragmentation framing:

- **Pillar A — data access:** `geo-stac`, `geo-vector`, `geo-geocode-route`, `geo-terrain`,
  `geo-weather-climate`, `geo-biodiversity`, `geo-ogc`.
- **Pillar B — processing/compute:** `geo-ops`, `geo-formats`, `geo-query`, `geo-raster`,
  `geo-pointcloud`, `geo-index`, `geo-3d`, `geo-warehouse`.
- **Pillar C — GeoAI:** `geo-foundation-models` (Clay, Prithvi, SatCLIP, SAMGeo),
  `geo-embedding-search`.
- Plus a **hub** (`kiro-geospatial`), a shared base (`geo-common`), commercial imagery, and
  an `aws-geo-compute` peer power.

It also ships **skills** (COG/GeoParquet guidance, CRS handling, tool selection, spatial
SQL) and **steering** workflows (COG conversion, zonal statistics, STAC discover→analyze,
embedding change detection). See its own `bundle-manifest.json` and `examples/` for details.

### Install it as a Kiro Power

Kiro Powers can be installed straight from GitHub repos. To add the geospatial power on the
remote machine where you are running Kiro:

1. Copy this link and paste it into your browser on the remote machine (where Kiro runs):
   [https://github.com/aws-samples/sample-geospatial-kiro-power-pack](https://github.com/aws-samples/sample-geospatial-kiro-power-pack)
2. Open a new terminal in the workshop folder, clone the repository, and change into it:

   ```bash
   git clone https://github.com/aws-samples/sample-geospatial-kiro-power-pack.git
   cd ./sample-geospatial-kiro-power-pack/
   ```

3. Follow the **Installation** instructions from the repository and install all of the MCP
   servers listed, then configure them. You do **not** need to create a new `uv` environment —
   you are already in one that is activated.

Your existing MCP servers are left untouched. Once installation completes, you should have
the full set of geospatial powers (the hub, data-access, processing, and GeoAI servers listed
above) available in Kiro.

---

## Key takeaways

- **MCP turns open geospatial data into agent tools.** A single small server (`open_data_mcp.py`)
  makes 1,000+ RODA datasets and public STAC catalogs directly callable by an AI agent.
- **Cloud-native reads beat downloads.** Every raster operation here uses COG byte-range
  reads over HTTPS against public, credential-free buckets — fast enough to run inside an
  AgentCore microVM.
- **Portability by design.** FloodGuard's tools are self-contained so the agent behaves the
  same in local dev and when deployed; the MCP server is an optional local enhancement, not a
  runtime dependency.
- **Same science, two indices, two sensors.** NDVI/NDWI/NDBI are simple band-ratio indices;
  swapping bands (and using SAR when it's cloudy) covers vegetation, water, and built-up
  analysis with one mental model.
- **Powers scale Kiro's reach.** The Geospatial Power Pack packages dozens of specialized
  MCP servers behind one credential surface, with skills and steering that teach Kiro *when*
  to use each one.

## Prerequisites

- Python 3.10+ (3.12 recommended) and [`uv`](https://docs.astral.sh/uv/)
- Node.js 20+ (for the AgentCore CDK deploy path)
- AWS credentials + Bedrock model access (only for deploying FloodGuard)

## License

See the individual subprojects for their licenses (the Power Pack includes its own `LICENSE`
and `NOTICE`).
