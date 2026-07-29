"""Direct pipeline test against real Maui, Hawaii 2026 flood imagery.

Exercises the flood tools without the LLM to confirm the data path works:
geocode -> scene search (optical + SAR) -> water/flood analysis.
The 2026 Hawaii floods were a Kona low, ~March 9-22 2026 (peak Mar 13-15),
hitting Kihei and Lahaina on Maui.
"""

import json


def show(label, obj):
    print(f"\n===== {label} =====")
    print(json.dumps(obj, indent=2, default=str))


def main():
    from flood_tools import (
        geocode_place,
        search_flood_scenes,
        analyze_flood_change,
        analyze_sar_flood,
        assess_flood_claim,
        search_aws_open_data,
    )

    # 1) Geocode Kihei, Maui (hard hit in the March 2026 floods).
    geo = geocode_place("Kihei, Maui, Hawaii")
    show("geocode Kihei, Maui", geo)

    # Use a small AOI around Kihei so reads stay fast.
    lat = geo["center"]["lat"]
    lon = geo["center"]["lon"]
    d = 0.05  # ~5.5 km half-width
    bbox = [lon - d, lat - d, lon + d, lat + d]
    print(f"\nAnalysis bbox: {bbox}")

    # 2) Find a "before" optical scene (dry baseline, Feb 2026).
    before = search_flood_scenes(bbox, "2026-02-01", "2026-03-08", sensor="optical", max_cloud_cover=25)
    show("optical BEFORE candidates", before)

    # 3) Find an "after" optical scene (during/just after the flood).
    after = search_flood_scenes(bbox, "2026-03-13", "2026-04-05", sensor="optical", max_cloud_cover=60)
    show("optical AFTER candidates", after)

    # 4) SAR scenes (cloud-penetrating) around the event.
    sar = search_flood_scenes(bbox, "2026-03-01", "2026-03-25", sensor="sar")
    show("SAR candidates", sar)

    # 5) If we have an optical pair, run NDWI change detection.
    if before["scene_count"] and after["scene_count"]:
        b_id = before["scenes"][0]["id"]
        a_id = after["scenes"][-1]["id"]
        try:
            change = analyze_flood_change(b_id, a_id, bbox)
            show("optical flood change (NDWI)", change)
        except Exception as e:
            print(f"optical change failed: {e}")

    # 6) If we have a SAR pair, run backscatter change detection.
    if sar["scene_count"] >= 2:
        try:
            sar_change = analyze_sar_flood(sar["scenes"][0]["id"], sar["scenes"][-1]["id"], bbox)
            show("SAR flood change (VV)", sar_change)
        except Exception as e:
            print(f"SAR change failed: {e}")

    # 7) RODA open-data discovery.
    show("RODA search 'sentinel'", search_aws_open_data("sentinel", max_results=3))

    # 8) Claim triage using a sample number.
    show("claim assessment", assess_flood_claim(
        "Keola K.", "Kihei, Maui, HI", newly_flooded_km2=0.32, property_in_flood_zone=True))


if __name__ == "__main__":
    main()
