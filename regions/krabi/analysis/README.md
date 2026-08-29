# Krabi change-screening analysis

## Current evidence base

The current analysis uses 48 reused Sentinel-2 plot observations from `saratchai1/prasae`, branch `pdd22-satellite-refetch`:

- 4 plots: 97-VSD, 98-VSD, 99-VSD, 100-VSD
- 12 periods per plot
- 2023-09 through 2026-08
- plot-level NDVI, NDRE, MNDWI, MFI and valid coverage / QA

These are plot-level screening metrics and PNG visualizations. They are **not** georeferenced shoreline rasters.

## QA-weighted trend rule

`script/analyze_krabi_trends.py` uses:

- `GOOD = 1.0`
- `PARTIAL = 0.6`
- `LOW_QA = 0.25`
- `NO_DATA = 0.0`

The QA weight is multiplied by valid coverage fraction. A linear trend is only labelled increasing/decreasing if:

- `R² >= 0.20`, and
- absolute slope is at least `0.015 index units/year`.

Otherwise the result is `NO_CLEAR_LINEAR_TREND`.

This conservative rule is intentional because seasonal water level, monsoon cloud, residual cloud/shadow and phenology can dominate a short 3-year spectral record.

## Result

All four plots currently return `NO_CLEAR_LINEAR_TREND` for NDVI, NDRE and MNDWI.

This means the current data do **not** support a claim of persistent vegetation decline or persistent water increase over the whole record. It does not prove that no local change occurred.

## Temporary NDVI dip flags

The screening rule flags a temporary event when NDVI drops by at least `0.10` from the preceding usable observation and later recovers by at least `0.10`.

Current flags:

| Plot | Dip | QA at dip | NDVI before | NDVI dip | Recovery | QA recovery | NDVI recovery |
|---|---|---|---:|---:|---|---|---:|
| 97-VSD | 2025-06 | GOOD | 0.5179 | 0.3494 | 2025-12 | GOOD | 0.5518 |
| 99-VSD | 2025-09 | LOW_QA | 0.4641 | 0.3203 | 2025-12 | GOOD | 0.5669 |
| 100-VSD | 2025-09 | PARTIAL | 0.4544 | 0.3373 | 2025-12 | GOOD | 0.5086 |

`97-VSD` is the highest-priority flag for follow-up because the dip observation itself is `GOOD` coverage, while the 99-VSD flag is heavily confounded by `LOW_QA`.

Possible explanations include real vegetation stress, seasonal inundation, turbidity/water influence, phenology, or residual atmospheric/cloud effects. Field evidence and spatial raster analysis are required before attributing a cause.

## Shoreline / erosion status

Do not calculate shoreline retreat in metres from the reused PNGs. They do not preserve the georeferencing needed for defensible distance measurements.

The next defensible erosion workflow is:

1. obtain AOI-clipped COG/GeoTIFF Sentinel-2 / Landsat / Sentinel-1 products;
2. build water/land masks on a fixed projected grid (EPSG:32647);
3. pair scenes with comparable tide levels and record tide datum/status;
4. extract water edges and/or water-gain polygons;
5. compare against a stable baseline with transects or polygon change;
6. report uncertainty at least at the raster-resolution + tide-mismatch level.

Until step 3 is satisfied, water-edge change must remain `TIDE_UNVERIFIED_SCREENING`.
