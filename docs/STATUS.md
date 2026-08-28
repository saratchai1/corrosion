# Satellite data workflow status

Generated on 2026-08-28 for branch `data/samut-songkhram-satellite-v1`.

- Repository was empty at initialization; no verified SEG030/project AOI existed.
- Provisional AOI added for Samut Songkhram coast / Mae Klong mouth / Don Hoi Lot reference area.
- Live STAC collections were verified and the original Earth Search 400 was diagnosed as an invalid date-only datetime interval; requests now use RFC3339 timestamps and yearly paginated searches.
- Completed catalogs: Sentinel-2 1,793 candidates / 40 selected dates; Landsat full-range catalog is generated from Planetary Computer; Sentinel-1 740 candidates / 232 selected dates.
- One real AOI-only download was tested for each dataset. Twenty raster COGs and six previews passed structural/visual QA; S1 GCP warping is explicit.
- Git LFS 3.8.0 is installed and tracking rules are present; the endpoint reports basic auth, but no-cost upload/quota confirmation is unavailable. Therefore **no raster binaries are pushed**; local rasters are recorded in manifests/checksums.
- Run the reproduction commands in `docs/DOWNLOAD_AND_REPRODUCE.md` from a network-enabled clone to reproduce catalogs and AOI-only COGs.
