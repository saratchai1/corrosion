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
