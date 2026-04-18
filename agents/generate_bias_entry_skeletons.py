#!/usr/bin/env python3

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

OUT_DIR = Path("src/data/entries")
TODAY = date.today().isoformat()

# 47-entry inventory from build plan categories.
ENTRIES = [
    # Precipitation / ITCZ (6)
    ("double-itcz", "Double ITCZ", "precipitation", "tropical_pacific"),
    ("tropical-diurnal-timing", "Tropical Diurnal Timing Bias", "precipitation", "tropics"),
    ("sahel-dry-bias", "Sahel Dry Bias", "precipitation", "sahel"),
    ("amazon-dry-season", "Amazon Dry Season Bias", "precipitation", "amazon"),
    ("monsoon-onset-delay", "Monsoon Onset Delay", "precipitation", "south_asia"),
    ("itcz-width-bias", "ITCZ Width Bias", "precipitation", "tropics"),

    # Temperature / SST (8)
    ("southern-ocean-warm-sst", "Southern Ocean Warm SST Bias", "temperature", "southern_ocean"),
    ("arctic-amplification-bias", "Arctic Amplification Bias", "temperature", "arctic"),
    ("tropical-cold-troposphere", "Tropical Cold Troposphere Bias", "temperature", "tropics"),
    ("cold-tongue-bias", "Cold Tongue Bias", "temperature", "equatorial_pacific"),
    ("semi-arid-land-warm", "Semi-Arid Land Warm Bias", "temperature", "semi_arid_land"),
    ("nw-pacific-cold-sst", "Northwest Pacific Cold SST Bias", "temperature", "northwest_pacific"),
    ("ne-pacific-warm-sst", "Northeast Pacific Warm SST Bias", "temperature", "northeast_pacific"),
    ("global-mean-sst-shift", "Global Mean SST Shift", "temperature", "global"),

    # Circulation (7)
    ("amoc-strength-bias", "AMOC Strength Bias", "circulation", "north_atlantic"),
    ("jet-equatorward-bias", "Jet Stream Equatorward Bias", "circulation", "midlatitudes"),
    ("mjo-propagation", "MJO Propagation Speed Bias", "circulation", "indo_pacific"),
    ("blocking-frequency-bias", "Blocking Frequency Bias", "circulation", "midlatitudes"),
    ("enso-amplitude-bias", "ENSO Amplitude Bias", "circulation", "equatorial_pacific"),
    ("hadley-cell-expansion", "Hadley Cell Expansion Bias", "circulation", "subtropics"),
    ("nao-representation-bias", "NAO Representation Bias", "circulation", "north_atlantic"),

    # Clouds / Radiation (6)
    ("southern-ocean-shortwave", "Southern Ocean Shortwave Bias", "clouds", "southern_ocean"),
    ("low-cloud-underestimate", "Low Cloud Underestimate", "clouds", "eastern_subtropical_oceans"),
    ("high-ecs-hot-model", "High ECS Hot Model Problem", "clouds", "global"),
    ("toa-energy-drift", "TOA Energy Drift", "clouds", "global"),
    ("tropical-cloud-anvil", "Tropical Cloud Anvil Bias", "clouds", "tropics"),
    ("cloud-phase-bias", "Cloud Phase Partition Bias", "clouds", "high_latitudes"),

    # Ocean (5)
    ("mixed-layer-depth-bias", "Mixed Layer Depth Bias", "ocean", "global_ocean"),
    ("deep-ocean-ventilation", "Deep Ocean Ventilation Bias", "ocean", "global_ocean"),
    ("subtropical-gyre-bias", "Subtropical Gyre Bias", "ocean", "subtropical_oceans"),
    ("acc-transport-bias", "ACC Transport Bias", "ocean", "southern_ocean"),
    ("equatorial-upwelling-bias", "Equatorial Upwelling Bias", "ocean", "equatorial_pacific"),

    # Land surface (4)
    ("central-us-warm-dry", "Central US Warm/Dry Bias", "land", "central_us"),
    ("permafrost-extent-bias", "Permafrost Extent Bias", "land", "high_latitudes"),
    ("soil-moisture-coupling", "Soil Moisture Coupling Bias", "land", "continental_regions"),
    ("semi-arid-albedo-bias", "Semi-Arid Albedo Bias", "land", "semi_arid_land"),

    # Sea ice (3)
    ("arctic-extent-loss-rate", "Arctic Sea Ice Extent Loss Rate Bias", "sea_ice", "arctic"),
    ("antarctic-sea-ice-trend", "Antarctic Sea Ice Trend Bias", "sea_ice", "antarctic"),
    ("sea-ice-thickness-bias", "Sea Ice Thickness Bias", "sea_ice", "polar"),

    # Resolved / historical (8)
    ("cmip3-tropical-cold-bias", "CMIP3 Tropical Cold Bias", "temperature", "tropics"),
    ("early-runaway-sea-ice", "Early Runaway Sea Ice Bias", "sea_ice", "polar"),
    ("old-convective-adjustment", "Old Convective Adjustment Bias", "precipitation", "tropics"),
    ("pre-cmip5-ocean-drift", "Pre-CMIP5 Ocean Drift Bias", "ocean", "global_ocean"),
    ("cmip5-southern-ocean-fix-story", "CMIP5 Southern Ocean Fix Story", "clouds", "southern_ocean"),
    ("flux-correction-era-bias", "Flux Correction Era Bias", "ocean", "global_ocean"),
    ("amip-sst-cold-bias", "AMIP SST Cold Bias", "temperature", "global_ocean"),
    ("early-land-carbon-bias", "Early Land Carbon Bias", "land", "global_land"),
]


def skeleton(entry_id: str, name: str, category: str, region: str) -> dict:
    return {
        "id": entry_id,
        "name": name,
        "version": "1.0",
        "last_updated": TODAY,
        "category": category,
        "region": region,
        "season": "annual",
        "affected_variables": [],
        "description": f"Draft description placeholder for {name}.",
        "persistence": "longstanding",
        "cmip_history": [],
        "severity_by_model": {},
        "implicated_params": [],
        "fix_attempts": [],
        "cascade_links": [],
        "disputed_mechanisms": [],
        "citations": [],
        "feedback_history": [],
        "changelog": [],
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    created = 0
    skipped = 0

    for entry_id, name, category, region in ENTRIES:
        target = OUT_DIR / f"{entry_id}.json"
        if target.exists():
            skipped += 1
            continue
        payload = skeleton(entry_id, name, category, region)
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        created += 1

    print(f"created={created} skipped={skipped} total_expected={len(ENTRIES)}")


if __name__ == "__main__":
    main()
