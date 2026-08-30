# Samut Songkhram tide predictions

This directory stores **free, cited tide predictions** used to screen satellite scenes for the Samut Songkhram erosion analysis.

## Primary station

- Station: `Pak Nam Mae Klong` / `ปากน้ำแม่กลอง`
- Preferred datum: `MSL`
- Time zone: `Asia/Bangkok` (`UTC+07:00`)
- Official landing page: `https://hydro.navy.mi.th/waterlaveltable`

Use the official Mean Sea Level table where available. Do not mix MSL and Lowest Low Water values in one time series without a documented datum conversion.

## Build the official 2023–2026 hourly catalog

The repository can download the annual official station PDFs, resolve archived URL variants, parse the 12 monthly hourly tables, and validate the expected number of hours per year:

```bash
python scripts/build_rtn_mae_klong_tide_catalog.py --refresh
```

This creates:

```text
data/tide/samut_songkhram/pak_nam_mae_klong_hourly_msl.csv
data/tide/samut_songkhram/pak_nam_mae_klong_hourly_msl_manifest.json
```

The manifest records each resolved PDF URL, SHA-256 checksum, page count, parsed hour count, tide range, and URL attempts. A year is rejected if the parser cannot recover every expected day and all 24 hourly values per day.

The generated values are harmonic **predictions**, not observations at the planting plots. They are retained at one-hour resolution in Thailand local time.

## Required CSV schema

```csv
datetime_bangkok,tide_m_msl,station_name,datum,source_url,source_year,qa_status
```

Rules:

1. one row per full local hour;
2. use ISO-8601 time with `+07:00`;
3. record the exact resolved official PDF URL and year;
4. retain parsing QA status;
5. never label predicted tide as an observed local water level.

The header-only fallback template is `pak_nam_mae_klong_hourly_msl_template.csv`.

## Match to satellite catalog

```bash
python scripts/match_scene_tides.py \
  --scene-catalog data/catalog/project_samut_songkhram_sentinel2_scenes.csv \
  --tide-csv data/tide/samut_songkhram/pak_nam_mae_klong_hourly_msl.csv \
  --output data/catalog/project_samut_songkhram_sentinel2_scenes_tide_matched.csv
```

The script records exact or interpolated prediction, source URL, datum, time gap and QA. Unmatched scenes remain explicit and are not silently filled.

## Scientific limit

This is a **tide-aware screening input**. It improves comparability between satellite scenes but does not replace a water-level logger at the plot. For the Mae Klong / Don Hoi Lot mudflat, the primary project indicators should be the seaward mangrove edge and bank edge, with the waterline used as supporting evidence.
