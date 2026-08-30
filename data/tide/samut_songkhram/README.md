# Samut Songkhram tide predictions

This directory stores **free, cited tide predictions** used to screen satellite scenes for the Samut Songkhram erosion analysis.

## Primary station

- Station: `Pak Nam Mae Klong` / `ปากน้ำแม่กลอง`
- Preferred datum: `MSL`
- Time zone: `Asia/Bangkok` (`UTC+07:00`)
- Official landing page: `https://hydro.navy.mi.th/waterlaveltable`

Use the official Mean Sea Level table where available. Do not mix MSL and Lowest Low Water values in one time series without a documented datum conversion.

## Current versioned coverage

The repository currently contains the verified official **2026** hourly MSL table:

```text
data/tide/samut_songkhram/pak_nam_mae_klong_hourly_msl.csv
```

It contains 8,760 hourly predictions parsed from the official annual PDF. The accompanying manifest records the resolved PDF URL, SHA-256 checksum, page count, monthly day/hour counts, tide range and parser method:

```text
data/tide/samut_songkhram/pak_nam_mae_klong_hourly_msl_manifest.json
```

The former annual PDF URLs for 2023–2025 returned HTTP 404 during the reproducible build on 2026-08-30. Those nine satellite scenes remain explicitly unmatched. Their status and handling policy are recorded in:

```text
data/tide/samut_songkhram/pak_nam_mae_klong_source_availability.json
```

No missing year is filled from another year, an uncited table or a search-result snippet.

## Rebuild the verified catalog

```bash
python scripts/build_rtn_mae_klong_tide_catalog.py \
  --years 2026 \
  --refresh
```

The parser validates every calendar day and requires exactly 24 hourly values per day. It rejects an annual PDF if the expected 8,760 or 8,784 values cannot be recovered.

When a cited official annual PDF for an earlier year is recovered, pass that year to the same command. Do not add a year unless its source and datum are verifiable.

## CSV schema

```csv
datetime_bangkok,tide_m_msl,station_name,datum,source_url,source_year,qa_status
```

Rules:

1. one row per full local hour;
2. use ISO-8601 time with `+07:00`;
3. record the exact resolved source URL and year;
4. retain parsing QA status;
5. never label predicted tide as an observed local water level.

The header-only fallback template is `pak_nam_mae_klong_hourly_msl_template.csv`.

## Match to the satellite catalog

```bash
python scripts/match_scene_tides.py \
  --scene-catalog data/catalog/project_samut_songkhram_sentinel2_scenes.csv \
  --tide-csv data/tide/samut_songkhram/pak_nam_mae_klong_hourly_msl.csv \
  --output data/catalog/project_samut_songkhram_sentinel2_scenes_tide_matched.csv
```

The current matched catalog contains 12 project scenes. The three 2026 scenes are matched by linear interpolation between adjacent hourly predictions; the nine scenes from 2023–2025 remain `unmatched_no_bracket`.

## Scientific limit

This is a **tide-screening input**, not a tide-normalized shoreline. Predicted station tide improves scene comparability but does not replace an observed water-level logger at each plot. For the Mae Klong / Don Hoi Lot mudflat, the primary project indicators should be the seaward mangrove edge and bank edge, with the waterline used only as supporting evidence.
