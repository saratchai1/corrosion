# Data limitations

1. **AOI is provisional.** The repository was empty at project initialization, so no verified SEG030/project polygon existed. The supplied AOI is intentionally broad and must not be represented as the official project boundary.
2. **Tide is not yet controlled.** Acquisition timestamps are retained in UTC and Asia/Bangkok, but tide level/station/datum must remain blank with `tide_status=unverified` until a sourced tide record is joined. Do not invent or interpolate tide values without an identified source and documented method.
3. **Water-land edge is not automatically the true shoreline.** Intertidal mudflats at the Mae Klong mouth and Don Hoi Lot are strongly affected by tide, suspended sediment, waves and season. Any image-derived boundary is a shoreline proxy/observation until tide control and independent/field validation are available.
4. **Cloud metrics differ.** Scene-level `eo:cloud_cover` is only a discovery/ranking hint. Sentinel-2 selection must assess cloud and cloud shadow over the AOI using SCL/quality data. Landsat selection must use QA pixels over the AOI.
5. **Spatial resolution limits inference.** Landsat 30 m supports long-term trends but not small planting-plot confirmation. Sentinel-2 20 m bands remain 20 m information even when resampled to a 10 m grid.
6. **Sentinel-1 is supporting evidence.** VV/VH can help during cloud cover and with water/mudflat context, but is not used alone to assert shoreline position.
7. **Landsat 7 SLC-off.** ETM+ acquisitions after the 2003 Scan Line Corrector failure contain systematic data gaps; composites/QA must account for them rather than treating gaps as change.
8. **Mixed sensor history.** Landsat TM/ETM+/OLI/OLI-2 spectral responses differ; long-term indices/trends should use sensor-aware harmonization or uncertainty treatment.
9. **COG/LFS delivery status.** Git LFS runtime state and account quota cannot be tested through the GitHub repository API used during initial setup. Therefore no large raster is pushed in v1 until `git lfs env` and no-cost quota are confirmed on a clone-capable runtime.
10. **Network execution.** The current execution environment cannot make arbitrary outbound STAC/API calls from the code runtime, so scene catalogs are staged with schema only. Run the documented commands in a network-enabled environment to populate candidates and acquire AOI windows.

## QA flags to record during visual review
Use catalog `qa_status`/notes to identify cloud, cloud shadow, haze, turbid water, exposed mudflat, suspicious geolocation, scan-line gaps and other anomalies. A candidate can remain in the catalog while being excluded from a particular composite.
