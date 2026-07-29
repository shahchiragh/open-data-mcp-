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


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
