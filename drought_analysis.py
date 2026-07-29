"""
Shasta Lake Drought Analysis — NDVI Comparison
Compares 2017 (recovery year) vs 2021 (extreme drought year)
using Sentinel-2 derived NDVI.
"""
import numpy as np
import rasterio
import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm


def load_ndvi(path: str) -> tuple[np.ndarray, dict]:
    """Load a single-band NDVI GeoTIFF."""
    with rasterio.open(path) as src:
        ndvi = src.read(1)
        profile = src.profile
    return ndvi, profile


def compute_stats(ndvi: np.ndarray, label: str) -> dict:
    """Compute vegetation classification stats."""
    valid = ndvi[ndvi != 0]  # exclude nodata
    total_pixels = valid.size

    water_bare = np.sum(valid < 0.1)
    sparse_veg = np.sum((valid >= 0.1) & (valid < 0.3))
    moderate_veg = np.sum((valid >= 0.3) & (valid < 0.6))
    dense_veg = np.sum(valid >= 0.6)

    stats = {
        "label": label,
        "mean_ndvi": float(np.mean(valid)),
        "median_ndvi": float(np.median(valid)),
        "std_ndvi": float(np.std(valid)),
        "water_bare_pct": 100.0 * water_bare / total_pixels,
        "sparse_veg_pct": 100.0 * sparse_veg / total_pixels,
        "moderate_veg_pct": 100.0 * moderate_veg / total_pixels,
        "dense_veg_pct": 100.0 * dense_veg / total_pixels,
    }
    return stats


def main():
    # Load both NDVI rasters
    ndvi_2017, _ = load_ndvi("ndvi_shasta_2017_recovery.tif")
    ndvi_2021, profile = load_ndvi("ndvi_shasta_2021_drought.tif")

    # Compute stats
    stats_2017 = compute_stats(ndvi_2017, "2017 (Recovery)")
    stats_2021 = compute_stats(ndvi_2021, "2021 (Extreme Drought)")

    # Compute difference: 2021 - 2017 (negative = vegetation loss)
    ndvi_diff = ndvi_2021 - ndvi_2017

    # Save difference raster
    diff_profile = profile.copy()
    diff_profile.update(dtype=rasterio.float32, count=1, compress="deflate")
    with rasterio.open("ndvi_shasta_diff_2021_vs_2017.tif", "w", **diff_profile) as dst:
        dst.write(ndvi_diff.astype(np.float32), 1)

    # --- Print Analysis Report ---
    print("=" * 70)
    print("   SHASTA LAKE DROUGHT ANALYSIS — NDVI COMPARISON")
    print("   Sentinel-2 L2A | Late September | bbox: Shasta Lake area")
    print("=" * 70)

    for stats in [stats_2017, stats_2021]:
        print(f"\n  📅 {stats['label']}")
        print(f"     Mean NDVI:       {stats['mean_ndvi']:.4f}")
        print(f"     Median NDVI:     {stats['median_ndvi']:.4f}")
        print(f"     Std Dev:         {stats['std_ndvi']:.4f}")
        print(f"     ─────────────────────────────────────")
        print(f"     Water/Bare:      {stats['water_bare_pct']:5.1f}%  (NDVI < 0.1)")
        print(f"     Sparse Veg:      {stats['sparse_veg_pct']:5.1f}%  (0.1 ≤ NDVI < 0.3)")
        print(f"     Moderate Veg:    {stats['moderate_veg_pct']:5.1f}%  (0.3 ≤ NDVI < 0.6)")
        print(f"     Dense Veg:       {stats['dense_veg_pct']:5.1f}%  (NDVI ≥ 0.6)")

    # Change summary
    print(f"\n{'─' * 70}")
    print("  📊 CHANGE ANALYSIS (2021 minus 2017)")
    print(f"{'─' * 70}")
    mean_change = stats_2021["mean_ndvi"] - stats_2017["mean_ndvi"]
    median_change = stats_2021["median_ndvi"] - stats_2017["median_ndvi"]
    water_change = stats_2021["water_bare_pct"] - stats_2017["water_bare_pct"]
    dense_change = stats_2021["dense_veg_pct"] - stats_2017["dense_veg_pct"]

    print(f"     Mean NDVI change:     {mean_change:+.4f}")
    print(f"     Median NDVI change:   {median_change:+.4f}")
    print(f"     Water/Bare change:    {water_change:+.1f} percentage points")
    print(f"     Dense Veg change:     {dense_change:+.1f} percentage points")

    # Pixel-level loss
    valid_mask = (ndvi_2017 != 0) & (ndvi_2021 != 0)
    diff_valid = ndvi_diff[valid_mask]
    degraded = np.sum(diff_valid < -0.1)
    improved = np.sum(diff_valid > 0.1)
    stable = np.sum(np.abs(diff_valid) <= 0.1)
    total = diff_valid.size

    print(f"\n     Pixel-level change (threshold ±0.1):")
    print(f"       Degraded:  {100.0 * degraded / total:5.1f}%  ({degraded:,} pixels)")
    print(f"       Stable:    {100.0 * stable / total:5.1f}%  ({stable:,} pixels)")
    print(f"       Improved:  {100.0 * improved / total:5.1f}%  ({improved:,} pixels)")

    print(f"\n{'=' * 70}")
    print("  Interpretation:")
    print("  • Lower NDVI in 2021 indicates drought stress: less green vegetation")
    print("    and more exposed soil/rock around the receded lake shoreline.")
    print("  • Increase in Water/Bare % reflects the dramatic drop in lake level")
    print("    exposing formerly submerged lakebed.")
    print("  • Dense vegetation loss corresponds to riparian zones and hillsides")
    print("    that dried out during the multi-year drought.")
    print("=" * 70)

    # --- Generate comparison figure ---
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    # 2017
    im1 = axes[0].imshow(ndvi_2017, cmap="RdYlGn", vmin=-0.2, vmax=0.9)
    axes[0].set_title("2017 (Recovery Year)\nSept 27", fontsize=12, fontweight="bold")
    axes[0].axis("off")
    plt.colorbar(im1, ax=axes[0], fraction=0.046, pad=0.04, label="NDVI")

    # 2021
    im2 = axes[1].imshow(ndvi_2021, cmap="RdYlGn", vmin=-0.2, vmax=0.9)
    axes[1].set_title("2021 (Extreme Drought)\nSept 24", fontsize=12, fontweight="bold")
    axes[1].axis("off")
    plt.colorbar(im2, ax=axes[1], fraction=0.046, pad=0.04, label="NDVI")

    # Difference
    norm = TwoSlopeNorm(vmin=-0.6, vcenter=0, vmax=0.6)
    im3 = axes[2].imshow(ndvi_diff, cmap="RdBu", norm=norm)
    axes[2].set_title("NDVI Change\n(2021 − 2017)", fontsize=12, fontweight="bold")
    axes[2].axis("off")
    plt.colorbar(im3, ax=axes[2], fraction=0.046, pad=0.04, label="ΔNDVI")

    plt.suptitle("Shasta Lake, CA — Drought Impact on Vegetation (NDVI)",
                 fontsize=14, fontweight="bold", y=0.98)
    plt.tight_layout()
    plt.savefig("shasta_drought_ndvi_comparison.png", dpi=150, bbox_inches="tight")
    print(f"\n  💾 Figure saved: shasta_drought_ndvi_comparison.png")
    print(f"  💾 Difference raster: ndvi_shasta_diff_2021_vs_2017.tif")


if __name__ == "__main__":
    main()
