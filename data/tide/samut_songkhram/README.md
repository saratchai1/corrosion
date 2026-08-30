# Samut Songkhram tide predictions

This directory stores **free, cited tide predictions** used to screen satellite scenes for the Samut Songkhram erosion analysis.

## Primary station

- Station: `Pak Nam Mae Klong` / `ปากน้ำแม่กลอง`
- Preferred datum: `MSL`
- Time zone: `Asia/Bangkok` (`UTC+07:00`)
- Official landing page: `https://hydro.navy.mi.th/waterlaveltable`

Use the official Mean Sea Level table where available. Do not mix MSL, Chart Datum and Lowest Low Water values without a documented conversion.

## Current versioned coverage

### Official hourly baseline — 2026

```text
data/tide/samut_songkhram/pak_nam_mae_klong_hourly_msl.csv
data/tide/samut_songkhram/pak_nam_mae_klong_hourly_msl_manifest.json
```

The official baseline contains 8,760 hourly MSL predictions parsed from the Hydrographic Department annual PDF. The manifest records the resolved PDF URL, SHA-256 checksum, page count, monthly day/hour counts, tide range and parser method.

### Secondary published extrema — 2023–2025

The former official annual PDF URLs for 2023–2025 returned HTTP 404. The repository therefore preserves the published high/low turning points from ThailandTideTables as an explicitly separate secondary tier:

```text
data/tide/samut_songkhram/pak_nam_mae_klong_2023_2025_secondary_extrema.csv
data/tide/samut_songkhram/pak_nam_mae_klong_2023_2025_secondary_extrema_manifest.json
data/tide/samut_songkhram/pak_nam_mae_klong_secondary_extrema_2026_validation.json
```

The collection contains all 36 monthly pages and 3,608 published extrema:

- 2023: 1,208 events;
- 2024: 1,199 events; and
- 2025: 1,201 events.

The source pages state Chart Datum and attribute the data to World Tides and the Hydrographic Department, Royal Thai Navy. Candidate MSL values are calculated as:

```text
height above MSL = published Chart Datum height - 2.14 m
```

The 2.14 m offset is the published Pak Nam Mae Klong Lowest Low Water distance below MSL. The conversion was checked against the official 2026 hourly MSL table using 2026 secondary extrema:

- mean absolute error: 0.02215 m;
- RMSE: 0.02723 m;
- mean bias: -0.00040 m;
- 95th-percentile absolute error: 0.05000 m; and
- maximum absolute error: 0.07000 m.

This validation supports datum consistency for screening. It does not convert the secondary extrema into official hourly predictions or observed local water levels.

Some calendar dates legitimately contain no listed extremum at this mixed-tide station. The workflow does not fabricate events for those dates. Instead, it checks monthly coverage, boundary coverage, missing-day runs and year-wide temporal continuity. The maximum source-event interval in the 2023–2025 series is 50.08333 hours.

## Rebuild the official 2026 baseline

```bash
python scripts/build_rtn_mae_klong_tide_catalog.py \
  --years 2026 \
  --refresh
```

The official parser validates every calendar day and requires exactly 24 hourly values per day. It rejects the annual PDF unless all expected 8,760 or 8,784 values are recovered.

## Rebuild the 2023–2025 secondary series

The source site blocks GitHub-hosted runners with HTTP 403. The reproducible workflow therefore uses Jina Reader only as a retrieval transport, while retaining the original ThailandTideTables URL as the data source and recording both URLs in QA metadata.

```bash
python scripts/cache_thailandtidetables_via_jina.py \
  --years 2023 2024 2025 2026 \
  --refresh

python -m scripts.build_secondary_mae_klong_tide_catalog \
  --years 2023 2024 2025 \
  --validation-year 2026 \
  --require-validation
```

Raw reader pages and cache diagnostics are retained as GitHub Actions artifacts; compact data, checksums, source URLs, QA results and derived scene values are versioned in Git.

## Satellite-scene matching

```text
data/catalog/project_samut_songkhram_sentinel2_scenes_tide_matched.csv
```

The catalog contains 12 Sentinel-2 project scenes:

- three 2026 scenes retain `predicted_interpolated` from the official hourly table; and
- nine 2023–2025 scenes use `modelled_secondary_extrema_cosine`, calculated between consecutive published extrema.

All 12 scenes now have MSL tide metadata. The largest secondary interpolation bracket used by a project scene is 17.71667 hours. Source tier, validation status, before/after extrema, bracket length and uncertainty wording remain in each row.

## Scientific limit

This is a **tide-aware screening input**, not a tide-normalized surveyed shoreline. Station predictions improve scene comparability but do not replace a water-level logger at each plot. Secondary extrema interpolation is less authoritative than the official hourly table and must remain distinguishable in analysis and reporting.

For the Mae Klong / Don Hoi Lot mudflat, the primary project indicators should be the seaward mangrove edge and bank edge. The image-derived waterline should be used only as supporting evidence.
