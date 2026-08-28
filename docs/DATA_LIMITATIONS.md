# Data limitations

1. **AOI is provisional.** The repository was empty at project initialization, so no verified SEG030/project polygon existed. The supplied AOI is intentionally broad and must not be represented as the official project boundary.
2. **Tide is not yet controlled.** Acquisition timestamps are retained in UTC and Asia/Bangkok, but tide level/station/datum must remain blank with `tide_status=unverified` until a sourced tide record is joined. Do not invent or interpolate tide values without an identified source and documented method.
3. **Water-land edge is not automatically the true shoreline.** Intertidal mudflats at the Mae Klong mouth and Don Hoi Lot are strongly affected by tide, suspended sediment, waves and season. Any image-derived boundary is a shoreline proxy/observation until tide control and independent/field validation are available.
4. **Cloud metrics differ.** Scene-level `eo:cloud_cover` is only a discovery/ranking hint. Sentinel-2 selection must assess cloud and cloud shadow over the AOI using SCL/quality data. Landsat selection must use QA pixels over the AOI.
5. **Spatial resolution limits inference.** Landsat 30 m supports long-term trends but not small planting-plot confirmation. Sentinel-2 20 m bands remain 20 m information even when resampled to a 10 m grid.
6. **Sentinel-1 is supporting evidence.** VV/VH can help during cloud cover and with water/mudflat context, but is not used alone to assert shoreline position.
7. **Landsat 7 SLC-off.** ETM+ acquisitions after the 2003 Scan Line Corrector failure contain systematic data gaps; composites/QA must account for them rather than treating gaps as change.
8. **Mixed sensor history.** Landsat TM/ETM+/OLI/OLI-2 spectral responses differ; long-term indices/trends should use sensor-aware harmonization or uncertainty treatment.
9. **COG/LFS delivery status.** Git LFS 3.8.0 is installed locally and the repository patterns are configured, but this account has no authenticated LFS upload access in the current runtime and no-cost quota cannot be confirmed confidently. Therefore v1 pushes scripts, catalogs, manifests, previews and QA only; downloaded raster COGs remain local.
10. **Provider coverage.** Sentinel-2 search returned no AOI-intersecting Level-2A item in 2016 from the verified Earth Search collection; usable records begin in 2017. Landsat search likewise returned no intersecting Level-2 records for 1984–1986 in the selected WRS path/row/AOI. These are recorded as observed provider results, not backfilled with invented data.
11. **Sentinel-1 geolocation.** The Planetary Computer GRD measurement assets use GCP geolocation. The downloader uses explicit GCP reprojection and visual QA is required for every new orbit/processing variant.

## QA flags to record during visual review
Use catalog `qa_status`/notes to identify cloud, cloud shadow, haze, turbid water, exposed mudflat, suspicious geolocation, scan-line gaps and other anomalies. A candidate can remain in the catalog while being excluded from a particular composite.
