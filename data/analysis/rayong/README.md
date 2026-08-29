# Rayong Coastal Change & Mangrove Analysis Methodology

## Proposed Analytical Approach

### A. Shoreline extraction
- **Optical (Sentinel-2, Landsat):**
  - Use NDWI (Normalized Difference Water Index) and MNDWI (Modified NDWI) to segment water from land.
  - Employ quality flags and cloud masking (QA_PIXEL, SCL) to remove cloudy/shadowed pixels.
- **Radar (Sentinel-1):**
  - Utilize VV and VH polarizations for water-land discrimination.
  - Thresholding backscatter values, taking advantage of Sentinel-1's cloud-penetrating capability, which is especially useful during the rainy season.

### B. Shoreline change
- **Transects:** Generate transects approximately perpendicular to the reference coastline at regular intervals.
- **Metrics:**
  - Track shoreline position along each transect over time.
  - Calculate **Net Shoreline Movement (NSM)** (distance between oldest and newest shorelines).
  - Calculate **End Point Rate (EPR)** in meters/year (NSM divided by the time elapsed).

### C. Mangrove change
- **Vegetation Indices:** Combine NDVI, NDMI, and Sentinel-2 red-edge bands to isolate mangrove vegetation from other land cover types.
- **Temporal Persistence:** Use a time-series approach to identify stable mangrove areas versus transient noise.
- **Metrics:**
  - Total mangrove area.
  - Mangrove width (measured along the established transects).
  - Vegetation gain/loss and annualized change rates.

### D. Planting effectiveness
- **Reference Comparison:** Compare the trajectory of each planting polygon (`14(1)-STC`, `14-STC`, `15-VSD`, etc.) against carefully selected, nearby unplanted reference areas.
- **Metrics:**
  - Vegetation index trajectory over time.
  - Canopy/vegetation coverage percentage.
  - Spatially explicit mangrove expansion.
  - Shoreline movement (accretion/erosion signal) immediately seaward of the plot.
- **Causality Note:** Do NOT claim causal impact merely because planting and shoreline change correlate. Many environmental factors (sediment supply, wave energy, bathymetry) influence erosion rates regardless of planting efforts.

## Execution Details
- **Raw GIS Source:** The original features were separated into `rayong_planting_plots_raw.geojson` to preserve integrity.
- **Geometry Repair:** We used `shapely.make_valid` and extracted polygonal features to fix invalid geometries safely, keeping area deviations < 0.5%.
- **AOI Derivation:** Validated at ~154 sq km enclosing Rayong coastline and plots.
- **Satellite Sources:** Element 84 Earth Search (Sentinel-2), Microsoft Planetary Computer (Landsat, Sentinel-1).
- **Scene-Selection Logic:** Extracted scenes meeting maximum coverage and minimal cloud-cover thresholds, filtering through temporal constraints (e.g., max 4 Sentinel-2 per year).
- **Tide Source:** Map Ta Phut / Ko Samet (Hydrographic Department, Royal Thai Navy) identified. Due to no live API, tide matching is currently BLOCKED pending real-time access.
- **Shoreline Extraction:** NDWI applied to Sentinel-2 imagery (B3 and B8), Otsu thresholding approach, vectorized to line features.
- **Transect Generation:** Extracted convex-hull-simplified shoreline as baseline, projected perpendiculars spaced at 100m intervals.
- **NSM/EPR Calculation:** Script implemented but populated with 0s because only a single test observation exists pending tide unblocking.
- **Limitations:** Cannot confidently proceed to full historical download and trend calculation until a programmatic tide data source is established to match timestamps with tidal heights.
