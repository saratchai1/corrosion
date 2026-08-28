# Samut Songkhram Coastal Change

Reproducible geospatial workflow and static WebApp for exploring apparent coastal change in Samut Songkhram, Thailand. The MVP covers eight target epochs from 1985–2026 using Landsat and Sentinel-2 imagery.

The displayed line is an **image-derived water-land boundary**, not a surveyed or tide-normalized shoreline. Every current epoch has `tide_status=unverified`; rates and classes therefore have `LOW` confidence and must not be described as definitive erosion rates.

## MVP outputs

- Quality-masked median surface-reflectance composites in EPSG:32647 COG format (local only)
- MNDWI water-land boundary for eight epochs
- Coastal vegetation spectral proxy and area statistics
- 100 m transects, yearly positions, endpoint and regression rates, and resolution-aware classes
- React + TypeScript + Vite + MapLibre static WebApp with timeline, synchronized comparison, layer controls, transect graph, and responsive layout

The active implementation branch is `feature/coastal-change-webapp`, based on `data/samut-songkhram-satellite-v1`.

## Reproduce the MVP

### 1. Environment and data selection

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/download_mvp_epochs.py
```

The bounded download selects 2–3 full-AOI optical acquisitions per epoch and stores AOI-only source COGs under `data/satellite/`. The tested local working set is about 355 MB, below the 15 GB ceiling. Source and processed TIFFs remain local because Git LFS quota is not verified.

### 2. Build composites, boundaries, vegetation, transects, statistics, and web assets

```bash
python scripts/build_coastal_change_mvp.py
```

This one reproducible command performs steps 2–5 of the analytical workflow:

1. builds per-epoch optical median composites using Landsat `QA_PIXEL` or Sentinel-2 `SCL` masks;
2. compares Otsu, fixed-zero, and percentile MNDWI thresholds, applies conservative cleanup, and extracts a continuous water-land trace;
3. calculates a coastal NDVI vegetation proxy;
4. creates perpendicular transects and change statistics; and
5. prepares WebP/GeoJSON/CSV/JSON assets under `data/processed/web/` and `web/public/data/`.

### 3. Run and build the WebApp

```bash
cd web
npm install
npm run dev
```

Open `http://localhost:5173`. Create the production bundle with:

```bash
npm run build
```

The deployable static bundle is written to `web/dist/`.

## Data and documentation

- [MVP methodology and results](docs/COASTAL_CHANGE_MVP.md)
- [Download and full data workflow](docs/DOWNLOAD_AND_REPRODUCE.md)
- [Scientific and operational limitations](docs/DATA_LIMITATIONS.md)
- [Data sources](docs/DATA_SOURCES.md)

The AOI in `data/aoi/samut_songkhram_aoi.geojson` is provisional. Replace it with a verified administrative/project/coastal analysis boundary before operational use.
